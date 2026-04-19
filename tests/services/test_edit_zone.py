"""Tests for services.edit_zone."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.polygonal_zones.services.edit_zone import action_builder
from custom_components.polygonal_zones.services.errors import (
    ZoneDoesNotExists,
    ZoneFileNotEditable,
)


def _polygon_feature(name: str, lat0: float = 0.0) -> dict:
    return {
        "type": "Feature",
        "properties": {"name": name, "priority": 0},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, lat0], [0, lat0 + 1], [1, lat0 + 1], [1, lat0], [0, lat0]]],
        },
    }


def _make_hass(tmp_path) -> SimpleNamespace:
    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=aaej,
    )


async def test_edit_existing_zone_replaces_geometry(tmp_path) -> None:
    (tmp_path / "zones.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": [_polygon_feature("Home", lat0=0)]})
    )
    fake_entity = SimpleNamespace(
        editable_file=True,
        zone_urls=["zones.json"],
        async_reload_zones=AsyncMock(),
        _config_entry_id="entry-id",
    )
    action = action_builder(_make_hass(tmp_path))

    new_zone = _polygon_feature("Home", lat0=10)
    call = SimpleNamespace(
        data={
            "device_id": "fake-device-id",
            "zone_name": "Home",
            "zone": json.dumps(new_zone),
        }
    )

    with patch(
        "custom_components.polygonal_zones.services.edit_zone.get_entities_from_device_id",
        return_value=[fake_entity],
    ):
        await action(call)

    parsed = json.loads((tmp_path / "zones.json").read_text())
    assert len(parsed["features"]) == 1
    assert parsed["features"][0]["geometry"]["coordinates"][0][0] == [0, 10]
    fake_entity.async_reload_zones.assert_awaited_once_with()


async def test_edit_preserves_feature_order(tmp_path) -> None:
    """Editing a zone replaces it in place — surrounding features keep their indices."""
    (tmp_path / "zones.json").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    _polygon_feature("Alpha"),
                    _polygon_feature("Bravo"),
                    _polygon_feature("Charlie"),
                ],
            }
        )
    )
    fake_entity = SimpleNamespace(
        editable_file=True,
        zone_urls=["zones.json"],
        async_reload_zones=AsyncMock(),
        _config_entry_id="entry-id",
    )
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(
        data={
            "device_id": "fake-device-id",
            "zone_name": "Bravo",
            "zone": json.dumps(_polygon_feature("Bravo", lat0=42)),
        }
    )

    with patch(
        "custom_components.polygonal_zones.services.edit_zone.get_entities_from_device_id",
        return_value=[fake_entity],
    ):
        await action(call)

    names = [
        f["properties"]["name"]
        for f in json.loads((tmp_path / "zones.json").read_text())["features"]
    ]
    assert names == ["Alpha", "Bravo", "Charlie"]


async def test_edit_missing_zone_raises(tmp_path) -> None:
    (tmp_path / "zones.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": [_polygon_feature("Home")]})
    )
    fake_entity = SimpleNamespace(
        editable_file=True,
        zone_urls=["zones.json"],
        async_reload_zones=AsyncMock(),
        _config_entry_id="entry-id",
    )
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(
        data={
            "device_id": "fake-device-id",
            "zone_name": "Nope",
            "zone": json.dumps(_polygon_feature("Nope")),
        }
    )

    with (
        patch(
            "custom_components.polygonal_zones.services.edit_zone.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneDoesNotExists),
    ):
        await action(call)


async def test_edit_missing_zone_name_raises(tmp_path) -> None:
    fake_entity = SimpleNamespace(
        editable_file=True,
        zone_urls=["zones.json"],
        async_reload_zones=AsyncMock(),
        _config_entry_id="entry-id",
    )
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(
        data={"device_id": "fake-device-id", "zone": json.dumps(_polygon_feature("Home"))}
    )

    with (
        patch(
            "custom_components.polygonal_zones.services.edit_zone.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneDoesNotExists),
    ):
        await action(call)


async def test_edit_non_editable_raises(tmp_path) -> None:
    fake_entity = SimpleNamespace(
        editable_file=False, zone_urls=["https://x"], _config_entry_id="entry-id"
    )
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(
        data={
            "device_id": "fake-device-id",
            "zone_name": "Home",
            "zone": json.dumps(_polygon_feature("Home")),
        }
    )

    with (
        patch(
            "custom_components.polygonal_zones.services.edit_zone.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneFileNotEditable),
    ):
        await action(call)
