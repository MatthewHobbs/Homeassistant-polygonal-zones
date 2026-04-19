"""Geometry / great-circle helpers for polygonal_zones.

Extracted from ``utils/zones.py`` as a standalone module so future work —
process-pool offload, rtree spatial indexing, a rust extension — has a
narrow, replaceable seam to target without touching the GeoJSON parser or
the Zone dataclass. All functions here are pure CPU and do not depend on
Home Assistant.
"""

from __future__ import annotations

from collections.abc import Iterable
import math

from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

_EARTH_RADIUS_M = 6371000


def _haversine_metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine great-circle distance between two (lat, lon) pairs in metres.

    Pure stdlib math. Polygon exterior loops run through this in Python;
    the vertex-per-collection cap keeps the worst case at ~10k iterations,
    which is sub-millisecond in CPython.
    """
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = lat2_r - lat1_r
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_M * c


def haversine_distances(
    point: tuple[float, float], coordinates: Iterable[tuple[float, float]]
) -> list[float]:
    """Return Haversine distances in metres from one point to every coordinate.

    ``point`` and each entry of ``coordinates`` are ``(lat, lon)`` tuples in
    degrees.
    """
    lat1, lon1 = point
    return [_haversine_metres(lat1, lon1, lat2, lon2) for lat2, lon2 in coordinates]


def get_distance_to_exterior_points(polygon: Polygon, point: Point) -> float:
    """Haversine distance to the closest point on the polygon's exterior, in metres.

    Uses ``(point.x, point.y)`` directly (which in shapely terms is ``(lon, lat)``
    for GeoJSON-convention polygons) to preserve the exact numerics of the prior
    numpy implementation.
    """
    return min(_haversine_metres(point.x, point.y, x, y) for x, y in polygon.exterior.coords)


def get_distance_to_centroid(polygon: Polygon, point: Point) -> float:
    """Haversine distance from ``point`` to the polygon's centroid, in metres (JSON-safe)."""
    centroid = polygon.centroid
    return _haversine_metres(point.x, point.y, centroid.x, centroid.y)
