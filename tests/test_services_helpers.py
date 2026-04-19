"""Tests for services.helpers — get_entities_from_device_id branches."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.polygonal_zones.const import DOMAIN
from custom_components.polygonal_zones.services.errors import InvalidZoneData
from custom_components.polygonal_zones.services.helpers import (
    get_entities_from_device_id,
    get_zone_idx,
    require_device_id,
    sync_entities_after_write,
)


def test_require_device_id_string() -> None:
    assert require_device_id({"device_id": "abc"}) == "abc"


def test_require_device_id_list() -> None:
    assert require_device_id({"device_id": ["abc", "def"]}) == "abc"


def test_require_device_id_missing_raises() -> None:
    with pytest.raises(InvalidZoneData):
        require_device_id({})


def test_require_device_id_empty_list_raises() -> None:
    with pytest.raises(InvalidZoneData):
        require_device_id({"device_id": []})


def test_get_zone_idx_finds_existing() -> None:
    zones = {
        "features": [
            {"properties": {"name": "Home"}},
            {"properties": {"name": "Work"}},
        ]
    }
    assert get_zone_idx("Work", zones) == 1


def test_get_zone_idx_missing_returns_none() -> None:
    zones = {"features": [{"properties": {"name": "Home"}}]}
    assert get_zone_idx("Other", zones) is None


def test_get_entities_from_device_id_unknown_device() -> None:
    """An unrecognised device_id surfaces as InvalidZoneData."""
    fake_registry = SimpleNamespace(async_get=lambda _id: None)
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_entry=lambda _eid: None),
    )

    with (
        patch(
            "custom_components.polygonal_zones.services.helpers.dr.async_get",
            return_value=fake_registry,
        ),
        pytest.raises(InvalidZoneData),
    ):
        get_entities_from_device_id("ghost-id", hass)


def test_get_entities_from_device_id_unregistered_entry() -> None:
    """Device exists but its entry isn't in our integration (different domain)."""
    fake_device = SimpleNamespace(primary_config_entry="other-entry")
    fake_registry = SimpleNamespace(async_get=lambda _id: fake_device)
    other_entry = SimpleNamespace(domain="some_other_domain")
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_entry=lambda _eid: other_entry),
    )

    with (
        patch(
            "custom_components.polygonal_zones.services.helpers.dr.async_get",
            return_value=fake_registry,
        ),
        pytest.raises(InvalidZoneData),
    ):
        get_entities_from_device_id("device-id", hass)


def test_get_entities_from_device_id_happy_path() -> None:
    from custom_components.polygonal_zones import PolygonalZonesData

    fake_device = SimpleNamespace(primary_config_entry="entry-1")
    fake_registry = SimpleNamespace(async_get=lambda _id: fake_device)
    fake_entity = SimpleNamespace()
    fake_entry = SimpleNamespace(
        domain=DOMAIN, runtime_data=PolygonalZonesData(entities=[fake_entity])
    )
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_entry=lambda _eid: fake_entry),
    )

    with patch(
        "custom_components.polygonal_zones.services.helpers.dr.async_get",
        return_value=fake_registry,
    ):
        entities = get_entities_from_device_id("device-id", hass)
        assert entities == [fake_entity]


async def test_sync_entities_after_write_calls_reload_on_each() -> None:
    """Every entity under a single entry must be re-synced after a mutation write."""
    a = SimpleNamespace(async_reload_zones=AsyncMock())
    b = SimpleNamespace(async_reload_zones=AsyncMock())

    await sync_entities_after_write([a, b])

    a.async_reload_zones.assert_awaited_once_with()
    b.async_reload_zones.assert_awaited_once_with()


async def test_sync_entities_after_write_empty_list_is_noop() -> None:
    """An empty entity list is a clean no-op, not an error."""
    await sync_entities_after_write([])
