"""Tests for utils.zones — pure-Python geospatial logic."""

import pytest
from shapely.geometry import Polygon

from custom_components.polygonal_zones.utils.zones import Zone, get_locations_zone


def _zone(name: str, polygon_coords: list[tuple[float, float]], priority: int = 0) -> Zone:
    return Zone(name=name, geometry=Polygon(polygon_coords), priority=priority)


# Two non-overlapping unit squares: A at (0,0)-(1,1), B at (2,0)-(3,1).
# Overlapping pair for priority tests: C and D both contain (5,5).
SQUARE_A = [(0, 0), (1, 0), (1, 1), (0, 1)]
SQUARE_B = [(2, 0), (3, 0), (3, 1), (2, 1)]
SQUARE_C = [(4, 4), (6, 4), (6, 6), (4, 6)]
SQUARE_D = [(4.5, 4.5), (5.5, 4.5), (5.5, 5.5), (4.5, 5.5)]


def test_point_inside_single_zone() -> None:
    """A point inside exactly one zone returns that zone's name."""
    zones = [_zone("A", SQUARE_A), _zone("B", SQUARE_B)]
    # gps_accuracy of 1 m → buffer ~9e-6° (effectively the point itself)
    result = get_locations_zone(lat=0.5, lon=0.5, acc=1, zones=zones)
    assert result is not None
    assert result["name"] == "A"


def test_point_outside_all_zones_returns_none() -> None:
    """A point not inside any zone returns None — used to render the "away" state."""
    zones = [_zone("A", SQUARE_A), _zone("B", SQUARE_B)]
    result = get_locations_zone(lat=10.0, lon=10.0, acc=1, zones=zones)
    assert result is None


def test_priority_tiebreak_picks_correct_zone() -> None:
    """Two overlapping zones at point (5,5).

    C has priority 1, D has priority 0 (lower number = higher priority).
    With ``prioritize`` enabled the integration should return D, not C.
    """
    zones = [
        _zone("C", SQUARE_C, priority=1),
        _zone("D", SQUARE_D, priority=0),
    ]
    result = get_locations_zone(lat=5.0, lon=5.0, acc=1, zones=zones)
    assert result is not None
    assert result["name"] == "D"


def test_empty_zones_returns_none() -> None:
    """With no zones loaded the call must return None, not raise."""
    assert get_locations_zone(lat=0.5, lon=0.5, acc=1, zones=[]) is None


def test_matched_zones_lists_every_intersecting_zone() -> None:
    """``matched_zones`` exposes every zone the buffered point intersects."""
    zones = [
        _zone("C", SQUARE_C, priority=1),
        _zone("D", SQUARE_D, priority=0),
    ]
    result = get_locations_zone(lat=5.0, lon=5.0, acc=1, zones=zones)
    assert result is not None
    # Winner is D (lower priority value) — see test_priority_tiebreak.
    assert result["name"] == "D"
    # The 'matched_zones' list contains both zones the buffered point intersects.
    assert set(result["matched_zones"]) == {"C", "D"}


def test_matched_zones_single_match() -> None:
    """Single-match case still populates matched_zones for attribute consistency."""
    zones = [_zone("A", SQUARE_A), _zone("B", SQUARE_B)]
    result = get_locations_zone(lat=0.5, lon=0.5, acc=1, zones=zones)
    assert result is not None
    assert result["matched_zones"] == ["A"]


# --- accuracy handling -------------------------------------------------------
#
# Regression cover for a bug where any tracker reporting gps_accuracy 0 read as
# "away" no matter where it was. get_locations_zone inflated the fix with
# Point.buffer(acc / 111320); Shapely returns an EMPTY polygon for buffer(0), and
# an empty geometry intersects nothing, so every zone test failed. The whole
# suite previously passed acc=1 as its stand-in for "no inflation", so the
# boundary value was never exercised.
#
# None is reachable in production: the caller gates on the gps_accuracy key being
# *present*, not on it being non-None, and TrackerEntity declares it `float | None`.
# Before the fix that raised TypeError on `acc / 111320`; it must now behave as
# "no accuracy figure". NaN takes the same branch, as every NaN comparison is False.


@pytest.mark.parametrize("acc", [0, 0.0, -1, -0.5, None, float("nan"), float("inf"), float("-inf")])
def test_non_positive_accuracy_still_matches_enclosing_zone(acc: float | None) -> None:
    """Zero/negative accuracy means "no figure available", not "match nothing"."""
    zones = [_zone("A", SQUARE_A), _zone("B", SQUARE_B)]
    result = get_locations_zone(lat=0.5, lon=0.5, acc=acc, zones=zones)
    assert result is not None, f"acc={acc!r} must not suppress an enclosing zone"
    assert result["name"] == "A"
    assert result["matched_zones"] == ["A"]


@pytest.mark.parametrize("acc", [0, 0.0, -1, None, float("nan"), float("inf")])
def test_non_positive_accuracy_still_reports_away_when_outside(acc: float | None) -> None:
    """The fix must not turn "outside" into a false match — only remove the inflation."""
    zones = [_zone("A", SQUARE_A), _zone("B", SQUARE_B)]
    assert get_locations_zone(lat=10.0, lon=10.0, acc=acc, zones=zones) is None


def test_zero_accuracy_does_not_match_a_zone_it_is_merely_near() -> None:
    """With no inflation, a point outside a zone stays outside however close it is.

    (1.0000001, 0.5) sits just beyond SQUARE_A's eastern edge. A generous accuracy
    reaches it; zero accuracy must not.
    """
    zones = [_zone("A", SQUARE_A)]
    near = {"lat": 0.5, "lon": 1.0000001, "zones": zones}
    assert get_locations_zone(acc=0, **near) is None
    assert get_locations_zone(acc=1000, **near) is not None


def test_positive_accuracy_still_inflates() -> None:
    """The inflating behaviour is unchanged for real accuracy values.

    (1.00001, 0.5) is ~1.1 m outside SQUARE_A — reachable by a 5 m accuracy ring
    but not by a 0.01 m one. Guards against "fixed" becoming "never inflates".
    """
    zones = [_zone("A", SQUARE_A)]
    just_outside = {"lat": 0.5, "lon": 1.00001, "zones": zones}
    assert get_locations_zone(acc=5, **just_outside) is not None
    assert get_locations_zone(acc=0.01, **just_outside) is None


def test_infinite_accuracy_does_not_raise() -> None:
    """Infinity must not reach shapely.

    ``Point.buffer(inf)`` raises ValueError("buffer distance must be finite"), and
    this runs inside an executor job where that surfaces as an unhandled exception
    rather than an "away" state. Treated as "no usable figure" instead.
    """
    zones = [_zone("A", SQUARE_A)]
    result = get_locations_zone(lat=0.5, lon=0.5, acc=float("inf"), zones=zones)
    assert result is not None
    assert result["name"] == "A"


def test_point_exactly_on_zone_boundary_counts_as_inside() -> None:
    """On-edge is inside, and stays inside once the buffer is removed.

    ``Point(1.0, 0.5)`` sits exactly on SQUARE_A's eastern edge: shapely reports
    ``intersects`` True but ``contains`` False, so the choice of predicate decides
    the answer. Asserted explicitly because removing the buffer for acc<=0 would
    silently change edge semantics if ``intersects`` were ever swapped for
    ``contains``.
    """
    zones = [_zone("A", SQUARE_A)]
    for acc in (0, 1):
        result = get_locations_zone(lat=0.5, lon=1.0, acc=acc, zones=zones)
        assert result is not None, f"boundary point must match with acc={acc}"
        assert result["name"] == "A"
