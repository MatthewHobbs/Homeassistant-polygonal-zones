"""Test 10 — PolygonalZoneEntity restores state on restart."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from tests.helpers import make_entity as _make_entity


async def test_state_restored_on_restart() -> None:
    """``async_added_to_hass`` populates the entity from the previous saved state."""
    entity = _make_entity()

    last_state = SimpleNamespace(
        state="Home",
        attributes={
            "latitude": 51.5,
            "longitude": -0.1,
            "gps_accuracy": 5,
            "source_entity": "device_tracker.phone",
        },
    )
    entity.async_get_last_state = AsyncMock(return_value=last_state)
    entity.hass = SimpleNamespace()

    await entity.async_added_to_hass()

    assert entity._attr_location_name == "Home"
    assert entity._attr_extra_state_attributes == last_state.attributes


async def test_no_previous_state_leaves_attrs_unset() -> None:
    """If nothing was persisted, the entity stays in its default unknown state."""
    entity = _make_entity()
    entity.async_get_last_state = AsyncMock(return_value=None)
    entity.hass = SimpleNamespace()

    await entity.async_added_to_hass()

    assert entity._attr_location_name is None


async def test_restore_strips_gated_attrs_when_expose_off() -> None:
    """A user who turned coordinates off must not get lat/lon (or the other gated
    attrs) re-published from restore state."""
    entity = _make_entity(expose_coordinates=False)
    last_state = SimpleNamespace(
        state="Home",
        attributes={
            "latitude": 51.5,
            "longitude": -0.1,
            "gps_accuracy": 5,
            "zone_uris": ["https://x/z.json"],
            "matched_zones": ["Home"],
            "source_entity": "device_tracker.phone",
            "last_load_result": "ok",
        },
    )
    entity.async_get_last_state = AsyncMock(return_value=last_state)
    entity.hass = SimpleNamespace()

    await entity.async_added_to_hass()

    attrs = entity._attr_extra_state_attributes
    for gated in ("latitude", "longitude", "gps_accuracy", "zone_uris", "matched_zones"):
        assert gated not in attrs
    # Non-location diagnostics survive the restore.
    assert attrs["source_entity"] == "device_tracker.phone"
    assert attrs["last_load_result"] == "ok"
