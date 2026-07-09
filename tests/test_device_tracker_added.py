"""Coverage for async_added_to_hass / _update_state / reload escalation paths."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
import pytest
from shapely.geometry import Polygon

from custom_components.polygonal_zones.device_tracker import PolygonalZoneEntity
from custom_components.polygonal_zones.utils.zones import Zone, ZoneLoadResult


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
    # Provide a valid source-tracker state so _update_state doesn't flip
    # availability to False on the unavailable-source path.
    entity.hass.states.get = MagicMock(
        return_value=SimpleNamespace(
            state="home",
            attributes={"latitude": 0.5, "longitude": 0.5, "gps_accuracy": 5},
        )
    )
    entity.async_get_last_state = AsyncMock(return_value=None)

    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    zones = [Zone(name="Home", geometry=polygon, priority=0)]

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
            "custom_components.polygonal_zones.device_tracker.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=zones)),
        ),
        patch.object(PolygonalZoneEntity, "async_write_ha_state", lambda self: None),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_create_issue"),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
    ):
        await entity.async_added_to_hass()
        await captured["cb"](entity.hass)

    assert entity._zones
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
            "custom_components.polygonal_zones.device_tracker.load_zones",
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
    # Equal jitter spreads the first-attempt retry across [15, 30]s so
    # entities sharing a zone source don't retry in lockstep.
    assert 15 <= delay <= 30


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
            "custom_components.polygonal_zones.device_tracker.load_zones",
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


async def test_added_to_hass_all_uris_failed_escalates_and_retries() -> None:
    """The real failure shape — load_zones returns empty zones + failure records
    (not a raised exception) — must still escalate to ZoneFileCorrupt and arm a
    retry. Guards the duplicated escalation branch from drifting from get_zones."""
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
            "custom_components.polygonal_zones.device_tracker.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=[], failures=[("http://x", "boom")])),
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.async_call_later",
            new=call_later_mock,
        ),
    ):
        await entity.async_added_to_hass()
        await captured["cb"](entity.hass)

    call_later_mock.assert_called_once()
    assert entity._last_load_result == "failed"


async def test_reload_zones_all_uris_failed_raises_for_service() -> None:
    """Same failure shape through the reload_zones service path → HomeAssistantError."""
    entity = _make_entity()
    entity.hass = _make_hass()

    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=[], failures=[("http://x", "boom")])),
        ),
        pytest.raises(HomeAssistantError),
    ):
        await entity.async_reload_zones(SimpleNamespace(return_response=True))


async def test_update_state_invokes_update_location_when_attrs_present() -> None:
    entity = _make_entity()
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    entity._zones = [Zone(name="Home", geometry=polygon, priority=0)]

    async def aaej(func, *args):
        return func(*args)

    state = SimpleNamespace(
        state="home",
        attributes={"latitude": 0.5, "longitude": 0.5, "gps_accuracy": 5},
    )
    entity.hass = SimpleNamespace(
        states=SimpleNamespace(get=MagicMock(return_value=state)),
        async_add_executor_job=aaej,
    )

    with patch.object(PolygonalZoneEntity, "async_write_ha_state", lambda self: None):
        await entity._update_state()
    assert entity._attr_location_name == "Home"


async def test_update_state_skips_when_source_state_missing() -> None:
    """Source tracker doesn't exist → mirror goes unavailable, location_name preserved."""
    entity = _make_entity()
    entity._attr_available = True  # simulate healthy startup state
    entity.hass = SimpleNamespace(states=SimpleNamespace(get=MagicMock(return_value=None)))

    with patch.object(PolygonalZoneEntity, "async_write_ha_state", lambda self: None):
        await entity._update_state()
    assert entity._attr_location_name is None
    assert entity._attr_available is False


async def test_update_state_flips_unavailable_when_source_is_unavailable() -> None:
    """Source device reports state='unavailable' → mirror follows."""
    entity = _make_entity()
    entity._attr_available = True
    entity.hass = SimpleNamespace(
        states=SimpleNamespace(
            get=MagicMock(return_value=SimpleNamespace(state="unavailable", attributes={}))
        )
    )

    with patch.object(PolygonalZoneEntity, "async_write_ha_state", lambda self: None):
        await entity._update_state()
    assert entity._attr_available is False


async def test_update_state_flips_unavailable_when_source_is_unknown() -> None:
    """Source device reports state='unknown' → mirror follows."""
    entity = _make_entity()
    entity._attr_available = True
    entity.hass = SimpleNamespace(
        states=SimpleNamespace(
            get=MagicMock(return_value=SimpleNamespace(state="unknown", attributes={}))
        )
    )

    with patch.object(PolygonalZoneEntity, "async_write_ha_state", lambda self: None):
        await entity._update_state()
    assert entity._attr_available is False


async def test_update_state_stays_available_when_source_has_state_but_no_gps() -> None:
    """Wifi-only trackers post state without lat/lon between fixes.

    This is common — don't flip availability just because a single update
    lacks GPS attrs; the previous resolved zone remains the best estimate
    until the next fix arrives.
    """
    entity = _make_entity()
    entity._attr_available = True
    entity.hass = SimpleNamespace(
        states=SimpleNamespace(
            get=MagicMock(return_value=SimpleNamespace(state="home", attributes={}))
        )
    )

    with patch.object(PolygonalZoneEntity, "async_write_ha_state", lambda self: None):
        await entity._update_state()
    assert entity._attr_available is True


async def test_update_state_recovers_available_when_source_returns() -> None:
    """Mirror flipped to unavailable; next valid GPS update restores availability."""
    entity = _make_entity()
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    entity._zones = [Zone(name="Home", geometry=polygon, priority=0)]
    entity._attr_available = False  # previously flipped off

    async def aaej(func, *args):
        return func(*args)

    state = SimpleNamespace(
        state="home",
        attributes={"latitude": 0.5, "longitude": 0.5, "gps_accuracy": 5},
    )
    entity.hass = SimpleNamespace(
        states=SimpleNamespace(get=MagicMock(return_value=state)),
        async_add_executor_job=aaej,
    )

    with patch.object(PolygonalZoneEntity, "async_write_ha_state", lambda self: None):
        await entity._update_state()

    assert entity._attr_available is True
    assert entity._attr_location_name == "Home"
