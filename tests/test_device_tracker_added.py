"""Entity-level behaviour: source subscription, reload delegation, _update_state.

The zone load/retry/repair lifecycle now lives on ``ZoneSource`` and is tested in
``test_zone_source.py``; here we cover the thin mirror entity that reads from it.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
import pytest
from shapely.geometry import Polygon

from custom_components.polygonal_zones.device_tracker import PolygonalZoneEntity
from custom_components.polygonal_zones.utils.zones import Zone, ZoneLoadResult
from tests.helpers import make_entity as _make_entity
from tests.helpers import make_source


def _make_hass() -> SimpleNamespace:
    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        states=SimpleNamespace(get=MagicMock(return_value=None)),
        async_create_task=MagicMock(),
        async_add_executor_job=aaej,
    )


async def test_added_to_hass_tracks_only_its_source_entity() -> None:
    """The mirror subscribes to its specific source tracker via
    async_track_state_change_event — not a global state_changed bus listener."""
    entity = _make_entity()
    entity.hass = _make_hass()
    entity.async_get_last_state = AsyncMock(return_value=None)

    tracker = MagicMock(return_value=lambda: None)
    with patch(
        "custom_components.polygonal_zones.device_tracker.async_track_state_change_event",
        new=tracker,
    ):
        await entity.async_added_to_hass()

    tracker.assert_called_once()
    # Second positional arg is the list of entity_ids to watch.
    assert tracker.call_args.args[1] == ["device_tracker.phone"]


async def test_added_to_hass_registers_source_listener() -> None:
    """The mirror registers a reload listener so it re-resolves when zones reload."""
    source = make_source()
    entity = _make_entity(source=source)
    entity.hass = _make_hass()
    entity.async_get_last_state = AsyncMock(return_value=None)

    await entity.async_added_to_hass()

    assert len(source._listeners) == 1


async def test_source_reload_notifies_entity_to_update() -> None:
    """When the source notifies, the entity schedules a state re-resolve."""
    created = []
    hass = _make_hass()
    hass.async_create_task = created.append
    entity = _make_entity()
    entity.hass = hass
    entity._handle_source_reloaded()
    assert len(created) == 1
    created[0].close()  # close the scheduled coroutine (never awaited in the test)


async def test_reload_zones_service_all_uris_failed_raises() -> None:
    """reload_zones service delegating to the source that fails every URI →
    HomeAssistantError (not a silent no-op)."""
    entity = _make_entity()
    entity.hass = _make_hass()

    with (
        patch(
            "custom_components.polygonal_zones.zone_source.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=[], failures=[("http://x", "boom")])),
        ),
        patch("custom_components.polygonal_zones.zone_source.ir.async_delete_issue"),
        pytest.raises(HomeAssistantError),
    ):
        await entity.async_reload_zones(SimpleNamespace(return_response=True))


async def test_update_state_unavailable_when_source_not_loaded() -> None:
    """Zones not yet loaded (or load exhausted) → the mirror is unavailable."""
    entity = _make_entity(loaded_ok=False)
    entity._attr_available = True
    entity.hass = SimpleNamespace(states=SimpleNamespace(get=MagicMock(return_value=None)))

    with patch.object(PolygonalZoneEntity, "async_write_ha_state", lambda self: None):
        await entity._update_state()
    assert entity._attr_available is False


async def test_update_state_invokes_update_location_when_attrs_present() -> None:
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    entity = _make_entity(zones=[Zone(name="Home", geometry=polygon, priority=0)])

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
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    entity = _make_entity(zones=[Zone(name="Home", geometry=polygon, priority=0)])
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
