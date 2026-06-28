"""Cross-repo contract conformance: the integration must parse the exact zones.json
shape the editor add-on writes.

The add-on (Homeassistant-polygonal-zones-addon) stamps the schema version at the
nested ``polygonal_zones.schema_version`` location and a stable ``properties.id``
(uuid4 hex) on every feature. If the integration's parser ever stops accepting
that shape, the two halves silently diverge. This test pins the contract from the
consumer side; pair it with the add-on's own write tests.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from custom_components.polygonal_zones.utils.zones import get_zones


async def _run_executor_job(func, *args):
    return func(*args)


def _make_hass() -> SimpleNamespace:
    return SimpleNamespace(async_add_executor_job=_run_executor_job)


# A faithful copy of what the add-on's _normalise_feature_collection writes:
# nested schema_version + a uuid4-hex properties.id on every feature.
_ADDON_OUTPUT = {
    "type": "FeatureCollection",
    "polygonal_zones": {"schema_version": 1},
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "Home", "id": "9f8c1e2a4b6d4f0a8c7e1d2b3a4c5e6f"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"name": "School", "id": "1a2b3c4d5e6f7081920304a5b6c7d8e9"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[5, 5], [5, 6], [6, 6], [6, 5], [5, 5]]],
            },
        },
    ],
}


async def test_integration_parses_addon_zones_json() -> None:
    """The integration loads an add-on-produced file (nested schema_version + id)."""
    with patch(
        "custom_components.polygonal_zones.utils.zones.load_data",
        new=AsyncMock(return_value=json.dumps(_ADDON_OUTPUT)),
    ):
        zones = await get_zones(["http://addon.local:8000/zones.json"], _make_hass(), False)

    assert [z.name for z in zones] == ["Home", "School"]
    # The add-on's stable id round-trips through to the parsed zone's properties.
    assert zones[0].properties.get("id") == "9f8c1e2a4b6d4f0a8c7e1d2b3a4c5e6f"
