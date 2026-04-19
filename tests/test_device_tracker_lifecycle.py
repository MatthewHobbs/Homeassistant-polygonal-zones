"""Lifecycle tests for PolygonalZoneEntity beyond restore-on-restart."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from shapely.geometry import Polygon

from custom_components.polygonal_zones.device_tracker import PolygonalZoneEntity
from custom_components.polygonal_zones.utils.zones import Zone


def _make_entity(zone_urls=None) -> PolygonalZoneEntity:
    return PolygonalZoneEntity(
        tracked_entity_id="device_tracker.phone",
        config_entry_id="entry-id",
        zone_urls=zone_urls or ["https://example.com/zones.json"],
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


async def test_set_available_logs_only_on_transition() -> None:
    entity = _make_entity()
    # Default _attr_available is True; first call to _set_available(True) is a no-op
    entity._set_available(True)
    entity._set_available(False)
    assert entity._attr_available is False
    entity._set_available(True)
    assert entity._attr_available is True


async def test_will_remove_releases_all_unsubs() -> None:
    entity = _make_entity()
    # Pre-populate the unsub handles with mocks
    entity._unsub = MagicMock()
    entity._unsub_at_started = MagicMock()
    entity._unsub_retry = MagicMock()

    await entity.async_will_remove_from_hass()

    assert entity._unsub is None
    assert entity._unsub_at_started is None
    assert entity._unsub_retry is None


async def test_update_location_sets_attributes() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._zones = [
        Zone(name="Home", geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), priority=0)
    ]

    await entity.update_location(latitude=0.5, longitude=0.5, gps_accuracy=10)

    assert entity._attr_location_name == "Home"
    assert entity._attr_extra_state_attributes["latitude"] == 0.5
    assert entity._attr_extra_state_attributes["longitude"] == 0.5
    assert entity._attr_extra_state_attributes["gps_accuracy"] == 10


async def test_update_location_outside_zones_marks_away() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._zones = [
        Zone(name="Home", geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), priority=0)
    ]
    await entity.update_location(latitude=10, longitude=10, gps_accuracy=1)
    assert entity._attr_location_name == "away"


async def test_async_reload_zones_returns_payload_when_requested() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._async_write_ha_state = MagicMock()

    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    zones = [Zone(name="Home", geometry=polygon, priority=0)]

    call = SimpleNamespace(return_response=True)
    with patch(
        "custom_components.polygonal_zones.device_tracker.get_zones",
        new=AsyncMock(return_value=zones),
    ):
        result = await entity.async_reload_zones(call)

    assert isinstance(result, list)
    assert result[0]["name"] == "Home"
    # geometry is a list of (lon,lat) tuples
    assert isinstance(result[0]["geometry"], list)


async def test_async_reload_zones_empty_returns_empty_list() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._async_write_ha_state = MagicMock()

    call = SimpleNamespace(return_response=True)
    with patch(
        "custom_components.polygonal_zones.device_tracker.get_zones",
        new=AsyncMock(return_value=[]),
    ):
        result = await entity.async_reload_zones(call)

    assert result == []


async def test_async_reload_zones_returns_none_when_response_not_requested() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._async_write_ha_state = MagicMock()

    call = SimpleNamespace(return_response=False)
    with patch(
        "custom_components.polygonal_zones.device_tracker.get_zones",
        new=AsyncMock(return_value=[]),
    ):
        result = await entity.async_reload_zones(call)

    assert result is None


async def test_async_reload_zones_handles_failure() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()

    call = SimpleNamespace(return_response=False)
    with patch(
        "custom_components.polygonal_zones.device_tracker.get_zones",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await entity.async_reload_zones(call)

    assert result is None


async def test_async_reload_zones_accepts_no_call() -> None:
    """Callable with ``call=None`` from the mutation-service path — no response."""
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._async_write_ha_state = MagicMock()

    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    zones = [Zone(name="Home", geometry=polygon, priority=0)]

    with patch(
        "custom_components.polygonal_zones.device_tracker.get_zones",
        new=AsyncMock(return_value=zones),
    ):
        result = await entity.async_reload_zones()

    assert result is None
    assert entity._zones == zones
