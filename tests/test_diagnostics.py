"""Tests for diagnostics.async_get_config_entry_diagnostics."""

from types import SimpleNamespace

import pandas as pd
from shapely.geometry import Polygon

from custom_components.polygonal_zones.const import DOMAIN
from custom_components.polygonal_zones.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics_redacts_identifying_lists() -> None:
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    fake_entity = SimpleNamespace(
        _attr_available=True,
        _editable_file=True,
        _zones=pd.DataFrame([{"name": "Home", "priority": 0, "geometry": polygon}]),
        _zones_urls=["https://example.com/a.json"],
        _prioritize_zone_files=True,
    )
    hass = SimpleNamespace(data={DOMAIN: {"entry-1": [fake_entity]}})
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="Polygonal Zones",
        version=1,
        data={
            "zone_urls": ["https://example.com/a.json"],
            "entities": ["device_tracker.alice", "device_tracker.bob"],
            "prioritize_zone_files": True,
            "download_zones": False,
        },
    )

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry"]["title"] == "Polygonal Zones"
    assert result["entry"]["data"]["entities"] == ["<redacted-0>", "<redacted-1>"]
    assert result["entry"]["data"]["zone_urls"] == ["<redacted-0>"]
    assert result["entry"]["data"]["prioritize_zone_files"] is True
    assert result["entities"][0]["available"] is True
    assert result["entities"][0]["zone_count"] == 1


async def test_diagnostics_with_no_entities() -> None:
    hass = SimpleNamespace(data={DOMAIN: {}})
    entry = SimpleNamespace(
        entry_id="entry-2",
        title="Polygonal Zones",
        version=1,
        data={"zone_urls": [], "entities": []},
    )
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["entities"] == []


async def test_diagnostics_redacts_non_list_values() -> None:
    """The _redact helper handles scalar values too (defensive against schema drift)."""
    from custom_components.polygonal_zones.diagnostics import _redact

    assert _redact("secret") == "<redacted>"
    assert _redact(["a", "b"]) == ["<redacted-0>", "<redacted-1>"]
