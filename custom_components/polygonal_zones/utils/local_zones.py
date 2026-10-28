"""Helper functions to handle local zones."""

import contextlib
import json
import logging
import math
import os
from pathlib import Path
import threading
from typing import Any

from homeassistant.core import HomeAssistant
from shapely import to_geojson

from ..const import SCHEMA_VERSION
from .zones import Zone, get_zones

_LOGGER = logging.getLogger(__name__)

_FILE_LOCKS: dict[str, threading.Lock] = {}
_FILE_LOCKS_GUARD = threading.Lock()


def _lock_timeout() -> float:
    """Seconds to wait on the per-file lock before a mutation service aborts.

    ``POLYGONAL_ZONES_LOCK_ACQUIRE_TIMEOUT`` in the HA process environment
    overrides the default 15 (useful for NFS-mounted /config or SD-card
    Raspberry Pi setups where a single flush can push past it). A value that is
    not a positive number is ignored with a warning instead of failing the
    import of the whole integration.
    """
    raw = os.environ.get("POLYGONAL_ZONES_LOCK_ACQUIRE_TIMEOUT")
    if raw is None:
        return 15
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if not (math.isfinite(value) and value > 0):
        _LOGGER.warning(
            "Ignoring POLYGONAL_ZONES_LOCK_ACQUIRE_TIMEOUT=%r: not a positive number; using 15",
            raw,
        )
        return 15
    return value


LOCK_ACQUIRE_TIMEOUT = _lock_timeout()


def file_lock(path: Path) -> threading.Lock:
    """The shared thread lock for ``path``, created on first use.

    A thread lock, not an asyncio one: the whole read-modify-write runs in one
    executor job, and an executor write cannot be cancelled. An asyncio lock is
    released when its caller is cancelled, which let the next mutation read the
    pre-write file and erase the first.
    """
    with _FILE_LOCKS_GUARD:
        return _FILE_LOCKS.setdefault(str(path), threading.Lock())


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
    """Convert a list of ``Zone`` objects back into a GeoJSON string.

    Preserves every key stored on ``Zone.properties`` so round-tripping (parse
    → serialize) doesn't silently drop producer-specific fields such as
    ``polygonal_zones_ext.*``. ``name`` and ``priority`` are written last so
    the authoritative dataclass values override any stale copies sitting in
    ``zone.properties``.
    """
    features = [
        {
            "type": "Feature",
            "properties": {
                **zone.properties,
                "name": zone.name,
                "priority": zone.priority,
            },
            "geometry": json.loads(to_geojson(zone.geometry)),
        }
        for zone in zones
    ]
    return dump_feature_collection(features)


async def download_zones(
    source_uris: list[str],
    dest_uri: Path,
    prioritize: bool,
    hass: HomeAssistant,
    *,
    allow_private_urls: bool = False,
    token: str | None = None,
    trusted_host: str | bool = False,
) -> None:
    """Download the zones in sources_uris to."""
    zones = await get_zones(
        source_uris,
        hass,
        prioritize,
        allow_private_urls=allow_private_urls,
        token=token,
        trusted_host=trusted_host,
    )
    geo_json = zones_to_geojson(zones)

    await save_zones(geo_json, dest_uri, hass)


async def save_zones(geojson: str, destination: Path, hass: HomeAssistant) -> None:
    """Save the GeoJSON string to a file atomically, off the event loop."""
    await hass.async_add_executor_job(write_zones, geojson, destination)


def write_zones(geojson: str, destination: Path) -> None:
    """Save the GeoJSON string atomically. Sync: callers hold the file lock.

    Writes to a sibling ``.tmp`` file and ``os.replace``s it into place so a
    crash mid-write cannot corrupt the destination. The parent directory is
    created with restrictive permissions; the file is written 0600.
    """
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Symlink hardening (CWE-59): /config write access would let an attacker
    # pre-plant a symlink and redirect this write. Refuse a symlinked
    # destination rather than silently clobbering, and open the .tmp with
    # O_NOFOLLOW so a planted temp path fails instead of being followed.
    if destination.is_symlink():
        raise OSError(f"Refusing to write zones: {destination} is a symlink")
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    # os.open, not Path.write_text: it applies the 0o600 mode atomically, with
    # no chmod follow-up window where the file is world-readable. O_NOFOLLOW
    # fails (ELOOP) on a pre-planted symlink at tmp.
    fd = os.open(
        tmp,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(geojson)
            # Flush-to-disk before the rename so a host power loss between
            # write() and replace() can't leave us with an empty file.
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(destination)
        # Sync the directory entry too — the rename is durable only once
        # the parent's fsync completes. Harmless on filesystems that
        # don't require it (HFS+, APFS).
        with contextlib.suppress(OSError):
            dir_fd = os.open(destination.parent, os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise
