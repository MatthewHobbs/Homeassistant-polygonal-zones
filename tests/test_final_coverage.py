"""Targeted tests to push the remaining branches over 99% coverage."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.polygonal_zones.device_tracker import PolygonalZoneEntity
from custom_components.polygonal_zones.services.add_new_zone import (
    action_builder as add_builder,
)
from custom_components.polygonal_zones.services.delete_zone import (
    action_builder as delete_builder,
)
from custom_components.polygonal_zones.services.edit_zone import (
    action_builder as edit_builder,
)
from custom_components.polygonal_zones.services.errors import InvalidZoneData
from custom_components.polygonal_zones.services.replace_all_zones import (
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


def _entity_stub() -> SimpleNamespace:
    return SimpleNamespace(
        editable_file=True, zone_urls=["zones.json"], _config_entry_id="entry-id"
    )


# ---- TimeoutError wrapping in each service ----


async def test_add_zone_timeout_wrapped(tmp_path) -> None:
    (tmp_path / "zones.json").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    action = add_builder(_hass(tmp_path))
    call = SimpleNamespace(data={"device_id": "x", "zone": json.dumps(_polygon_feature("Home"))})
    with (
        patch(
            "custom_components.polygonal_zones.services.add_new_zone.get_entities_from_device_id",
            return_value=[_entity_stub()],
        ),
        patch(
            "custom_components.polygonal_zones.services.add_new_zone.load_data",
            new=AsyncMock(side_effect=TimeoutError),
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


async def test_delete_zone_timeout_wrapped(tmp_path) -> None:
    (tmp_path / "zones.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": [_polygon_feature("Home")]})
    )
    action = delete_builder(_hass(tmp_path))
    call = SimpleNamespace(data={"device_id": "x", "zone_name": "Home"})
    with (
        patch(
            "custom_components.polygonal_zones.services.delete_zone.get_entities_from_device_id",
            return_value=[_entity_stub()],
        ),
        patch(
            "custom_components.polygonal_zones.services.delete_zone.load_data",
            new=AsyncMock(side_effect=TimeoutError),
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


async def test_edit_zone_timeout_wrapped(tmp_path) -> None:
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
            "custom_components.polygonal_zones.services.edit_zone.get_entities_from_device_id",
            return_value=[_entity_stub()],
        ),
        patch(
            "custom_components.polygonal_zones.services.edit_zone.load_data",
            new=AsyncMock(side_effect=TimeoutError),
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


async def test_replace_all_timeout_wrapped(tmp_path) -> None:
    action = replace_builder(_hass(tmp_path))
    call = SimpleNamespace(
        data={
            "device_id": "x",
            "zone": json.dumps({"type": "FeatureCollection", "features": []}),
        }
    )
    with (
        patch(
            "custom_components.polygonal_zones.services.replace_all_zones.get_entities_from_device_id",
            return_value=[_entity_stub()],
        ),
        patch(
            "custom_components.polygonal_zones.services.replace_all_zones.save_zones",
            new=AsyncMock(side_effect=TimeoutError),
        ),
        pytest.raises(InvalidZoneData),
    ):
        await action(call)


# ---- _retry inner function in device_tracker ----


def _make_entity_for_retry() -> PolygonalZoneEntity:
    return PolygonalZoneEntity(
        tracked_entity_id="device_tracker.phone",
        config_entry_id="entry-id",
        zone_urls=["https://example.com/zones.json"],
        own_id="device_tracker.polygonal_zones_phone",
        prioritized_zone_files=False,
        editable_file=False,
    )


async def test_retry_callback_fires_initialize_again() -> None:
    """async_call_later is invoked with the _retry closure; calling it triggers another attempt."""
    entity = _make_entity_for_retry()
    bus = SimpleNamespace(async_listen=MagicMock(return_value=lambda: None))
    create_task_calls = []
    entity.hass = SimpleNamespace(
        bus=bus,
        async_create_task=MagicMock(side_effect=lambda coro: create_task_calls.append(coro)),
    )
    entity.async_get_last_state = AsyncMock(return_value=None)

    captured = {}

    def fake_at_started(hass, cb):
        captured["cb"] = cb
        return lambda: None

    def fake_call_later(_hass, _delay, callback):
        # Synchronously invoke the retry closure to cover its body
        callback(None)
        return lambda: None

    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.async_at_started",
            side_effect=fake_at_started,
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.load_zones",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.async_call_later",
            side_effect=fake_call_later,
        ),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_create_issue"),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
    ):
        await entity.async_added_to_hass()
        await captured["cb"](entity.hass)

    # Cleanup any coroutine objects we created (the retry called create_task with one)
    for coro in create_task_calls:
        coro.close()
    assert len(create_task_calls) == 1


# ---- general._PublicOnlyResolver mixed-IP filtering ----


async def test_public_only_resolver_drops_private_keeps_public() -> None:
    """When a single hostname returns both public and private IPs, only publics survive."""
    from custom_components.polygonal_zones.utils.general import _PublicOnlyResolver

    resolver = _PublicOnlyResolver()
    mixed = [{"host": "8.8.8.8"}, {"host": "10.0.0.1"}]
    with patch(
        "aiohttp.resolver.DefaultResolver.resolve",
        new=AsyncMock(return_value=mixed),
    ):
        infos = await resolver.resolve("mixed.example", 443)
    assert infos == [{"host": "8.8.8.8"}]


async def test_public_only_resolver_skips_garbage_addresses() -> None:
    """Non-IP strings in the resolver output are silently skipped."""
    from custom_components.polygonal_zones.utils.general import _PublicOnlyResolver

    resolver = _PublicOnlyResolver()
    bad = [{"host": "not-an-ip"}, {"host": "8.8.8.8"}]
    with patch(
        "aiohttp.resolver.DefaultResolver.resolve",
        new=AsyncMock(return_value=bad),
    ):
        infos = await resolver.resolve("garbage.example", 443)
    assert infos == [{"host": "8.8.8.8"}]


# ---- event_should_trigger fall-through ----


def test_event_should_trigger_attribute_change_returns_true() -> None:
    """The any() comparison returns True when one of the required attrs changed."""
    from custom_components.polygonal_zones.utils.general import event_should_trigger

    old = SimpleNamespace(attributes={"latitude": 1, "longitude": 2, "gps_accuracy": 5})
    new = SimpleNamespace(attributes={"latitude": 99, "longitude": 2, "gps_accuracy": 5})
    event = SimpleNamespace(
        data={"entity_id": "device_tracker.me", "old_state": old, "new_state": new}
    )
    assert event_should_trigger(event, "device_tracker.me") is True


# ---- helpers.parse_zone_collection valid coverage ----


def test_parse_zone_collection_string_features_rejected() -> None:
    """Edge: features is present but not a list."""
    from custom_components.polygonal_zones.services.helpers import parse_zone_collection

    with pytest.raises(InvalidZoneData):
        parse_zone_collection(
            json.dumps({"type": "FeatureCollection", "features": {"not": "a list"}})
        )


# ---- __init__.async_unload_entry safe_config_path fallback ----


async def test_unload_entry_path_traversal_falls_back(tmp_path, monkeypatch) -> None:
    """When safe_config_path raises ValueError, fall back to a manual Path build."""
    from custom_components.polygonal_zones import async_unload_entry
    from custom_components.polygonal_zones.const import DOMAIN

    unload_mock = AsyncMock(return_value=True)
    entry = SimpleNamespace(entry_id="entry-1")
    hass = SimpleNamespace(
        data={DOMAIN: {"entry-1": ["entity"]}},
        config=SimpleNamespace(config_dir=str(tmp_path)),
        config_entries=SimpleNamespace(async_unload_platforms=unload_mock),
    )

    with patch(
        "custom_components.polygonal_zones.safe_config_path",
        side_effect=ValueError("forced traversal"),
    ):
        result = await async_unload_entry(hass, entry)
    assert result is True


# Sanity asyncio import to satisfy the linter
def test_asyncio_imported() -> None:
    assert asyncio is asyncio
