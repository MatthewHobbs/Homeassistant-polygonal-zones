"""Regression tests: geometry helpers must handle MultiPolygon zones.

The editor add-on and the GeoJSON spec both allow ``MultiPolygon`` geometries.
``get_distance_to_exterior_points`` previously did ``polygon.exterior.coords``,
which raises ``AttributeError`` on a ``MultiPolygon`` and crashed zone
tie-breaking the moment two same-priority zones overlapped and one was a
multi-part zone.
"""

from shapely.geometry import MultiPolygon, Point, Polygon

from custom_components.polygonal_zones.utils.geometry import (
    exterior_coords,
    get_distance_to_centroid,
    get_distance_to_exterior_points,
    haversine_distances,
)

# Two disjoint unit squares → a MultiPolygon.
_SQUARE_A = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
_SQUARE_B = Polygon([(5, 5), (5, 6), (6, 6), (6, 5)])
_MULTI = MultiPolygon([_SQUARE_A, _SQUARE_B])


def test_exterior_coords_polygon():
    coords = list(exterior_coords(_SQUARE_A))
    assert (0.0, 0.0) in coords
    assert len(coords) == 5  # closed ring repeats the first vertex


def test_exterior_coords_multipolygon_covers_all_parts():
    coords = list(exterior_coords(_MULTI))
    # Vertices from both parts must be present.
    assert (0.0, 0.0) in coords
    assert (5.0, 5.0) in coords
    assert len(coords) == 10  # two closed 5-point rings


def test_distance_to_exterior_points_multipolygon_does_not_raise():
    point = Point(0.5, 0.5)  # inside square A
    dist = get_distance_to_exterior_points(_MULTI, point)
    # Closest exterior point of the nearer part; finite, non-negative metres.
    assert dist >= 0.0
    # Must equal the single-Polygon answer for the nearer part (B is far away).
    assert dist == get_distance_to_exterior_points(_SQUARE_A, point)


def test_distance_to_centroid_multipolygon_does_not_raise():
    point = Point(0.5, 0.5)
    assert get_distance_to_centroid(_MULTI, point) >= 0.0


# Distance helpers must use (lat, lon) order. shapely stores GeoJSON coords as
# (x=lon, y=lat); _haversine_metres wants (lat, lon). These cross-check the
# helpers against haversine_distances (the known-correct oracle) using a
# London-ish polygon and a Paris-ish point (~344 km apart) — they fail if the
# lon/lat order regresses.
_LONDON_POLY = Polygon([(-0.13, 51.50), (-0.14, 51.50), (-0.14, 51.51), (-0.13, 51.51)])
_PARIS_POINT = Point(2.0, 49.0)  # (x=lon, y=lat)


def test_distance_to_exterior_uses_correct_latlon_order():
    got = get_distance_to_exterior_points(_LONDON_POLY, _PARIS_POINT)
    oracle = min(
        haversine_distances((49.0, 2.0), [(y, x)])[0] for x, y in _LONDON_POLY.exterior.coords
    )
    assert abs(got - oracle) < 1.0  # metres
    assert got > 300_000  # ~344 km London<->Paris; a lon/lat swap is far off this


def test_distance_to_centroid_uses_correct_latlon_order():
    got = get_distance_to_centroid(_LONDON_POLY, _PARIS_POINT)
    c = _LONDON_POLY.centroid
    oracle = haversine_distances((49.0, 2.0), [(c.y, c.x)])[0]
    assert abs(got - oracle) < 1.0
    assert got > 300_000
