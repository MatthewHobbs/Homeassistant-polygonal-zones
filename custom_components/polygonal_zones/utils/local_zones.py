"""Helper functions to handle local zones."""

import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from shapely import to_geojson

from ..const import SCHEMA_VERSION
from .zones import Zone, get_zones

_FILE_LOCKS: dict[str, asyncio.Lock] = {}

LOCK_ACQUIRE_TIMEOUT = 15  # seconds


def get_file_lock(path: Path) -> asyncio.Lock:
    """Return a shared ``asyncio.Lock`` keyed by the absolute path.

    Used to serialize read-modify-write service calls against the same
    zone file so two concurrent callers can't lose each other's changes.
    """
    key = str(path)
    lock = _FILE_LOCKS.get(key)
    if lock is None:
        lock = _FILE_LOCKS[key] = asyncio.Lock()
    return lock


def release_file_lock(path: Path) -> None:
    """Drop the cached ``asyncio.Lock`` for ``path`` if one exists.

    Called from ``async_unload_entry`` so locks don't accumulate forever
    across config-entry reloads in long-running HA instances.
    """
    _FILE_LOCKS.pop(str(path), None)


def dump_feature_collection(
    features: list[dict[str, Any]], existing: dict[str, Any] | None = None
) -> str:
    """Serialize a FeatureCollection JSON string, stamped with the current schema_version.

    When ``existing`` is supplied (read-modify-write flow), non-standard top-level
    keys and any unrelated ``polygonal_zones.*`` members are preserved; only
    ``schema_version`` is (re-)written to :data:`SCHEMA_VERSION`.
    """
    collection: dict[str, Any] = {"type": "FeatureCollection"}
    if existing:
        for key, value in existing.items():
            if key in ("type", "features", "polygonal_zones"):
                continue
            collection[key] = value
        existing_pz = existing.get("polygonal_zones")
        preserved_pz = existing_pz if isinstance(existing_pz, dict) else {}
        collection["polygonal_zones"] = {**preserved_pz, "schema_version": SCHEMA_VERSION}
    else:
        collection["polygonal_zones"] = {"schema_version": SCHEMA_VERSION}
    collection["features"] = features
    return json.dumps(collection)


def zones_to_geojson(zones: list[Zone]) -> str:
    """Convert a list of ``Zone`` objects back into a GeoJSON string."""
    features = [
        {
            "type": "Feature",
            "properties": {
                "name": zone.name,
                "priority": zone.priority,
            },
            "geometry": json.loads(to_geojson(zone.geometry)),
        }
        for zone in zones
    ]
    return dump_feature_collection(features)


async def download_zones(
    source_uris: list[str], dest_uri: Path, prioritize: bool, hass: HomeAssistant
) -> None:
    """Download the zones in sources_uris to."""
    zones = await get_zones(source_uris, hass, prioritize)
    geo_json = zones_to_geojson(zones)

    await save_zones(geo_json, dest_uri, hass)


async def save_zones(geojson: str, destination: Path, hass: HomeAssistant) -> None:
    """Save the GeoJSON string to a file atomically.

    Writes to a sibling ``.tmp`` file and ``os.replace``s it into place so a
    crash mid-write cannot corrupt the destination. The parent directory is
    created with restrictive permissions; the file is written 0600.
    """

    def _write() -> None:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(geojson)
            os.replace(tmp, destination)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
            raise

    await hass.async_add_executor_job(_write)
