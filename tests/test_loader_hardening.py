"""Regression tests for loader/reliability hardening.

- The URI loader must reject a payload that is not a GeoJSON FeatureCollection,
  matching the strictness of the mutation-service validator.
- The HTTP fetch timeout must carry connect/read sub-timeouts, not just a total.
- ``id`` (the editor add-on's stable per-feature handle) must be a known
  feature property key so add-on-produced files don't log a WARNING on every
  mutation.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.polygonal_zones.services.helpers import KNOWN_FEATURE_PROPERTY_KEYS
from custom_components.polygonal_zones.utils.general import FETCH_TIMEOUT
from custom_components.polygonal_zones.utils.zones import ZoneFileCorrupt, get_zones


async def _run_executor_job(func, *args):
    return func(*args)


def _make_hass() -> SimpleNamespace:
    return SimpleNamespace(async_add_executor_job=_run_executor_job)


_FEATURE = {
    "type": "Feature",
    "properties": {"name": "Home"},
    "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]},
}


async def test_loader_rejects_non_feature_collection() -> None:
    """A payload missing the FeatureCollection type member is not loaded."""
    payload = json.dumps({"features": [_FEATURE]})  # no "type"
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value=payload),
        ),
        pytest.raises(ZoneFileCorrupt),
    ):
        # Single URI; it fails the type check, so all URIs failed -> raises.
        await get_zones(["http://example.com/zones.json"], _make_hass(), False)


async def test_loader_accepts_valid_feature_collection() -> None:
    payload = json.dumps({"type": "FeatureCollection", "features": [_FEATURE]})
    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        new=AsyncMock(return_value=payload),
    ):
        zones = await get_zones(["http://example.com/zones.json"], _make_hass(), False)
    assert [z.name for z in zones] == ["Home"]


async def test_loader_rejects_too_many_features() -> None:
    """Read-time cap: a file exceeding the feature limit is rejected, not parsed."""
    from custom_components.polygonal_zones.utils.limits import MAX_FEATURES_PER_COLLECTION

    payload = json.dumps(
        {"type": "FeatureCollection", "features": [_FEATURE] * (MAX_FEATURES_PER_COLLECTION + 1)}
    )
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value=payload),
        ),
        pytest.raises(ZoneFileCorrupt),
    ):
        await get_zones(["http://example.com/zones.json"], _make_hass(), False)


def _collection(feature: dict) -> str:
    return json.dumps({"type": "FeatureCollection", "features": [feature]})


async def _expect_corrupt(feature: dict) -> None:
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value=_collection(feature)),
        ),
        pytest.raises(ZoneFileCorrupt),
    ):
        await get_zones(["http://example.com/zones.json"], _make_hass(), False)


async def test_loader_rejects_non_polygon_geometry() -> None:
    """A LineString/Point/etc. is refused at the read boundary — this closes the
    vertex-cap bypass (non-Polygon geometry counts as 0 vertices) and the
    downstream ``.exterior`` crash in the zone tie-break."""
    await _expect_corrupt(
        {
            "type": "Feature",
            "properties": {"name": "Sneaky"},
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        }
    )


async def test_loader_vertex_cap_not_bypassed_by_linestring() -> None:
    """A giant LineString (which count_geometry_vertices scores as 0) is still
    rejected — the type gate fires before the vertex count can be gamed."""
    huge = {
        "type": "Feature",
        "properties": {"name": "Huge"},
        "geometry": {"type": "LineString", "coordinates": [[i, i] for i in range(50_000)]},
    }
    await _expect_corrupt(huge)


async def test_loader_read_path_vertex_cap_enforced() -> None:
    """A Polygon exceeding the total-vertex cap is rejected on the read path."""
    from custom_components.polygonal_zones.utils.limits import (
        MAX_TOTAL_VERTICES_PER_COLLECTION,
    )

    ring = [[0, 0]] * (MAX_TOTAL_VERTICES_PER_COLLECTION + 5)
    await _expect_corrupt(
        {
            "type": "Feature",
            "properties": {"name": "Big"},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        }
    )


async def test_loader_rejects_feature_not_an_object() -> None:
    await _expect_corrupt("not-a-feature-object")  # type: ignore[arg-type]


async def test_loader_rejects_properties_not_a_dict() -> None:
    await _expect_corrupt(
        {"type": "Feature", "properties": ["nope"], "geometry": _FEATURE["geometry"]}
    )


async def test_loader_rejects_non_int_str_priority() -> None:
    await _expect_corrupt(
        {
            "type": "Feature",
            "properties": {"name": "P", "priority": [1]},
            "geometry": _FEATURE["geometry"],
        }
    )


async def test_loader_rejects_unparseable_geometry() -> None:
    await _expect_corrupt(
        {
            "type": "Feature",
            "properties": {"name": "Bad"},
            "geometry": {"type": "Polygon", "coordinates": "not-coordinates"},
        }
    )


async def test_loader_wraps_recursion_error() -> None:
    """A RecursionError from json.loads (adversarial deep nesting) surfaces as a typed
    ZoneFileCorrupt, for parity with the mutation-service parsers."""
    with (
        patch(
            "custom_components.polygonal_zones.utils.zones.load_data",
            new=AsyncMock(return_value="[]"),
        ),
        patch(
            "custom_components.polygonal_zones.utils.zones.json.loads",
            side_effect=RecursionError,
        ),
        pytest.raises(ZoneFileCorrupt),
    ):
        await get_zones(["http://example.com/zones.json"], _make_hass(), False)


def test_fetch_timeout_has_sub_timeouts() -> None:
    assert FETCH_TIMEOUT.total == 10
    assert FETCH_TIMEOUT.connect == 5
    assert FETCH_TIMEOUT.sock_read == 8


def test_id_is_a_known_feature_property_key() -> None:
    # The add-on stamps properties.id on every feature; it must not be treated
    # as drift (which would WARN on every mutation service call).
    assert "id" in KNOWN_FEATURE_PROPERTY_KEYS
