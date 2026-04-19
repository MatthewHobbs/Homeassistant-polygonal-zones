"""Tests for utils.zones.get_zones — GeoJSON parsing."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np
from shapely.geometry import Point, Polygon

from custom_components.polygonal_zones.utils.zones import (
    get_distance_to_centroid,
    get_distance_to_exterior_points,
    get_zones,
    haversine_distances,
)


def _polygon(name: str, priority: int | None = None) -> dict:
    feature = {
        "type": "Feature",
        "properties": {"name": name},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
        },
    }
    if priority is not None:
        feature["properties"]["priority"] = priority
    return feature


async def test_get_zones_parses_feature_collection() -> None:
    """get_zones converts a single GeoJSON file into a DataFrame of Polygon rows."""
    payload = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [_polygon("Home", priority=0), _polygon("Work")],
        }
    )
    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        new=AsyncMock(return_value=payload),
    ):
        df = await get_zones(["http://example.com/zones.json"], SimpleNamespace(), False)

    assert len(df) == 2
    assert set(df["name"]) == {"Home", "Work"}
    # Home had explicit priority 0; Work falls back to idx (0) when prioritize=False
    assert int(df.loc[df["name"] == "Home", "priority"].iloc[0]) == 0


async def test_get_zones_prioritise_uses_file_index() -> None:
    """With prioritize=True, features without an explicit priority inherit the file index."""
    file_a = json.dumps({"type": "FeatureCollection", "features": [_polygon("A")]})
    file_b = json.dumps({"type": "FeatureCollection", "features": [_polygon("B")]})

    async def fake_load(uri: str, _hass) -> str:
        return file_a if "a." in uri else file_b

    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        side_effect=fake_load,
    ):
        df = await get_zones(
            ["http://example.com/a.json", "http://example.com/b.json"],
            SimpleNamespace(),
            True,
        )

    priorities = dict(zip(df["name"], df["priority"], strict=False))
    assert priorities["A"] == 0
    assert priorities["B"] == 1


def test_haversine_distance_known_pair() -> None:
    """London → Paris, ~344 km, accept 1% tolerance."""
    london = np.array([51.5074, -0.1278])
    paris = np.array([[48.8566, 2.3522]])
    distance_m = haversine_distances(london, paris)[0]
    distance_km = distance_m / 1000.0
    assert abs(distance_km - 344) < 4


def test_haversine_distance_to_self_is_zero() -> None:
    p = np.array([10.0, 20.0])
    distance = haversine_distances(p, np.array([[10.0, 20.0]]))[0]
    assert abs(distance) < 1e-6


def test_get_distance_to_centroid_returns_float() -> None:
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    point = Point(0.5, 0.5)
    distance = get_distance_to_centroid(polygon, point)
    assert isinstance(distance, float)


def test_get_distance_to_exterior_points_returns_min() -> None:
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    point = Point(0.5, 0.5)
    d = get_distance_to_exterior_points(polygon, point)
    assert d > 0


def test_get_zones_empty_uri_list_returns_empty_df() -> None:
    """Edge case: zero URIs → empty DataFrame, not a crash."""
    import asyncio

    async def _go():
        return await get_zones([], SimpleNamespace(), False)

    df = asyncio.run(_go())
    assert df.empty
