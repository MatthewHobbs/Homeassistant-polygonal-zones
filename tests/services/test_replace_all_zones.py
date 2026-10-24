"""Tests for services.replace_all_zones."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.polygonal_zones.services.errors import (
    InvalidZoneData,
    ZoneAlreadyExists,
    ZoneFileNotEditable,
)
from custom_components.polygonal_zones.services.helpers import reset_mutation_rate_limit
from custom_components.polygonal_zones.services.replace_all_zones import action_builder


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
    fake_entity = SimpleNamespace(
        editable_file=True,
        zone_urls=["zones.json"],
        _source=SimpleNamespace(async_reload=AsyncMock(), entry_id="entry-id"),
        _config_entry_id="entry-id",
        hass=None,
    )
    action = action_builder(_make_hass(tmp_path))

    new_collection = {
        "type": "FeatureCollection",
        "features": [_polygon_feature("Home"), _polygon_feature("Work")],
    }
    call = SimpleNamespace(data={"device_id": "fake-device-id", "zone": json.dumps(new_collection)})

    with patch(
        "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
        return_value=[fake_entity],
    ):
        await action(call)

    parsed = json.loads((tmp_path / "zones.json").read_text())
    names = sorted(f["properties"]["name"] for f in parsed["features"])
    assert names == ["Home", "Work"]
    fake_entity._source.async_reload.assert_awaited_once()


async def test_replace_invalid_payload_raises(tmp_path) -> None:
    fake_entity = SimpleNamespace(
        editable_file=True,
        zone_urls=["zones.json"],
        _source=SimpleNamespace(async_reload=AsyncMock(), entry_id="entry-id"),
        _config_entry_id="entry-id",
        hass=None,
    )
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(data={"device_id": "fake-device-id", "zone": '{"type": "wrong"}'})

    with (
        patch(
            "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


async def test_replace_non_editable_raises(tmp_path) -> None:
    fake_entity = SimpleNamespace(
        editable_file=False, zone_urls=["https://x"], _config_entry_id="entry-id"
    )
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(
        data={
            "device_id": "fake-device-id",
            "zone": json.dumps({"type": "FeatureCollection", "features": []}),
        }
    )

    with (
        patch(
            "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneFileNotEditable),
    ):
        await action(call)


async def test_replace_all_wraps_a_lock_timeout(tmp_path) -> None:
    fake_entity = SimpleNamespace(
        editable_file=True, zone_urls=["zones.json"], _config_entry_id="entry-id"
    )
    call = SimpleNamespace(
        data={"device_id": "x", "zone": json.dumps({"type": "FeatureCollection", "features": []})}
    )
    with (
        patch(
            "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        patch(
            "custom_components.polygonal_zones.services.replace_all_zones.write_zones",
            new=MagicMock(side_effect=TimeoutError),
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action_builder(_make_hass(tmp_path))(call)


async def test_replace_with_duplicate_names_is_refused(tmp_path) -> None:
    reset_mutation_rate_limit()
    zones_file = tmp_path / "zones.json"
    zones_file.write_text(
        json.dumps({"type": "FeatureCollection", "features": [_polygon_feature("Home")]})
    )
    fake_entity = SimpleNamespace(
        editable_file=True,
        zone_urls=["zones.json"],
        _source=SimpleNamespace(async_reload=AsyncMock(), entry_id="entry-id"),
        _config_entry_id="entry-id",
        hass=None,
    )
    collection = {
        "type": "FeatureCollection",
        "features": [_polygon_feature("Home"), _polygon_feature("Home")],
    }
    call = SimpleNamespace(data={"device_id": "fake-device-id", "zone": json.dumps(collection)})

    with (
        patch(
            "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneAlreadyExists, match="Home"),
    ):
        await action_builder(_make_hass(tmp_path))(call)

    assert len(json.loads(zones_file.read_text())["features"]) == 1
    fake_entity._source.async_reload.assert_not_awaited()


async def test_replace_with_duplicate_ids_is_refused(tmp_path) -> None:
    reset_mutation_rate_limit()
    zones_file = tmp_path / "zones.json"
    zones_file.write_text(
        json.dumps({"type": "FeatureCollection", "features": [_polygon_feature("Home")]})
    )
    fake_entity = SimpleNamespace(
        editable_file=True,
        zone_urls=["zones.json"],
        _source=SimpleNamespace(async_reload=AsyncMock(), entry_id="entry-id"),
        _config_entry_id="entry-id",
        hass=None,
    )
    home = _polygon_feature("Home")
    home["properties"]["id"] = "same"
    work = _polygon_feature("Work")
    work["properties"]["id"] = "same"
    collection = {"type": "FeatureCollection", "features": [home, work]}
    call = SimpleNamespace(data={"device_id": "fake-device-id", "zone": json.dumps(collection)})

    with (
        patch(
            "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneAlreadyExists, match="same"),
    ):
        await action_builder(_make_hass(tmp_path))(call)

    assert len(json.loads(zones_file.read_text())["features"]) == 1
