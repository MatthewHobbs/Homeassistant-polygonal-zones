"""Tests for utils.zones — pure-Python geospatial logic."""

import pandas as pd
from shapely.geometry import Polygon

from custom_components.polygonal_zones.utils.zones import get_locations_zone


def _zone(name: str, polygon_coords: list[tuple[float, float]], priority: int = 0) -> dict:
    return {
        "name": name,
        "geometry": Polygon(polygon_coords),
        "priority": priority,
    }


# Two non-overlapping unit squares: A at (0,0)-(1,1), B at (2,0)-(3,1).
# Overlapping pair for priority tests: C and D both contain (5,5).
SQUARE_A = [(0, 0), (1, 0), (1, 1), (0, 1)]
SQUARE_B = [(2, 0), (3, 0), (3, 1), (2, 1)]
SQUARE_C = [(4, 4), (6, 4), (6, 6), (4, 6)]
SQUARE_D = [(4.5, 4.5), (5.5, 4.5), (5.5, 5.5), (4.5, 5.5)]


def test_point_inside_single_zone() -> None:
    """A point inside exactly one zone returns that zone's name."""
    zones = pd.DataFrame([_zone("A", SQUARE_A), _zone("B", SQUARE_B)])
    # gps_accuracy of 1 m → buffer ~9e-6° (effectively the point itself)
    result = get_locations_zone(lat=0.5, lon=0.5, acc=1, zones=zones)
    assert result is not None
    assert result["name"] == "A"


def test_point_outside_all_zones_returns_none() -> None:
    """A point not inside any zone returns None — used to render the "away" state."""
    zones = pd.DataFrame([_zone("A", SQUARE_A), _zone("B", SQUARE_B)])
    result = get_locations_zone(lat=10.0, lon=10.0, acc=1, zones=zones)
    assert result is None


def test_priority_tiebreak_picks_correct_zone() -> None:
    """Two overlapping zones at point (5,5).

    C has priority 1, D has priority 0 (lower number = higher priority).
    With ``prioritize`` enabled the integration should return D, not C.
    """
    zones = pd.DataFrame(
        [
            _zone("C", SQUARE_C, priority=1),
            _zone("D", SQUARE_D, priority=0),
        ]
    )
    result = get_locations_zone(lat=5.0, lon=5.0, acc=1, zones=zones)
    assert result is not None
    assert result["name"] == "D"


def test_empty_zones_returns_none() -> None:
    """With no zones loaded the call must return None, not raise."""
    zones = pd.DataFrame([])
    assert get_locations_zone(lat=0.5, lon=0.5, acc=1, zones=zones) is None
