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
