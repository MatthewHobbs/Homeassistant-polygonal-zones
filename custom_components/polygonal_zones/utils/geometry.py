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

from shapely.geometry import MultiPolygon, Point
from shapely.geometry.polygon import Polygon

_EARTH_RADIUS_M = 6371000


def exterior_coords(geometry: Polygon | MultiPolygon) -> Iterable[tuple[float, float]]:
    """Yield exterior-ring coordinates of a Polygon or every part of a MultiPolygon.

    The GeoJSON spec and the editor add-on both allow ``MultiPolygon`` zones, so
    callers must not assume ``geometry.exterior`` exists (``MultiPolygon`` has no
    ``.exterior`` — only ``.geoms``). Interior rings (holes) are intentionally
    ignored: distance-to-zone is measured to the outer boundary only, matching
    the prior Polygon-only behaviour.
    """
    if isinstance(geometry, MultiPolygon):
        for part in geometry.geoms:
            yield from part.exterior.coords
    else:
        yield from geometry.exterior.coords


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


def get_distance_to_exterior_points(polygon: Polygon | MultiPolygon, point: Point) -> float:
    """Haversine distance to the closest point on the zone's exterior, in metres.

    Accepts ``Polygon`` and ``MultiPolygon`` (the latter previously raised
    ``AttributeError`` here, crashing zone tie-breaking).

    shapely stores GeoJSON coordinates as ``(x, y) = (lon, lat)``, but
    ``_haversine_metres`` expects ``(lat, lon)`` pairs — so pass ``point.y``
    (lat) before ``point.x`` (lon), and likewise ``y`` before ``x`` for each
    exterior vertex. (The earlier code passed them lon-first, producing
    incorrect great-circle distances that skewed tie-breaking, worst near the
    poles.)
    """
    return min(_haversine_metres(point.y, point.x, y, x) for x, y in exterior_coords(polygon))


def get_distance_to_centroid(polygon: Polygon | MultiPolygon, point: Point) -> float:
    """Haversine distance from ``point`` to the zone's centroid, in metres (JSON-safe).

    ``.centroid`` is defined for ``MultiPolygon`` too, so no special-casing is
    needed here.

    Passes ``(lat, lon)`` to ``_haversine_metres`` (i.e. ``.y`` before ``.x``);
    shapely's ``.x``/``.y`` are lon/lat for GeoJSON coordinates.
    """
    centroid = polygon.centroid
    return _haversine_metres(point.y, point.x, centroid.y, centroid.x)
