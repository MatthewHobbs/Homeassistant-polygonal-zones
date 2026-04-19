"""Edge-case coverage for services.helpers._validate_feature."""

import json

import pytest

from custom_components.polygonal_zones.services.errors import InvalidZoneData
from custom_components.polygonal_zones.services.helpers import (
    parse_zone_collection,
    parse_zone_feature,
)


def test_parse_zone_feature_empty_string() -> None:
    with pytest.raises(InvalidZoneData):
        parse_zone_feature("")


def test_parse_zone_feature_invalid_json() -> None:
    with pytest.raises(InvalidZoneData):
        parse_zone_feature("not json at all {")


def test_parse_zone_feature_not_a_feature() -> None:
    with pytest.raises(InvalidZoneData):
        parse_zone_feature(json.dumps({"type": "FeatureCollection", "features": []}))


def test_parse_zone_feature_properties_not_dict() -> None:
    raw = json.dumps({"type": "Feature", "properties": "nope", "geometry": {}})
    with pytest.raises(InvalidZoneData):
        parse_zone_feature(raw)


def test_parse_zone_feature_name_is_blank() -> None:
    raw = json.dumps(
        {
            "type": "Feature",
            "properties": {"name": "   "},
            "geometry": {"type": "Polygon", "coordinates": []},
        }
    )
    with pytest.raises(InvalidZoneData):
        parse_zone_feature(raw)


def test_parse_zone_collection_empty_string() -> None:
    with pytest.raises(InvalidZoneData):
        parse_zone_collection("")


def test_parse_zone_collection_features_not_list() -> None:
    raw = json.dumps({"type": "FeatureCollection", "features": "nope"})
    with pytest.raises(InvalidZoneData):
        parse_zone_collection(raw)


def test_parse_zone_collection_invalid_json() -> None:
    with pytest.raises(InvalidZoneData):
        parse_zone_collection("not json {")


def test_parse_zone_collection_too_large() -> None:
    huge = "x" * (1_048_577)
    with pytest.raises(InvalidZoneData):
        parse_zone_collection(huge)
