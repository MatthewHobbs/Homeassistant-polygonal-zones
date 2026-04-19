"""Test 8 — services.add_new_zone duplicate-name path."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.polygonal_zones.services.add_new_zone import action_builder
from custom_components.polygonal_zones.services.errors import ZoneAlreadyExists


def _polygon_feature(name: str) -> dict:
    return {
        "type": "Feature",
        "properties": {"name": name, "priority": 0},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
        },
    }


def _make_hass(tmp_path) -> SimpleNamespace:
    """Hass stub exposing only what the service code reaches into."""

    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=aaej,
    )


async def test_add_zone_duplicate_name_raises(tmp_path) -> None:
    """Re-adding a zone with an existing name surfaces ZoneAlreadyExists."""
    zones_file = tmp_path / "zones.json"
    zones_file.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [_polygon_feature("Home")],
            }
        )
    )

    fake_entity = SimpleNamespace(editable_file=True, zone_urls=["zones.json"])
    hass = _make_hass(tmp_path)
    action = action_builder(hass)

    call = SimpleNamespace(
        data={
            "device_id": "fake-device-id",
            "zone": json.dumps(_polygon_feature("Home")),
        }
    )

    with (
        patch(
            "custom_components.polygonal_zones.services.add_new_zone.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneAlreadyExists),
    ):
        await action(call)

    # File must be unchanged after the failed call.
    parsed = json.loads(zones_file.read_text())
    assert len(parsed["features"]) == 1
    assert parsed["features"][0]["properties"]["name"] == "Home"


async def test_add_zone_new_name_appends_to_file(tmp_path) -> None:
    """Happy path: a unique zone name is appended and persisted to disk."""
    zones_file = tmp_path / "zones.json"
    zones_file.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [_polygon_feature("Home")],
            }
        )
    )

    fake_entity = SimpleNamespace(editable_file=True, zone_urls=["zones.json"])
    hass = _make_hass(tmp_path)
    action = action_builder(hass)

    call = SimpleNamespace(
        data={
            "device_id": "fake-device-id",
            "zone": json.dumps(_polygon_feature("Work")),
        }
    )

    with patch(
        "custom_components.polygonal_zones.services.add_new_zone.get_entities_from_device_id",
        return_value=[fake_entity],
    ):
        await action(call)

    parsed = json.loads(zones_file.read_text())
    names = sorted(f["properties"]["name"] for f in parsed["features"])
    assert names == ["Home", "Work"]
