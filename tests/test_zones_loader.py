"""Tests for utils.zones.get_zones — GeoJSON parsing."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from shapely.geometry import Point, Polygon

from custom_components.polygonal_zones.utils.zones import (
    UnsupportedSchemaVersion,
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
    """get_zones converts a single GeoJSON file into a list of Zone objects."""
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
        zones = await get_zones(["http://example.com/zones.json"], SimpleNamespace(), False)

    assert len(zones) == 2
    assert {z.name for z in zones} == {"Home", "Work"}
    by_name = {z.name: z for z in zones}
    assert by_name["Home"].priority == 0


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
        zones = await get_zones(
            ["http://example.com/a.json", "http://example.com/b.json"],
            SimpleNamespace(),
            True,
        )

    priorities = {z.name: z.priority for z in zones}
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


def test_get_zones_empty_uri_list_returns_empty_list() -> None:
    """Edge case: zero URIs → empty list, not a crash."""

    async def _go():
        return await get_zones([], SimpleNamespace(), False)

    zones = asyncio.run(_go())
    assert zones == []


async def test_get_zones_accepts_missing_schema_version() -> None:
    """A file without a polygonal_zones member is treated as implicit schema_version=1."""
    payload = json.dumps({"type": "FeatureCollection", "features": [_polygon("Home")]})
    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        new=AsyncMock(return_value=payload),
    ):
        zones = await get_zones(["http://x"], SimpleNamespace(), False)
    assert zones[0].name == "Home"


async def test_get_zones_accepts_known_schema_version() -> None:
    payload = json.dumps(
        {
            "type": "FeatureCollection",
            "polygonal_zones": {"schema_version": 1},
            "features": [_polygon("Home")],
        }
    )
    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        new=AsyncMock(return_value=payload),
    ):
        zones = await get_zones(["http://x"], SimpleNamespace(), False)
    assert zones[0].name == "Home"


async def test_parse_serialize_roundtrip_preserves_extra_properties() -> None:
    """A full file → get_zones → zones_to_geojson → get_zones cycle preserves custom keys."""
    from custom_components.polygonal_zones.utils.local_zones import zones_to_geojson

    source = json.dumps(
        {
            "type": "FeatureCollection",
            "polygonal_zones": {"schema_version": 1},
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "name": "Home",
                        "priority": 2,
                        "description": "front door",
                        "polygonal_zones_ext": {"color": "#f00"},
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                    },
                }
            ],
        }
    )

    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        new=AsyncMock(return_value=source),
    ):
        first = await get_zones(["http://x"], SimpleNamespace(), False)

    serialized = zones_to_geojson(first)

    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        new=AsyncMock(return_value=serialized),
    ):
        second = await get_zones(["http://x"], SimpleNamespace(), False)

    assert second[0].properties["description"] == "front door"
    assert second[0].properties["polygonal_zones_ext"] == {"color": "#f00"}
    assert second[0].priority == 2


async def test_get_zones_rejects_future_schema_version() -> None:
    payload = json.dumps(
        {
            "type": "FeatureCollection",
            "polygonal_zones": {"schema_version": 99},
            "features": [_polygon("Home")],
        }
    )
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value=payload),
        ),
        pytest.raises(UnsupportedSchemaVersion, match="schema_version=99"),
    ):
        await get_zones(["http://x"], SimpleNamespace(), False)
