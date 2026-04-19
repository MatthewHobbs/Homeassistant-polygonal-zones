"""Tests for diagnostics.async_get_config_entry_diagnostics."""

from types import SimpleNamespace

from shapely.geometry import Polygon

from homeassistant.components.polygonal_zones import PolygonalZonesData
from homeassistant.components.polygonal_zones.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.components.polygonal_zones.utils.zones import Zone


async def test_diagnostics_redacts_identifying_lists() -> None:
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    fake_entity = SimpleNamespace(
        _attr_available=True,
        _editable_file=True,
        _zones=[Zone(name="Home", geometry=polygon, priority=0)],
        _zones_urls=["https://example.com/a.json"],
        _prioritize_zone_files=True,
    )
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="Polygonal Zones",
        version=1,
        runtime_data=PolygonalZonesData(entities=[fake_entity]),
        data={
            "zone_urls": ["https://example.com/a.json"],
            "entities": ["device_tracker.alice", "device_tracker.bob"],
            "prioritize_zone_files": True,
            "download_zones": False,
        },
    )

    result = await async_get_config_entry_diagnostics(SimpleNamespace(), entry)

    assert result["entry"]["title"] == "Polygonal Zones"
    assert result["entry"]["data"]["entities"] == ["<redacted-0>", "<redacted-1>"]
    assert result["entry"]["data"]["zone_urls"] == ["<redacted-0>"]
    assert result["entry"]["data"]["prioritize_zone_files"] is True
    assert result["entities"][0]["available"] is True
    assert result["entities"][0]["zone_count"] == 1


async def test_diagnostics_with_no_entities() -> None:
    entry = SimpleNamespace(
        entry_id="entry-2",
        title="Polygonal Zones",
        version=1,
        runtime_data=PolygonalZonesData(),
        data={"zone_urls": [], "entities": []},
    )
    result = await async_get_config_entry_diagnostics(SimpleNamespace(), entry)
    assert result["entities"] == []


async def test_diagnostics_when_runtime_data_missing() -> None:
    """Defensive: an entry without runtime_data still produces a sensible report."""
    entry = SimpleNamespace(
        entry_id="entry-3",
        title="Polygonal Zones",
        version=1,
        data={"zone_urls": [], "entities": []},
    )
    result = await async_get_config_entry_diagnostics(SimpleNamespace(), entry)
    assert result["entities"] == []


async def test_diagnostics_redacts_non_list_values() -> None:
    """The _redact helper handles scalar values too (defensive against schema drift)."""
    from homeassistant.components.polygonal_zones.diagnostics import _redact

    assert _redact("secret") == "<redacted>"
    assert _redact(["a", "b"]) == ["<redacted-0>", "<redacted-1>"]
