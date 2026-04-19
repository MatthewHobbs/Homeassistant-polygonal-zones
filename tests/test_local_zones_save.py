"""Coverage for utils.local_zones save_zones, download_zones, release_file_lock."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from shapely.geometry import Polygon

from custom_components.polygonal_zones.const import SCHEMA_VERSION
from custom_components.polygonal_zones.utils.local_zones import (
    download_zones,
    dump_feature_collection,
    get_file_lock,
    release_file_lock,
    save_zones,
    zones_to_geojson,
)
from custom_components.polygonal_zones.utils.zones import Zone


def _hass(tmp_path) -> SimpleNamespace:
    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=aaej,
    )


async def test_save_zones_writes_atomically(tmp_path) -> None:
    target = tmp_path / "polygonal_zones" / "out.json"
    await save_zones('{"hello": true}', target, _hass(tmp_path))

    assert target.exists()
    assert target.read_text() == '{"hello": true}'
    # tmp file cleaned up
    assert not target.with_suffix(".json.tmp").exists()


async def test_save_zones_cleans_up_tmp_on_failure(tmp_path) -> None:
    target = tmp_path / "polygonal_zones" / "out.json"
    target.parent.mkdir(parents=True)

    # Patch os.replace to raise mid-write so the cleanup branch fires
    with (
        patch(
            "custom_components.polygonal_zones.utils.local_zones.os.replace",
            side_effect=OSError("device gone"),
        ),
        pytest.raises(OSError),
    ):
        await save_zones('{"x": 1}', target, _hass(tmp_path))

    # tmp must be cleaned up by the suppress(FileNotFoundError) branch
    assert not target.with_suffix(".json.tmp").exists()


def test_zones_to_geojson_roundtrip() -> None:
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    df = [Zone(name="Home", geometry=polygon, priority=0)]
    raw = zones_to_geojson(df)
    parsed = json.loads(raw)
    assert parsed["type"] == "FeatureCollection"
    assert parsed["features"][0]["properties"]["name"] == "Home"


def test_zones_to_geojson_stamps_schema_version() -> None:
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    raw = zones_to_geojson([Zone(name="Home", geometry=polygon)])
    parsed = json.loads(raw)
    assert parsed["polygonal_zones"] == {"schema_version": SCHEMA_VERSION}


def test_zones_to_geojson_preserves_extra_properties() -> None:
    """Unknown property keys and the polygonal_zones_ext namespace survive round-trip."""
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    zone = Zone(
        name="Home",
        geometry=polygon,
        priority=1,
        properties={
            "name": "Home",
            "priority": 1,
            "description": "kept me out of the party",
            "polygonal_zones_ext": {"color": "#3366ff", "editor_version": "2.1"},
        },
    )
    raw = zones_to_geojson([zone])
    props = json.loads(raw)["features"][0]["properties"]
    assert props["description"] == "kept me out of the party"
    assert props["polygonal_zones_ext"] == {"color": "#3366ff", "editor_version": "2.1"}


def test_zones_to_geojson_dataclass_values_override_stale_properties() -> None:
    """``Zone.name`` and ``Zone.priority`` are authoritative; stale copies in ``properties`` lose."""
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    zone = Zone(
        name="Renamed",
        geometry=polygon,
        priority=5,
        properties={"name": "OldName", "priority": 0, "extra": "keep"},
    )
    props = json.loads(zones_to_geojson([zone]))["features"][0]["properties"]
    assert props["name"] == "Renamed"
    assert props["priority"] == 5
    assert props["extra"] == "keep"


def test_zones_to_geojson_empty_properties_still_emits_name_and_priority() -> None:
    """A hand-built Zone with no ``properties`` dict still produces valid output."""
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    zone = Zone(name="Solo", geometry=polygon)
    props = json.loads(zones_to_geojson([zone]))["features"][0]["properties"]
    assert props == {"name": "Solo", "priority": 0}


def test_dump_feature_collection_stamps_schema_version_without_existing() -> None:
    raw = dump_feature_collection([])
    parsed = json.loads(raw)
    assert parsed["type"] == "FeatureCollection"
    assert parsed["polygonal_zones"]["schema_version"] == SCHEMA_VERSION
    assert parsed["features"] == []


def test_dump_feature_collection_preserves_foreign_members() -> None:
    """Non-standard top-level keys and unrelated polygonal_zones.* keys pass through."""
    existing = {
        "type": "FeatureCollection",
        "polygonal_zones": {"schema_version": 1, "editor": "addon"},
        "bbox": [-1, -1, 1, 1],
        "features": [],
    }
    raw = dump_feature_collection([], existing=existing)
    parsed = json.loads(raw)
    assert parsed["bbox"] == [-1, -1, 1, 1]
    assert parsed["polygonal_zones"]["editor"] == "addon"
    assert parsed["polygonal_zones"]["schema_version"] == SCHEMA_VERSION


async def test_download_zones_writes_to_destination(tmp_path) -> None:
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    df = [Zone(name="Home", geometry=polygon, priority=0)]
    dest = tmp_path / "out.json"

    with patch(
        "custom_components.polygonal_zones.utils.local_zones.get_zones",
        new=AsyncMock(return_value=df),
    ):
        await download_zones(["http://x"], dest, False, _hass(tmp_path))

    parsed = json.loads(dest.read_text())
    assert parsed["features"][0]["properties"]["name"] == "Home"


def test_release_file_lock_on_unknown_path_is_noop(tmp_path) -> None:
    """Releasing a path that was never locked must not raise."""
    release_file_lock(tmp_path / "never-locked.json")


def test_get_file_lock_returns_same_instance() -> None:
    """Repeat calls for the same path return the same Lock object."""

    async def _go():
        path = Path("/tmp/test-zones.json")
        a = get_file_lock(path)
        b = get_file_lock(path)
        assert a is b

    asyncio.run(_go())
