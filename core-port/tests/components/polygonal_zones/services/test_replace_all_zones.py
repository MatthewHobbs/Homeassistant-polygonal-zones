"""Tests for services.replace_all_zones."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from homeassistant.components.polygonal_zones.services.errors import (
    InvalidZoneData,
    ZoneFileNotEditable,
)
from homeassistant.components.polygonal_zones.services.replace_all_zones import action_builder


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
    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=aaej,
    )


async def test_replace_writes_full_collection(tmp_path) -> None:
    (tmp_path / "zones.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": [_polygon_feature("Old")]})
    )
    fake_entity = SimpleNamespace(editable_file=True, zone_urls=["zones.json"])
    action = action_builder(_make_hass(tmp_path))

    new_collection = {
        "type": "FeatureCollection",
        "features": [_polygon_feature("Home"), _polygon_feature("Work")],
    }
    call = SimpleNamespace(data={"device_id": "fake-device-id", "zone": json.dumps(new_collection)})

    with patch(
        "homeassistant.components.polygonal_zones.services.replace_all_zones.get_entities_from_device_id",
        return_value=[fake_entity],
    ):
        await action(call)

    parsed = json.loads((tmp_path / "zones.json").read_text())
    names = sorted(f["properties"]["name"] for f in parsed["features"])
    assert names == ["Home", "Work"]


async def test_replace_invalid_payload_raises(tmp_path) -> None:
    fake_entity = SimpleNamespace(editable_file=True, zone_urls=["zones.json"])
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(data={"device_id": "fake-device-id", "zone": '{"type": "wrong"}'})

    with (
        patch(
            "homeassistant.components.polygonal_zones.services.replace_all_zones.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


async def test_replace_non_editable_raises(tmp_path) -> None:
    fake_entity = SimpleNamespace(editable_file=False, zone_urls=["https://x"])
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(
        data={
            "device_id": "fake-device-id",
            "zone": json.dumps({"type": "FeatureCollection", "features": []}),
        }
    )

    with (
        patch(
            "homeassistant.components.polygonal_zones.services.replace_all_zones.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneFileNotEditable),
    ):
        await action(call)
