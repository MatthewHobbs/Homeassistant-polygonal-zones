"""Coverage for the new exception-translation paths in services + helpers + general.

These tests exercise the broad except blocks (aiohttp.ClientError, OSError,
ValueError) added for the action-exceptions Silver rule.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from homeassistant.components.polygonal_zones.services.add_new_zone import (
    action_builder as add_builder,
)
from homeassistant.components.polygonal_zones.services.delete_zone import (
    action_builder as delete_builder,
)
from homeassistant.components.polygonal_zones.services.edit_zone import (
    action_builder as edit_builder,
)
from homeassistant.components.polygonal_zones.services.errors import InvalidZoneData
from homeassistant.components.polygonal_zones.services.replace_all_zones import (
    action_builder as replace_builder,
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


def _hass(tmp_path) -> SimpleNamespace:
    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=aaej,
    )


def _entity() -> SimpleNamespace:
    return SimpleNamespace(editable_file=True, zone_urls=["zones.json"])


def _add_call() -> SimpleNamespace:
    return SimpleNamespace(
        data={
            "device_id": "fake-device-id",
            "zone": json.dumps(_polygon_feature("New")),
        }
    )


async def test_add_zone_aiohttp_error_wrapped(tmp_path) -> None:
    (tmp_path / "zones.json").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    action = add_builder(_hass(tmp_path))
    with (
        patch(
            "homeassistant.components.polygonal_zones.services.add_new_zone.get_entities_from_device_id",
            return_value=[_entity()],
        ),
        patch(
            "homeassistant.components.polygonal_zones.services.add_new_zone.load_data",
            new=AsyncMock(side_effect=aiohttp.ClientError("network down")),
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(_add_call())


async def test_add_zone_oserror_wrapped(tmp_path) -> None:
    (tmp_path / "zones.json").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    action = add_builder(_hass(tmp_path))
    with (
        patch(
            "homeassistant.components.polygonal_zones.services.add_new_zone.get_entities_from_device_id",
            return_value=[_entity()],
        ),
        patch(
            "homeassistant.components.polygonal_zones.services.add_new_zone.save_zones",
            new=AsyncMock(side_effect=OSError("disk full")),
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(_add_call())


async def test_add_zone_valueerror_wrapped(tmp_path) -> None:
    (tmp_path / "zones.json").write_text("not valid json")
    action = add_builder(_hass(tmp_path))
    with (
        patch(
            "homeassistant.components.polygonal_zones.services.add_new_zone.get_entities_from_device_id",
            return_value=[_entity()],
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(_add_call())


async def test_delete_zone_aiohttp_error_wrapped(tmp_path) -> None:
    (tmp_path / "zones.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": [_polygon_feature("Home")]})
    )
    action = delete_builder(_hass(tmp_path))
    call = SimpleNamespace(data={"device_id": "x", "zone_name": "Home"})
    with (
        patch(
            "homeassistant.components.polygonal_zones.services.delete_zone.get_entities_from_device_id",
            return_value=[_entity()],
        ),
        patch(
            "homeassistant.components.polygonal_zones.services.delete_zone.load_data",
            new=AsyncMock(side_effect=aiohttp.ClientError("nope")),
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


async def test_delete_zone_oserror_wrapped(tmp_path) -> None:
    (tmp_path / "zones.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": [_polygon_feature("Home")]})
    )
    action = delete_builder(_hass(tmp_path))
    call = SimpleNamespace(data={"device_id": "x", "zone_name": "Home"})
    with (
        patch(
            "homeassistant.components.polygonal_zones.services.delete_zone.get_entities_from_device_id",
            return_value=[_entity()],
        ),
        patch(
            "homeassistant.components.polygonal_zones.services.delete_zone.save_zones",
            new=AsyncMock(side_effect=OSError("disk full")),
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


async def test_delete_zone_corrupt_json_wrapped(tmp_path) -> None:
    (tmp_path / "zones.json").write_text("not valid json")
    action = delete_builder(_hass(tmp_path))
    call = SimpleNamespace(data={"device_id": "x", "zone_name": "Home"})
    with (
        patch(
            "homeassistant.components.polygonal_zones.services.delete_zone.get_entities_from_device_id",
            return_value=[_entity()],
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


async def test_edit_zone_aiohttp_error_wrapped(tmp_path) -> None:
    (tmp_path / "zones.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": [_polygon_feature("Home")]})
    )
    action = edit_builder(_hass(tmp_path))
    call = SimpleNamespace(
        data={
            "device_id": "x",
            "zone_name": "Home",
            "zone": json.dumps(_polygon_feature("Home")),
        }
    )
    with (
        patch(
            "homeassistant.components.polygonal_zones.services.edit_zone.get_entities_from_device_id",
            return_value=[_entity()],
        ),
        patch(
            "homeassistant.components.polygonal_zones.services.edit_zone.load_data",
            new=AsyncMock(side_effect=aiohttp.ClientError("nope")),
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


async def test_edit_zone_oserror_wrapped(tmp_path) -> None:
    (tmp_path / "zones.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": [_polygon_feature("Home")]})
    )
    action = edit_builder(_hass(tmp_path))
    call = SimpleNamespace(
        data={
            "device_id": "x",
            "zone_name": "Home",
            "zone": json.dumps(_polygon_feature("Home")),
        }
    )
    with (
        patch(
            "homeassistant.components.polygonal_zones.services.edit_zone.get_entities_from_device_id",
            return_value=[_entity()],
        ),
        patch(
            "homeassistant.components.polygonal_zones.services.edit_zone.save_zones",
            new=AsyncMock(side_effect=OSError("disk full")),
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


async def test_edit_zone_corrupt_json_wrapped(tmp_path) -> None:
    (tmp_path / "zones.json").write_text("not valid json")
    action = edit_builder(_hass(tmp_path))
    call = SimpleNamespace(
        data={
            "device_id": "x",
            "zone_name": "Home",
            "zone": json.dumps(_polygon_feature("Home")),
        }
    )
    with (
        patch(
            "homeassistant.components.polygonal_zones.services.edit_zone.get_entities_from_device_id",
            return_value=[_entity()],
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


async def test_replace_all_oserror_wrapped(tmp_path) -> None:
    action = replace_builder(_hass(tmp_path))
    call = SimpleNamespace(
        data={
            "device_id": "x",
            "zone": json.dumps({"type": "FeatureCollection", "features": []}),
        }
    )
    with (
        patch(
            "homeassistant.components.polygonal_zones.services.replace_all_zones.get_entities_from_device_id",
            return_value=[_entity()],
        ),
        patch(
            "homeassistant.components.polygonal_zones.services.replace_all_zones.save_zones",
            new=AsyncMock(side_effect=OSError("disk full")),
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


async def test_replace_all_path_traversal_wrapped(tmp_path) -> None:
    action = replace_builder(_hass(tmp_path))
    bad_entity = SimpleNamespace(editable_file=True, zone_urls=["../../../etc/passwd"])
    call = SimpleNamespace(
        data={
            "device_id": "x",
            "zone": json.dumps({"type": "FeatureCollection", "features": []}),
        }
    )
    with (
        patch(
            "homeassistant.components.polygonal_zones.services.replace_all_zones.get_entities_from_device_id",
            return_value=[bad_entity],
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)
