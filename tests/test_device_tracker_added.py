"""Coverage for async_added_to_hass / async_update_config / _update_state paths."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
from shapely.geometry import Polygon

from custom_components.polygonal_zones.device_tracker import PolygonalZoneEntity


def _make_entity() -> PolygonalZoneEntity:
    return PolygonalZoneEntity(
        tracked_entity_id="device_tracker.phone",
        config_entry_id="entry-id",
        zone_urls=["https://example.com/zones.json"],
        own_id="device_tracker.polygonal_zones_phone",
        prioritized_zone_files=False,
        editable_file=False,
    )


def _make_hass() -> SimpleNamespace:
    bus = SimpleNamespace(async_listen=MagicMock(return_value=lambda: None))

    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        bus=bus,
        states=SimpleNamespace(get=MagicMock(return_value=None)),
        async_create_task=MagicMock(),
        async_add_executor_job=aaej,
    )


async def test_added_to_hass_initializes_zones_immediately() -> None:
    """async_at_started callback runs the initialiser; zones load + state updates."""
    entity = _make_entity()
    entity.hass = _make_hass()
    entity.async_get_last_state = AsyncMock(return_value=None)

    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    df = pd.DataFrame([{"name": "Home", "priority": 0, "geometry": polygon}])

    captured = {}

    def _capture(hass, cb):
        captured["cb"] = cb
        return lambda: None

    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.async_at_started",
            side_effect=_capture,
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.get_zones",
            new=AsyncMock(return_value=df),
        ),
        patch.object(PolygonalZoneEntity, "async_write_ha_state", lambda self: None),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_create_issue"),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
    ):
        await entity.async_added_to_hass()
        await captured["cb"](entity.hass)

    assert not entity._zones.empty
    assert entity._attr_available is True


async def test_added_to_hass_failure_schedules_retry() -> None:
    """When get_zones raises and attempts < MAX, async_call_later is armed."""
    entity = _make_entity()
    entity.hass = _make_hass()
    entity.async_get_last_state = AsyncMock(return_value=None)

    call_later_mock = MagicMock(return_value=lambda: None)
    captured = {}

    def _capture(hass, cb):
        captured["cb"] = cb
        return lambda: None

    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.async_at_started",
            side_effect=_capture,
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.get_zones",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.async_call_later",
            new=call_later_mock,
        ),
    ):
        await entity.async_added_to_hass()
        await captured["cb"](entity.hass)

    call_later_mock.assert_called_once()
    delay = call_later_mock.call_args.args[1]
    assert delay == 30  # base delay on first failure


async def test_added_to_hass_exhausted_retries_marks_unavailable() -> None:
    """After MAX_LOAD_ATTEMPTS, the entity goes unavailable and no further retry is armed."""
    entity = _make_entity()
    entity.hass = _make_hass()
    entity.async_get_last_state = AsyncMock(return_value=None)

    call_later_mock = MagicMock(return_value=lambda: None)
    # Force the closure to think it's the final attempt: stub async_at_started to invoke
    # the inner function with attempt=5
    captured = {}

    def fake_at_started(hass, cb):
        captured["cb"] = cb
        return lambda: None

    create_issue_mock = MagicMock()
    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.async_at_started",
            side_effect=fake_at_started,
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.get_zones",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.async_call_later",
            new=call_later_mock,
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.ir.async_create_issue",
            new=create_issue_mock,
        ),
    ):
        await entity.async_added_to_hass()
        await captured["cb"](entity.hass, attempt=5)

    call_later_mock.assert_not_called()
    create_issue_mock.assert_called_once()
    assert entity._attr_available is False


async def test_update_config_reads_new_data_and_reloads() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._async_write_ha_state = MagicMock()

    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    df = pd.DataFrame([{"name": "Home", "priority": 0, "geometry": polygon}])

    new_entry = SimpleNamespace(
        data={"zone_urls": ["https://new.example/zones.json"], "prioritize_zone_files": True}
    )

    with patch(
        "custom_components.polygonal_zones.device_tracker.get_zones",
        new=AsyncMock(return_value=df),
    ):
        await entity.async_update_config(new_entry)

    assert entity._zones_urls == ["https://new.example/zones.json"]
    assert entity._prioritize_zone_files is True


async def test_update_config_keeps_previous_zones_on_failure() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._async_write_ha_state = MagicMock()

    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    entity._zones = pd.DataFrame([{"name": "Home", "priority": 0, "geometry": polygon}])

    new_entry = SimpleNamespace(
        data={"zone_urls": ["https://nope"], "prioritize_zone_files": False}
    )

    with patch(
        "custom_components.polygonal_zones.device_tracker.get_zones",
        new=AsyncMock(side_effect=RuntimeError("nope")),
    ):
        await entity.async_update_config(new_entry)

    # Previous zones preserved
    assert not entity._zones.empty


async def test_update_state_invokes_update_location_when_attrs_present() -> None:
    entity = _make_entity()
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    entity._zones = pd.DataFrame([{"name": "Home", "priority": 0, "geometry": polygon}])

    async def aaej(func, *args):
        return func(*args)

    state = SimpleNamespace(attributes={"latitude": 0.5, "longitude": 0.5, "gps_accuracy": 5})
    entity.hass = SimpleNamespace(
        states=SimpleNamespace(get=MagicMock(return_value=state)),
        async_add_executor_job=aaej,
    )

    with patch.object(PolygonalZoneEntity, "async_write_ha_state", lambda self: None):
        await entity._update_state()
    assert entity._attr_location_name == "Home"


async def test_update_state_skips_when_source_state_missing() -> None:
    entity = _make_entity()
    entity.hass = SimpleNamespace(states=SimpleNamespace(get=MagicMock(return_value=None)))

    with patch.object(PolygonalZoneEntity, "async_write_ha_state", lambda self: None):
        await entity._update_state()
    # location_name stays at default None
    assert entity._attr_location_name is None
