"""Tests for services.delete_zone."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.polygonal_zones.services.delete_zone import action_builder
from custom_components.polygonal_zones.services.errors import (
    InvalidZoneData,
    ZoneDoesNotExists,
    ZoneFileNotEditable,
)


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


def _seed_zones(tmp_path, names: list[str]) -> None:
    (tmp_path / "zones.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": [_polygon_feature(n) for n in names]})
    )


async def test_delete_existing_zone(tmp_path) -> None:
    _seed_zones(tmp_path, ["Home", "Work"])
    fake_entity = SimpleNamespace(
        editable_file=True, zone_urls=["zones.json"], async_reload_zones=AsyncMock()
    )
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(data={"device_id": "fake-device-id", "zone_name": "Home"})

    with patch(
        "custom_components.polygonal_zones.services.delete_zone.get_entities_from_device_id",
        return_value=[fake_entity],
    ):
        await action(call)

    parsed = json.loads((tmp_path / "zones.json").read_text())
    names = [f["properties"]["name"] for f in parsed["features"]]
    assert names == ["Work"]
    fake_entity.async_reload_zones.assert_awaited_once_with()


async def test_delete_missing_zone_raises(tmp_path) -> None:
    _seed_zones(tmp_path, ["Home"])
    fake_entity = SimpleNamespace(
        editable_file=True, zone_urls=["zones.json"], async_reload_zones=AsyncMock()
    )
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(data={"device_id": "fake-device-id", "zone_name": "Nope"})

    with (
        patch(
            "custom_components.polygonal_zones.services.delete_zone.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneDoesNotExists),
    ):
        await action(call)


async def test_delete_missing_zone_name_raises(tmp_path) -> None:
    fake_entity = SimpleNamespace(
        editable_file=True, zone_urls=["zones.json"], async_reload_zones=AsyncMock()
    )
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(data={"device_id": "fake-device-id"})

    with (
        patch(
            "custom_components.polygonal_zones.services.delete_zone.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneDoesNotExists),
    ):
        await action(call)


async def test_delete_non_editable_raises(tmp_path) -> None:
    fake_entity = SimpleNamespace(editable_file=False, zone_urls=["https://x"])
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(data={"device_id": "fake-device-id", "zone_name": "Home"})

    with (
        patch(
            "custom_components.polygonal_zones.services.delete_zone.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneFileNotEditable),
    ):
        await action(call)


async def test_delete_path_traversal_wrapped(tmp_path) -> None:
    fake_entity = SimpleNamespace(editable_file=True, zone_urls=["../../../etc/passwd"])
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(data={"device_id": "fake-device-id", "zone_name": "Home"})

    with (
        patch(
            "custom_components.polygonal_zones.services.delete_zone.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)
