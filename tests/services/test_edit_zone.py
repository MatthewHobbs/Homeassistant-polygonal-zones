"""Tests for services.edit_zone."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.polygonal_zones.services.edit_zone import action_builder
from custom_components.polygonal_zones.services.errors import (
    ZoneAlreadyExists,
    ZoneDoesNotExists,
    ZoneFileNotEditable,
)
from custom_components.polygonal_zones.services.helpers import reset_mutation_rate_limit


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
        _source=SimpleNamespace(async_reload=AsyncMock(), entry_id="entry-id"),
        _config_entry_id="entry-id",
        hass=None,
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
        "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
        return_value=[fake_entity],
    ):
        await action(call)

    parsed = json.loads((tmp_path / "zones.json").read_text())
    assert len(parsed["features"]) == 1
    assert parsed["features"][0]["geometry"]["coordinates"][0][0] == [0, 10]
    fake_entity._source.async_reload.assert_awaited_once()


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
        _source=SimpleNamespace(async_reload=AsyncMock(), entry_id="entry-id"),
        _config_entry_id="entry-id",
        hass=None,
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
        "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
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
        _source=SimpleNamespace(async_reload=AsyncMock(), entry_id="entry-id"),
        _config_entry_id="entry-id",
        hass=None,
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
            "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneDoesNotExists),
    ):
        await action(call)


async def test_edit_missing_zone_name_raises(tmp_path) -> None:
    fake_entity = SimpleNamespace(
        editable_file=True,
        zone_urls=["zones.json"],
        _source=SimpleNamespace(async_reload=AsyncMock(), entry_id="entry-id"),
        _config_entry_id="entry-id",
        hass=None,
    )
    action = action_builder(_make_hass(tmp_path))

    call = SimpleNamespace(
        data={"device_id": "fake-device-id", "zone": json.dumps(_polygon_feature("Home"))}
    )

    with (
        patch(
            "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
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
            "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneFileNotEditable),
    ):
        await action(call)


async def test_rename_onto_an_existing_name_is_refused(tmp_path) -> None:
    """Duplicates make the target of every later action ambiguous: get_zone_idx
    returns the first match, so a delete would remove the wrong polygon."""
    reset_mutation_rate_limit()
    zones_file = tmp_path / "zones.json"
    zones_file.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [_polygon_feature("Alpha"), _polygon_feature("Bravo")],
            }
        )
    )
    fake_entity = SimpleNamespace(
        editable_file=True,
        zone_urls=["zones.json"],
        _source=SimpleNamespace(async_reload=AsyncMock(), entry_id="entry-id"),
        _config_entry_id="entry-id",
        hass=None,
    )
    call = SimpleNamespace(
        data={
            "device_id": "fake-device-id",
            "zone_name": "Alpha",
            "zone": json.dumps(_polygon_feature("Bravo")),
        }
    )

    with (
        patch(
            "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneAlreadyExists, match="Bravo"),
    ):
        await action_builder(_make_hass(tmp_path))(call)

    names = [f["properties"]["name"] for f in json.loads(zones_file.read_text())["features"]]
    assert names == ["Alpha", "Bravo"]
    fake_entity._source.async_reload.assert_not_awaited()


async def test_edit_onto_an_existing_id_is_refused(tmp_path) -> None:
    """An id binds automations to a zone; two zones sharing one is ambiguous."""
    reset_mutation_rate_limit()
    zones_file = tmp_path / "zones.json"
    alpha = _polygon_feature("Alpha")
    alpha["properties"]["id"] = "id-alpha"
    bravo = _polygon_feature("Bravo")
    bravo["properties"]["id"] = "id-bravo"
    zones_file.write_text(json.dumps({"type": "FeatureCollection", "features": [alpha, bravo]}))
    fake_entity = SimpleNamespace(
        editable_file=True,
        zone_urls=["zones.json"],
        _source=SimpleNamespace(async_reload=AsyncMock(), entry_id="entry-id"),
        _config_entry_id="entry-id",
        hass=None,
    )
    renamed = _polygon_feature("Alpha", lat0=5)
    renamed["properties"]["id"] = "id-bravo"
    call = SimpleNamespace(
        data={
            "device_id": "fake-device-id",
            "zone_name": "Alpha",
            "zone": json.dumps(renamed),
        }
    )

    with (
        patch(
            "custom_components.polygonal_zones.services.helpers.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneAlreadyExists, match="id-bravo"),
    ):
        await action_builder(_make_hass(tmp_path))(call)

    ids = [f["properties"]["id"] for f in json.loads(zones_file.read_text())["features"]]
    assert ids == ["id-alpha", "id-bravo"]
