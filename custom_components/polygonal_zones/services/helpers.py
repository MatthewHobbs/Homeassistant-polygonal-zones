"""Helper functions for the services for the polygonal zones integration."""

import asyncio
import json
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

from ..const import DOMAIN
from ..device_tracker import PolygonalZoneEntity
from .errors import InvalidZoneData, RateLimited

_LOGGER = logging.getLogger(__name__)

MAX_ZONE_JSON_BYTES = 1_048_576
MAX_ZONE_NAME_LEN = 200
MAX_FEATURES_PER_COLLECTION = 500
# Total vertex count across every ring of every polygon in the collection.
# Caps event-loop stall time inside shapely.buffer()/.intersects() on each
# state_changed — a 1 MiB JSON file can otherwise encode ~50k vertices.
MAX_TOTAL_VERTICES_PER_COLLECTION = 10_000
SUPPORTED_GEOMETRY_TYPES = {"Polygon", "MultiPolygon"}
# Declared top-level feature property keys. Anything else is preserved through
# round-trip but logged at WARNING so drift is visible. New producer-specific
# fields belong under ``properties.polygonal_zones_ext``. See docs/ZONES_FORMAT.md.
KNOWN_FEATURE_PROPERTY_KEYS = frozenset({"name", "priority", "polygonal_zones_ext"})

# Minimum seconds between mutation-service calls for a single config entry.
# A low-privilege authenticated user can't wedge the event loop by spamming
# service calls; 2s is generous for human + automation use and catches runaway
# loops immediately.
MUTATION_MIN_INTERVAL_S = 2.0
_LAST_MUTATION_TIMESTAMP: dict[str, float] = {}


def reset_mutation_rate_limit() -> None:
    """Clear the mutation rate-limit timestamps. Intended for tests."""
    _LAST_MUTATION_TIMESTAMP.clear()


def enforce_mutation_rate_limit(
    entry_id: str, min_interval: float = MUTATION_MIN_INTERVAL_S
) -> None:
    """Raise ``RateLimited`` if this entry mutated within ``min_interval`` seconds.

    Keyed by ``entry_id`` rather than ``device_id`` because every entity under
    one entry shares the same on-disk file — allowing two devices in the same
    entry to mutate simultaneously would bypass the point of the gate.
    """
    now = time.monotonic()
    last = _LAST_MUTATION_TIMESTAMP.get(entry_id, 0.0)
    elapsed = now - last
    if elapsed < min_interval:
        raise RateLimited(
            f"Rate limit exceeded: wait {min_interval - elapsed:.1f}s before the "
            "next polygonal_zones mutation on this entry."
        )
    _LAST_MUTATION_TIMESTAMP[entry_id] = now


def audit_mutation_call(call: ServiceCall, service_name: str, entry_id: str) -> None:
    """Log every mutation invocation at INFO with the calling user_id.

    ``ServiceCall.context.user_id`` is the HA user that invoked the service.
    Automation / script / system invocations carry a ``None`` user_id; we
    surface that as ``<automation/system>`` so the audit trail still shows
    the origin.
    """
    context = getattr(call, "context", None)
    user_id = getattr(context, "user_id", None) if context is not None else None
    _LOGGER.info(
        "polygonal_zones.%s invoked by user=%s on entry=%s",
        service_name,
        user_id or "<automation/system>",
        entry_id,
    )


def _count_geometry_vertices(geometry: dict) -> int:
    """Sum the vertex count across every ring of a Polygon / MultiPolygon.

    Walks the ``coordinates`` tree instead of calling into shapely so the cap
    can be enforced before geometry construction, which is the expensive step
    we are trying to keep off the event loop.
    """
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list):
        return 0

    polygons = [coordinates] if geometry.get("type") == "Polygon" else coordinates

    total = 0
    for polygon in polygons:
        if not isinstance(polygon, list):
            continue
        for ring in polygon:
            if isinstance(ring, list):
                total += len(ring)
    return total


def _validate_feature(feature: object) -> None:
    """Validate a single GeoJSON Feature has the fields this integration needs."""
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise InvalidZoneData("Zone must be a GeoJSON Feature")
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise InvalidZoneData("Feature must have a properties object")
    name = properties.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InvalidZoneData("Feature must have a non-empty 'name' property")
    if len(name) > MAX_ZONE_NAME_LEN:
        raise InvalidZoneData(f"Zone name exceeds {MAX_ZONE_NAME_LEN} characters")
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise InvalidZoneData("Feature must have a geometry object")
    geom_type = geometry.get("type")
    if geom_type not in SUPPORTED_GEOMETRY_TYPES:
        raise InvalidZoneData(
            f"Unsupported geometry type {geom_type!r}; "
            f"expected one of {sorted(SUPPORTED_GEOMETRY_TYPES)}"
        )
    vertex_count = _count_geometry_vertices(geometry)
    if vertex_count > MAX_TOTAL_VERTICES_PER_COLLECTION:
        raise InvalidZoneData(
            f"Feature has {vertex_count} vertices; single-feature limit is "
            f"{MAX_TOTAL_VERTICES_PER_COLLECTION}"
        )
    unknown_keys = set(properties) - KNOWN_FEATURE_PROPERTY_KEYS
    if unknown_keys:
        _LOGGER.warning(
            "Zone feature %r carries unknown property keys %s; "
            "preserved but producers should move new fields under "
            "properties.polygonal_zones_ext (see docs/ZONES_FORMAT.md)",
            name,
            sorted(unknown_keys),
        )


def parse_zone_feature(raw: str | None) -> dict:
    """Parse a JSON string into a validated GeoJSON Feature dict."""
    if not raw:
        raise InvalidZoneData("Missing zone payload")
    if len(raw) > MAX_ZONE_JSON_BYTES:
        raise InvalidZoneData(f"Zone payload exceeds {MAX_ZONE_JSON_BYTES} bytes")
    try:
        feature = json.loads(raw)
    except (ValueError, RecursionError) as err:
        raise InvalidZoneData(f"Zone payload is not valid JSON: {err}") from err
    _validate_feature(feature)
    return feature


def parse_zone_collection(raw: str | None) -> dict:
    """Parse a JSON string into a validated GeoJSON FeatureCollection dict."""
    if not raw:
        raise InvalidZoneData("Missing zone payload")
    if len(raw) > MAX_ZONE_JSON_BYTES:
        raise InvalidZoneData(f"Zone payload exceeds {MAX_ZONE_JSON_BYTES} bytes")
    try:
        collection = json.loads(raw)
    except (ValueError, RecursionError) as err:
        raise InvalidZoneData(f"Zone payload is not valid JSON: {err}") from err
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise InvalidZoneData("Payload must be a GeoJSON FeatureCollection")
    features = collection.get("features")
    if not isinstance(features, list):
        raise InvalidZoneData("FeatureCollection must have a 'features' array")
    if len(features) > MAX_FEATURES_PER_COLLECTION:
        raise InvalidZoneData(
            f"FeatureCollection has {len(features)} features; limit is "
            f"{MAX_FEATURES_PER_COLLECTION}"
        )
    total_vertices = 0
    for feature in features:
        _validate_feature(feature)
        total_vertices += _count_geometry_vertices(feature["geometry"])
    if total_vertices > MAX_TOTAL_VERTICES_PER_COLLECTION:
        raise InvalidZoneData(
            f"FeatureCollection has {total_vertices} total vertices; limit is "
            f"{MAX_TOTAL_VERTICES_PER_COLLECTION}"
        )
    return collection


def require_device_id(call_data: dict) -> str:
    """Extract a device_id from a service call, raising on missing/empty input."""
    device_id = call_data.get("device_id")
    if not device_id:
        raise InvalidZoneData("Service call is missing 'device_id'")
    if isinstance(device_id, list):
        return device_id[0]
    return device_id


def get_zone_idx(name: str, existing_zones: dict[str, Any]) -> int | None:
    """Get the index of the zone in the features list of a GeoJSON dict.

    Args:
        name: The name to get the index of
        existing_zones: A GeoJSON dict of the existing zones to search in.

    Returns:
         int | None: the index if the name is found. otherwise None

    """
    for idx, zone in enumerate(existing_zones["features"]):
        if zone["properties"]["name"] == name:
            return idx
    return None


def zone_already_defined(name: str, existing_zones: dict[str, Any]) -> bool:
    """Check if a zone has already been defined.

    Args:
        name: The name of the zone to check for
        existing_zones: a GeoJSON dict of the existing zones to check in

    Returns:
         boolean: true if the zone already exists. false if it doesn't

    """
    return any(zone["properties"]["name"] == name for zone in existing_zones["features"])


async def sync_entities_after_write(entities: list[PolygonalZoneEntity]) -> None:
    """Refresh each entity's in-memory zone list after a successful disk write.

    Every entity under a single config entry shares the same local zone file,
    so a mutation service has to refresh them all — otherwise a device that
    moves between the write and the next manual ``reload_zones`` call would
    resolve against the stale in-memory list. ``async_reload_zones`` swallows
    per-entity exceptions, so ``gather`` never raises.
    """
    if not entities:
        return
    await asyncio.gather(*(e.async_reload_zones() for e in entities))


def get_entities_from_device_id(device_id: str, hass: HomeAssistant) -> list[PolygonalZoneEntity]:
    """Get the entities from the provided device_id via the entry's runtime_data."""
    device_entry = dr.async_get(hass)
    device = device_entry.async_get(device_id)
    if device is None:
        raise InvalidZoneData(f"Unknown device_id: {device_id}")
    entry_id = device.primary_config_entry
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
        raise InvalidZoneData(f"Device '{device_id}' is not registered to polygonal_zones")
    return entry.runtime_data.entities
