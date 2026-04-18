"""Helper functions to handle local zones."""

import asyncio
import contextlib
import json
import os
from pathlib import Path

from homeassistant.core import HomeAssistant
import pandas as pd
from shapely import to_geojson

from .zones import get_zones

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


def zones_to_geojson(zones: pd.DataFrame) -> str:
    """Convert the zones to GeoJSON."""
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "name": zone.name,
                        "priority": zone.priority,
                    },
                    "geometry": json.loads(to_geojson(zone.geometry)),
                }
                for zone in zones.itertuples()
            ],
        }
    )


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
