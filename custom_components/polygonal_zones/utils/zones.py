"""Zone-related utility functions for the polygonal_zones integration."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from shapely.errors import GEOSException
from shapely.geometry import Point, shape
from shapely.geometry.polygon import Polygon

from ..const import MAX_SUPPORTED_SCHEMA_VERSION
from .general import load_data
from .geometry import (
    get_distance_to_centroid,
    get_distance_to_exterior_points,
    haversine_distances,
)

# Re-exported for back-compat with call sites / tests that imported from zones.
__all__ = [
    "UnsupportedSchemaVersion",
    "Zone",
    "ZoneFileCorrupt",
    "ZoneLoadResult",
    "get_distance_to_centroid",
    "get_distance_to_exterior_points",
    "get_locations_zone",
    "get_zones",
    "haversine_distances",
    "load_zones",
]

_LOGGER = logging.getLogger(__name__)


class UnsupportedSchemaVersion(ValueError):
    """Raised when a zone file declares a schema_version this integration can't read."""


class ZoneFileCorrupt(ValueError):
    """Raised when a zone file can be fetched/parsed as JSON but fails structural checks.

    Covers: top-level not a FeatureCollection, ``features`` missing or not a list,
    a feature missing ``geometry`` / ``properties`` / ``properties.name``, or an
    unparseable geometry.
    """


@dataclass
class Zone:
    """A single named polygonal zone with optional priority + extra properties."""

    name: str
    geometry: Polygon
    priority: int = 0
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class ZoneLoadResult:
    """Outcome of a multi-URI zone load.

    ``zones`` is the union of every feature successfully parsed.
    ``failures`` records per-URI failures as ``(uri, message)`` tuples; callers
    that want graceful degradation use it to surface the failure list in
    diagnostics without aborting the whole load.
    """

    zones: list[Zone] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)


def _parse_feature(feature: Any, default_priority: int) -> Zone:
    """Validate a single GeoJSON Feature and convert it to a ``Zone``.

    Raises ``ZoneFileCorrupt`` with an actionable message when any expected
    field is missing or malformed, so callers get a typed failure instead of
    a raw KeyError/TypeError escaping from deep inside the parse loop.
    """
    if not isinstance(feature, dict):
        raise ZoneFileCorrupt("feature is not an object")
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise ZoneFileCorrupt("feature has no 'properties' object")
    name = properties.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ZoneFileCorrupt("feature 'properties.name' is missing or not a non-empty string")
    geometry_data = feature.get("geometry")
    if not isinstance(geometry_data, dict):
        raise ZoneFileCorrupt(f"feature {name!r} has no 'geometry' object")

    if "priority" in properties:
        raw_priority = properties["priority"]
        if not isinstance(raw_priority, int | str):
            raise ZoneFileCorrupt(
                f"feature {name!r} has non-integer priority of type {type(raw_priority).__name__}"
            )
        try:
            priority = int(raw_priority)
        except (TypeError, ValueError) as err:
            raise ZoneFileCorrupt(
                f"feature {name!r} has non-integer priority {raw_priority!r}"
            ) from err
    else:
        priority = default_priority

    try:
        geometry = shape(geometry_data)
    except (GEOSException, TypeError, ValueError, KeyError) as err:
        raise ZoneFileCorrupt(f"feature {name!r} has unparseable geometry: {err}") from err

    return Zone(
        name=name,
        geometry=geometry,
        priority=priority,
        properties=dict(properties),
    )


async def _load_zones_from_uri(
    uri: str,
    idx: int,
    prioritize: bool,
    hass: HomeAssistant,
    *,
    allow_private_urls: bool = False,
) -> list[Zone]:
    """Load and parse one zone file. Returns a list of zones or raises a typed error."""
    raw = await load_data(uri, hass, allow_private_urls=allow_private_urls)
    try:
        data = json.loads(raw)
    except ValueError as err:
        raise ZoneFileCorrupt(f"not valid JSON: {err}") from err
    if not isinstance(data, dict):
        raise ZoneFileCorrupt("top-level payload is not an object")

    pz = data.get("polygonal_zones")
    if isinstance(pz, dict):
        declared_version = pz.get("schema_version", 1)
        if isinstance(declared_version, int) and declared_version > MAX_SUPPORTED_SCHEMA_VERSION:
            raise UnsupportedSchemaVersion(
                f"Zone file {uri!r} declares schema_version={declared_version}; "
                f"this integration supports up to {MAX_SUPPORTED_SCHEMA_VERSION}. "
                "See docs/ZONES_FORMAT.md."
            )

    features = data.get("features")
    if not isinstance(features, list):
        raise ZoneFileCorrupt("'features' is missing or not a list")

    default_priority = idx if prioritize else 0
    return [_parse_feature(feature, default_priority) for feature in features]


async def load_zones(
    uris: list[str],
    hass: HomeAssistant,
    prioritize: bool,
    *,
    allow_private_urls: bool = False,
) -> ZoneLoadResult:
    """Load every URI independently; return successes plus per-URI failure records.

    Partial-success semantics: one flaky URI no longer kills the whole load.
    Each URI's failure is logged at WARNING with a stacktrace and recorded on the
    returned result, so the entity can still resolve zones from healthy sources
    and the failing sources can be surfaced in diagnostics.

    ``allow_private_urls`` relaxes the SSRF resolver for RFC-1918 / ULA
    addresses so a user can point the integration at a LAN-installed source.
    """
    result = ZoneLoadResult()
    for idx, uri in enumerate(uris):
        try:
            result.zones.extend(
                await _load_zones_from_uri(
                    uri, idx, prioritize, hass, allow_private_urls=allow_private_urls
                )
            )
        except UnsupportedSchemaVersion:
            # Schema-version mismatch means the file format is ahead of this
            # integration. Propagate as a hard error so the user sees it clearly
            # instead of silently skipping the file.
            raise
        except Exception as err:
            _LOGGER.warning("Failed to load zones from %s: %s", uri, err, exc_info=True)
            result.failures.append((uri, str(err)))
    return result


async def get_zones(
    uris: list[str],
    hass: HomeAssistant,
    prioritize: bool,
    *,
    allow_private_urls: bool = False,
) -> list[Zone]:
    """Load every URI; return successful zones or raise if all URIs failed.

    Backward-compatible wrapper around :func:`load_zones` for callers that only
    care about the happy-path list (e.g. ``download_zones`` materialising a merge).
    When at least one URI returns zones, the failures are logged as WARNINGs and
    the union is returned. When every URI fails, ``ZoneFileCorrupt`` is raised
    with the first failure's message so existing retry/backoff logic keeps working.
    """
    result = await load_zones(uris, hass, prioritize, allow_private_urls=allow_private_urls)
    if uris and not result.zones and result.failures:
        first_uri, first_msg = result.failures[0]
        raise ZoneFileCorrupt(
            f"All {len(result.failures)} zone URIs failed; first: {first_uri}: {first_msg}"
        )
    return result.zones


def get_locations_zone(lat: float, lon: float, acc: float, zones: list[Zone]) -> dict | None:
    """Resolve the GPS position to the highest-priority enclosing zone.

    Args:
        lat: latitude of the GPS fix in degrees.
        lon: longitude of the GPS fix in degrees.
        acc: accuracy radius in metres (used to inflate the search point).
        zones: list of ``Zone`` objects to search.

    Returns:
        ``{"name": ..., "distance_to_centroid": <metres>, "matched_zones": [...]}``
        or ``None`` if the point falls outside every zone.

        ``matched_zones`` is the full list of zone names the buffered GPS point
        intersects (including the winner) — used for overlap-debugging in the
        mirror entity's attributes.
    """
    if not zones:
        return None

    gps_point = Point(lon, lat)
    buffer = gps_point.buffer(acc / 111320)

    possible = [z for z in zones if buffer.intersects(z.geometry)]
    if not possible:
        return None

    matched_names = [z.name for z in possible]

    if len(possible) == 1:
        z = possible[0]
        return {
            "name": z.name,
            "distance_to_centroid": get_distance_to_centroid(z.geometry, gps_point),
            "matched_zones": matched_names,
        }

    # Filter to the highest-priority candidates (lowest priority value wins)
    min_priority = min(z.priority for z in possible)
    candidates = [z for z in possible if z.priority == min_priority]

    closest = min(candidates, key=lambda z: get_distance_to_exterior_points(z.geometry, gps_point))
    return {
        "name": closest.name,
        "distance_to_centroid": get_distance_to_centroid(closest.geometry, gps_point),
        "matched_zones": matched_names,
    }
