"""Final 7 lines to push coverage from 99% to 100%."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.polygonal_zones.config_flow import (
    ConfigFlow,
    OptionsFlowHandler,
)
from custom_components.polygonal_zones.device_tracker import PolygonalZoneEntity
from custom_components.polygonal_zones.services.add_new_zone import (
    action_builder as add_builder,
)
from custom_components.polygonal_zones.services.errors import (
    InvalidZoneData,
    ZoneFileNotEditable,
)
from custom_components.polygonal_zones.services.helpers import parse_zone_feature
from custom_components.polygonal_zones.utils.general import (
    event_should_trigger,
    load_data,
)

# 1. add_new_zone.py:30 — non-editable entity raises ZoneFileNotEditable


def _hass(tmp_path) -> SimpleNamespace:
    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=aaej,
    )


async def test_add_zone_non_editable_raises(tmp_path) -> None:
    fake_entity = SimpleNamespace(editable_file=False, zone_urls=["https://x"])
    action = add_builder(_hass(tmp_path))
    call = SimpleNamespace(
        data={
            "device_id": "x",
            "zone": json.dumps(
                {
                    "type": "Feature",
                    "properties": {"name": "Home", "priority": 0},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                    },
                }
            ),
        }
    )
    with (
        patch(
            "custom_components.polygonal_zones.services.add_new_zone.get_entities_from_device_id",
            return_value=[fake_entity],
        ),
        pytest.raises(ZoneFileNotEditable),
    ):
        await action(call)


# 2. helpers.py:29 — feature name exceeds MAX_ZONE_NAME_LEN


def test_parse_zone_feature_name_too_long() -> None:
    feature = {
        "type": "Feature",
        "properties": {"name": "x" * 201},
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]},
    }
    with pytest.raises(InvalidZoneData):
        parse_zone_feature(json.dumps(feature))


# 3. general.py:93 — streamed body exceeds MAX_RESPONSE_BYTES mid-stream


class _BigChunkResponse:
    """An aiohttp response stand-in whose iter_chunked yields >5 MiB."""

    def __init__(self) -> None:
        self.status = 200
        self.charset = "utf-8"
        self.content_length = None  # advertise nothing → fall through to streaming check

        async def _iter(_chunk_size: int):
            for _ in range(7):
                yield b"x" * (1024 * 1024)  # 7 MiB total

        self.content = SimpleNamespace(iter_chunked=_iter)

    def raise_for_status(self) -> None:
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None


class _FakeSession:
    def __init__(self, response) -> None:
        self._response = response

    def get(self, *_a, **_kw):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def close(self) -> None:
        return None


async def test_load_data_streamed_body_exceeds_max(tmp_path) -> None:
    response = _BigChunkResponse()
    hass = SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=AsyncMock(),
    )
    with (
        patch(
            "custom_components.polygonal_zones.utils.general.aiohttp.TCPConnector",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.polygonal_zones.utils.general.aiohttp.ClientSession",
            return_value=_FakeSession(response),
        ),
        pytest.raises(ValueError),
    ):
        await load_data("https://example.com/zones.json", hass)


# 4. general.py:130 — event_should_trigger returns False when old_state is None


def test_event_should_trigger_old_state_none() -> None:
    new = SimpleNamespace(attributes={"latitude": 1, "longitude": 2, "gps_accuracy": 5})
    event = SimpleNamespace(
        data={"entity_id": "device_tracker.me", "old_state": None, "new_state": new}
    )
    assert event_should_trigger(event, "device_tracker.me") is False


# 5. device_tracker.py:285-286 — _handle_state_change_builder closure


async def test_handle_state_change_builder_invokes_update_on_match() -> None:
    entity = PolygonalZoneEntity(
        tracked_entity_id="device_tracker.phone",
        config_entry_id="entry-id",
        zone_urls=["https://example.com/zones.json"],
        own_id="device_tracker.polygonal_zones_phone",
        prioritized_zone_files=False,
        editable_file=False,
    )
    update_mock = AsyncMock()
    entity._update_state = update_mock

    func = entity._handle_state_change_builder()

    old = SimpleNamespace(attributes={"latitude": 1, "longitude": 2, "gps_accuracy": 5})
    new_attrs = {"latitude": 99, "longitude": 2, "gps_accuracy": 5}
    new = SimpleNamespace(attributes=new_attrs)
    event = SimpleNamespace(
        data={"entity_id": "device_tracker.phone", "old_state": old, "new_state": new}
    )
    await func(event)
    update_mock.assert_awaited_once()


async def test_handle_state_change_builder_skips_other_entity() -> None:
    entity = PolygonalZoneEntity(
        tracked_entity_id="device_tracker.phone",
        config_entry_id="entry-id",
        zone_urls=["https://example.com/zones.json"],
        own_id="device_tracker.polygonal_zones_phone",
        prioritized_zone_files=False,
        editable_file=False,
    )
    update_mock = AsyncMock()
    entity._update_state = update_mock

    func = entity._handle_state_change_builder()
    event = SimpleNamespace(
        data={"entity_id": "device_tracker.someone_else", "old_state": None, "new_state": None}
    )
    await func(event)
    update_mock.assert_not_awaited()


# 6. config_flow.py:135 — async_get_options_flow returns an OptionsFlowHandler


def test_async_get_options_flow_returns_handler() -> None:
    handler = ConfigFlow.async_get_options_flow(SimpleNamespace())
    assert isinstance(handler, OptionsFlowHandler)
