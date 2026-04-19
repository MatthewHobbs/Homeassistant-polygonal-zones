"""Test 10 — PolygonalZoneEntity restores state on restart."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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

    bus = SimpleNamespace(async_listen=MagicMock(return_value=lambda: None))
    entity.hass = SimpleNamespace(bus=bus)

    with patch(
        "custom_components.polygonal_zones.device_tracker.async_at_started",
        return_value=lambda: None,
    ):
        await entity.async_added_to_hass()

    assert entity._attr_location_name == "Home"
    assert entity._attr_extra_state_attributes == last_state.attributes


async def test_no_previous_state_leaves_attrs_unset() -> None:
    """If nothing was persisted, the entity stays in its default unknown state."""
    entity = _make_entity()
    entity.async_get_last_state = AsyncMock(return_value=None)

    bus = SimpleNamespace(async_listen=MagicMock(return_value=lambda: None))
    entity.hass = SimpleNamespace(bus=bus)

    with patch(
        "custom_components.polygonal_zones.device_tracker.async_at_started",
        return_value=lambda: None,
    ):
        await entity.async_added_to_hass()

    assert entity._attr_location_name is None
