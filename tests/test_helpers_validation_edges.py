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


def _make_polygon_feature(name: str, vertex_count: int) -> dict:
    """Build a GeoJSON Feature with a polygon ring of ``vertex_count`` coordinates."""
    ring = [[float(i), float(i)] for i in range(vertex_count - 1)]
    ring.append(ring[0])  # close the ring
    return {
        "type": "Feature",
        "properties": {"name": name},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def test_parse_zone_feature_rejects_too_many_vertices() -> None:
    """A single feature with > MAX_TOTAL_VERTICES_PER_COLLECTION vertices is refused."""
    feature = _make_polygon_feature("Huge", 10_002)
    with pytest.raises(InvalidZoneData, match="vertices"):
        parse_zone_feature(json.dumps(feature))


def test_parse_zone_feature_accepts_vertex_cap_exact() -> None:
    """Exactly MAX_TOTAL_VERTICES_PER_COLLECTION vertices in one feature is accepted."""
    feature = _make_polygon_feature("Edge", 10_000)
    parsed = parse_zone_feature(json.dumps(feature))
    assert parsed["properties"]["name"] == "Edge"


def test_parse_zone_collection_rejects_too_many_features() -> None:
    """A collection with > MAX_FEATURES_PER_COLLECTION features is refused."""
    features = [_make_polygon_feature(f"Z{i}", 4) for i in range(501)]
    raw = json.dumps({"type": "FeatureCollection", "features": features})
    with pytest.raises(InvalidZoneData, match="features"):
        parse_zone_collection(raw)


def test_parse_zone_collection_rejects_too_many_total_vertices() -> None:
    """Summed vertices across features must stay under the collection cap."""
    # 3 features of 5000 rings each = 15000 total vertices > 10_000
    features = [_make_polygon_feature(f"Z{i}", 5000) for i in range(3)]
    raw = json.dumps({"type": "FeatureCollection", "features": features})
    with pytest.raises(InvalidZoneData, match="total vertices"):
        parse_zone_collection(raw)


def test_parse_zone_collection_accepts_at_caps() -> None:
    """At exactly the caps, the collection is accepted."""
    # 2 features of 5000 vertices = 10000 total
    features = [_make_polygon_feature(f"Z{i}", 5000) for i in range(2)]
    raw = json.dumps({"type": "FeatureCollection", "features": features})
    parsed = parse_zone_collection(raw)
    assert len(parsed["features"]) == 2


def test_parse_zone_feature_warns_on_unknown_property_keys(caplog) -> None:
    """Unknown top-level property keys are preserved but logged at WARNING."""
    feature = _make_polygon_feature("Home", 4)
    feature["properties"]["color"] = "#ff0000"
    feature["properties"]["nickname"] = "house"

    with caplog.at_level("WARNING", logger="custom_components.polygonal_zones.services.helpers"):
        parsed = parse_zone_feature(json.dumps(feature))

    assert parsed["properties"]["color"] == "#ff0000"
    assert parsed["properties"]["nickname"] == "house"
    assert any("unknown property keys" in rec.message for rec in caplog.records)
    warning_message = next(rec.message for rec in caplog.records if "unknown property keys" in rec.message)
    assert "color" in warning_message
    assert "nickname" in warning_message


def test_parse_zone_feature_polygonal_zones_ext_is_not_unknown(caplog) -> None:
    """The reserved polygonal_zones_ext namespace passes validation silently."""
    feature = _make_polygon_feature("Home", 4)
    feature["properties"]["polygonal_zones_ext"] = {"editor": "addon", "color": "#00f"}

    with caplog.at_level("WARNING", logger="custom_components.polygonal_zones.services.helpers"):
        parsed = parse_zone_feature(json.dumps(feature))

    assert parsed["properties"]["polygonal_zones_ext"]["editor"] == "addon"
    assert not any("unknown property keys" in rec.message for rec in caplog.records)


def test_parse_zone_feature_name_and_priority_are_not_unknown(caplog) -> None:
    """The canonical keys name + priority never trigger the drift warning."""
    feature = _make_polygon_feature("Home", 4)
    feature["properties"]["priority"] = 1

    with caplog.at_level("WARNING", logger="custom_components.polygonal_zones.services.helpers"):
        parse_zone_feature(json.dumps(feature))

    assert not any("unknown property keys" in rec.message for rec in caplog.records)
