"""Zone-related utility functions for the polygonal_zones integration."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from homeassistant.core import HomeAssistant
import numpy as np
from shapely.geometry import Point, shape
from shapely.geometry.polygon import Polygon

from ..const import MAX_SUPPORTED_SCHEMA_VERSION
from .general import load_data


class UnsupportedSchemaVersion(ValueError):
    """Raised when a zone file declares a schema_version this integration can't read."""


@dataclass
class Zone:
    """A single named polygonal zone with optional priority + extra properties."""

    name: str
    geometry: Polygon
    priority: int = 0
    properties: dict[str, Any] = field(default_factory=dict)


def haversine_distances(point: np.ndarray, coordinates: np.ndarray) -> np.ndarray:
    """Calculate Haversine distances from a single point to multiple points.

    Args:
        point: NumPy array of shape (2,) containing [latitude, longitude] in degrees.
        coordinates: NumPy array of shape (n, 2) containing latitudes and longitudes.

    Returns:
        Array of distances in metres.
    """
    R = 6371000  # Earth radius in metres

    lat1, lon1 = np.radians(point)
    lats2, lons2 = np.radians(coordinates).T

    dlat = lats2 - lat1
    dlon = lons2 - lon1

    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lats2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    return R * c


def get_distance_to_exterior_points(polygon: Polygon, point: Point) -> float:
    """Haversine distance to the closest point on the polygon's exterior, in metres."""
    polygon_points = np.array(polygon.exterior.coords)
    point_coords = np.array([point.x, point.y])
    distances = haversine_distances(point_coords, polygon_points)
    return float(min(distances))


def get_distance_to_centroid(polygon: Polygon, point: Point) -> float:
    """Haversine distance from ``point`` to the polygon's centroid, in metres (JSON-safe)."""
    centroid = polygon.centroid
    point_coords = np.array([point.x, point.y])
    centroid_coords = np.array([[centroid.x, centroid.y]])
    return float(haversine_distances(point_coords, centroid_coords)[0])


async def get_zones(uris: list[str], hass: HomeAssistant, prioritize: bool) -> list[Zone]:
    """Load and parse the GeoJSON file(s) into a list of ``Zone`` objects.

    Args:
        uris: URLs (or HA config-dir paths) of GeoJSON files.
        hass: The Home Assistant instance.
        prioritize: When True, features without an explicit priority inherit the
            file's index in ``uris`` so earlier files outrank later ones.

    Returns:
        A list of Zone objects parsed from every file.
    """
    zones: list[Zone] = []

    for idx, uri in enumerate(uris):
        raw = await load_data(uri, hass)
        data = json.loads(raw)

        pz = data.get("polygonal_zones") if isinstance(data, dict) else None
        if isinstance(pz, dict):
            declared_version = pz.get("schema_version", 1)
            if (
                isinstance(declared_version, int)
                and declared_version > MAX_SUPPORTED_SCHEMA_VERSION
            ):
                raise UnsupportedSchemaVersion(
                    f"Zone file {uri!r} declares schema_version={declared_version}; "
                    f"this integration supports up to {MAX_SUPPORTED_SCHEMA_VERSION}. "
                    "See docs/ZONES_FORMAT.md."
                )

        for feature in data["features"]:
            properties = dict(feature["properties"])
            if "priority" in properties:
                priority = int(properties["priority"])
            else:
                priority = idx if prioritize else 0

            geometry = shape(feature["geometry"])
            zones.append(
                Zone(
                    name=properties["name"],
                    geometry=geometry,
                    priority=priority,
                    properties=properties,
                )
            )

    return zones


def get_locations_zone(lat: float, lon: float, acc: float, zones: list[Zone]) -> dict | None:
    """Resolve the GPS position to the highest-priority enclosing zone.

    Args:
        lat: latitude of the GPS fix in degrees.
        lon: longitude of the GPS fix in degrees.
        acc: accuracy radius in metres (used to inflate the search point).
        zones: list of ``Zone`` objects to search.

    Returns:
        ``{"name": ..., "distance_to_centroid": <metres>}`` or ``None`` if the
        point falls outside every zone.
    """
    if not zones:
        return None

    gps_point = Point(lon, lat)
    buffer = gps_point.buffer(acc / 111320)

    possible = [z for z in zones if buffer.intersects(z.geometry)]
    if not possible:
        return None

    if len(possible) == 1:
        z = possible[0]
        return {
            "name": z.name,
            "distance_to_centroid": get_distance_to_centroid(z.geometry, gps_point),
        }

    # Filter to the highest-priority candidates (lowest priority value wins)
    min_priority = min(z.priority for z in possible)
    candidates = [z for z in possible if z.priority == min_priority]

    closest = min(candidates, key=lambda z: get_distance_to_exterior_points(z.geometry, gps_point))
    return {
        "name": closest.name,
        "distance_to_centroid": get_distance_to_centroid(closest.geometry, gps_point),
    }
