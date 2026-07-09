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
