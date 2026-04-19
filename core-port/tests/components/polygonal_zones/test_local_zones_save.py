"""Coverage for utils.local_zones save_zones, download_zones, release_file_lock."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from shapely.geometry import Polygon

from homeassistant.components.polygonal_zones.utils.local_zones import (
    download_zones,
    get_file_lock,
    release_file_lock,
    save_zones,
    zones_to_geojson,
)
from homeassistant.components.polygonal_zones.utils.zones import Zone


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
            "homeassistant.components.polygonal_zones.utils.local_zones.os.replace",
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


async def test_download_zones_writes_to_destination(tmp_path) -> None:
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    df = [Zone(name="Home", geometry=polygon, priority=0)]
    dest = tmp_path / "out.json"

    with patch(
        "homeassistant.components.polygonal_zones.utils.local_zones.get_zones",
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
