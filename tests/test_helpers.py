"""Tests for services.helpers — GeoJSON contract validation."""

import json

import pytest

from custom_components.polygonal_zones.services.errors import InvalidZoneData
from custom_components.polygonal_zones.services.helpers import (
    parse_zone_collection,
    parse_zone_feature,
)


def _feature(geometry: dict | None, name: str = "Home", priority: int = 0) -> dict:
    return {
        "type": "Feature",
        "properties": {"name": name, "priority": priority},
        "geometry": geometry,
    }


VALID_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
}


def test_valid_polygon_feature_round_trips() -> None:
    feature = _feature(VALID_POLYGON)
    parsed = parse_zone_feature(json.dumps(feature))
    assert parsed["properties"]["name"] == "Home"
    assert parsed["geometry"]["type"] == "Polygon"


def test_null_geometry_rejected() -> None:
    """A Feature with ``geometry: null`` must be rejected before it reaches shapely."""
    feature = _feature(None)
    with pytest.raises(InvalidZoneData):
        parse_zone_feature(json.dumps(feature))


def test_missing_geometry_key_rejected() -> None:
    raw = json.dumps({"type": "Feature", "properties": {"name": "Home"}})
    with pytest.raises(InvalidZoneData):
        parse_zone_feature(raw)


def test_linestring_geometry_rejected() -> None:
    """A non-Polygon geometry must be rejected before it reaches shapely."""
    feature = _feature({"type": "LineString", "coordinates": [[0, 0], [1, 1]]})
    with pytest.raises(InvalidZoneData):
        parse_zone_feature(json.dumps(feature))


def test_multipolygon_geometry_accepted() -> None:
    """MultiPolygon is the only supported non-Polygon type."""
    feature = _feature(
        {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]],
        }
    )
    parsed = parse_zone_feature(json.dumps(feature))
    assert parsed["geometry"]["type"] == "MultiPolygon"


def test_missing_name_rejected() -> None:
    raw = json.dumps({"type": "Feature", "properties": {}, "geometry": VALID_POLYGON})
    with pytest.raises(InvalidZoneData):
        parse_zone_feature(raw)


def test_payload_too_large_rejected() -> None:
    huge = "x" * (1_048_577)
    with pytest.raises(InvalidZoneData):
        parse_zone_feature(huge)


def test_collection_round_trips() -> None:
    collection = {
        "type": "FeatureCollection",
        "features": [_feature(VALID_POLYGON, name="Home"), _feature(VALID_POLYGON, name="Work")],
    }
    parsed = parse_zone_collection(json.dumps(collection))
    assert len(parsed["features"]) == 2


def test_collection_with_invalid_inner_feature_rejected() -> None:
    """Every feature inside a FeatureCollection is validated; a bad one fails the whole call."""
    collection = {
        "type": "FeatureCollection",
        "features": [_feature(VALID_POLYGON, name="Home"), _feature(None, name="Bad")],
    }
    with pytest.raises(InvalidZoneData):
        parse_zone_collection(json.dumps(collection))
