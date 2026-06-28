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
        await get_zones(["http://example.com/zones.json"], SimpleNamespace(), False)


async def test_loader_accepts_valid_feature_collection() -> None:
    payload = json.dumps({"type": "FeatureCollection", "features": [_FEATURE]})
    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        new=AsyncMock(return_value=payload),
    ):
        zones = await get_zones(["http://example.com/zones.json"], SimpleNamespace(), False)
    assert [z.name for z in zones] == ["Home"]


def test_fetch_timeout_has_sub_timeouts() -> None:
    assert FETCH_TIMEOUT.total == 10
    assert FETCH_TIMEOUT.connect == 5
    assert FETCH_TIMEOUT.sock_read == 8


def test_id_is_a_known_feature_property_key() -> None:
    # The add-on stamps properties.id on every feature; it must not be treated
    # as drift (which would WARN on every mutation service call).
    assert "id" in KNOWN_FEATURE_PROPERTY_KEYS
