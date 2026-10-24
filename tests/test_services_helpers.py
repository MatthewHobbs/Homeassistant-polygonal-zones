"""Tests for services.helpers — get_entities_from_device_id branches."""

import asyncio
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.polygonal_zones.const import DOMAIN
from custom_components.polygonal_zones.services.errors import (
    InvalidZoneData,
    RateLimited,
    ZoneFileNotEditable,
)
from custom_components.polygonal_zones.services.helpers import (
    audit_mutation_call,
    enforce_mutation_rate_limit,
    get_entities_from_device_id,
    get_zone_idx,
    modify_zone_file,
    require_device_id,
    reset_mutation_rate_limit,
    resolve_mutation_target,
    sync_entities_after_write,
)
from custom_components.polygonal_zones.utils.local_zones import file_lock, write_zones


def test_require_device_id_string() -> None:
    assert require_device_id({"device_id": "abc"}) == "abc"


def test_require_device_id_list() -> None:
    assert require_device_id({"device_id": ["abc", "def"]}) == "abc"


def test_require_device_id_missing_raises() -> None:
    with pytest.raises(InvalidZoneData):
        require_device_id({})


def test_require_device_id_empty_list_raises() -> None:
    with pytest.raises(InvalidZoneData):
        require_device_id({"device_id": []})


def test_get_zone_idx_finds_existing() -> None:
    zones = {
        "features": [
            {"properties": {"name": "Home"}},
            {"properties": {"name": "Work"}},
        ]
    }
    assert get_zone_idx("Work", zones) == 1


def test_get_zone_idx_missing_returns_none() -> None:
    zones = {"features": [{"properties": {"name": "Home"}}]}
    assert get_zone_idx("Other", zones) is None


def test_get_entities_from_device_id_unknown_device() -> None:
    """An unrecognised device_id surfaces as InvalidZoneData."""
    fake_registry = SimpleNamespace(async_get=lambda _id: None)
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_entry=lambda _eid: None),
    )

    with (
        patch(
            "custom_components.polygonal_zones.services.helpers.dr.async_get",
            return_value=fake_registry,
        ),
        pytest.raises(InvalidZoneData),
    ):
        get_entities_from_device_id("ghost-id", hass)


def test_get_entities_from_device_id_unregistered_entry() -> None:
    """Device exists but its entry isn't in our integration (different domain)."""
    fake_device = SimpleNamespace(primary_config_entry="other-entry")
    fake_registry = SimpleNamespace(async_get=lambda _id: fake_device)
    other_entry = SimpleNamespace(domain="some_other_domain")
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_entry=lambda _eid: other_entry),
    )

    with (
        patch(
            "custom_components.polygonal_zones.services.helpers.dr.async_get",
            return_value=fake_registry,
        ),
        pytest.raises(InvalidZoneData),
    ):
        get_entities_from_device_id("device-id", hass)


def test_get_entities_from_device_id_happy_path() -> None:
    from custom_components.polygonal_zones import PolygonalZonesData

    fake_device = SimpleNamespace(primary_config_entry="entry-1")
    fake_registry = SimpleNamespace(async_get=lambda _id: fake_device)
    fake_entity = SimpleNamespace()
    fake_entry = SimpleNamespace(
        domain=DOMAIN, runtime_data=PolygonalZonesData(entities=[fake_entity])
    )
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_entry=lambda _eid: fake_entry),
    )

    with patch(
        "custom_components.polygonal_zones.services.helpers.dr.async_get",
        return_value=fake_registry,
    ):
        entities = get_entities_from_device_id("device-id", hass)
        assert entities == [fake_entity]


async def test_sync_entities_after_write_reloads_shared_source_once() -> None:
    """All entities read one shared source, so a mutation reloads it exactly once."""
    shared = SimpleNamespace(async_reload=AsyncMock(), entry_id="entry-id")
    a = SimpleNamespace(_source=shared, hass=None)
    b = SimpleNamespace(_source=shared, hass=None)

    await sync_entities_after_write([a, b])

    shared.async_reload.assert_awaited_once()


async def test_sync_entities_after_write_swallows_reload_failure() -> None:
    """A post-write reload failure is logged, not raised — the write already committed."""
    shared = SimpleNamespace(async_reload=AsyncMock(side_effect=RuntimeError("boom")))
    shared.entry_id = "entry-id"
    a = SimpleNamespace(_source=shared, hass=None)

    await sync_entities_after_write([a])  # must not raise
    shared.async_reload.assert_awaited_once()


# ---------- enforce_mutation_rate_limit ----------


def test_rate_limit_second_call_within_window_raises() -> None:
    """A repeat call within the minimum interval raises RateLimited."""
    enforce_mutation_rate_limit("busy-entry")
    with pytest.raises(RateLimited, match="Rate limit exceeded"):
        enforce_mutation_rate_limit("busy-entry")


def test_rate_limit_is_scoped_per_entry() -> None:
    """Mutations on entry A don't gate mutations on entry B."""
    enforce_mutation_rate_limit("entry-a")
    # No raise — different entry_id.
    enforce_mutation_rate_limit("entry-b")


# ---------- audit_mutation_call ----------


def test_audit_log_emits_user_id_when_present(caplog) -> None:
    call = SimpleNamespace(context=SimpleNamespace(user_id="user-123"))
    with caplog.at_level("INFO", logger="custom_components.polygonal_zones.services.helpers"):
        audit_mutation_call(call, "add_new_zone", "entry-1")
    assert any("user=user-123" in rec.message for rec in caplog.records)
    assert any("entry=entry-1" in rec.message for rec in caplog.records)


def test_audit_log_falls_back_when_user_id_missing(caplog) -> None:
    """Automations / system invocations have no user_id — log a sentinel instead of None."""
    call = SimpleNamespace(context=SimpleNamespace(user_id=None))
    with caplog.at_level("INFO", logger="custom_components.polygonal_zones.services.helpers"):
        audit_mutation_call(call, "edit_zone", "entry-2")
    assert any("user=<automation/system>" in rec.message for rec in caplog.records)


def test_audit_log_survives_missing_context(caplog) -> None:
    """A ServiceCall without a ``context`` attribute still logs rather than crashing."""
    call = SimpleNamespace()
    with caplog.at_level("INFO", logger="custom_components.polygonal_zones.services.helpers"):
        audit_mutation_call(call, "delete_zone", "entry-3")
    assert any("user=<automation/system>" in rec.message for rec in caplog.records)


_HELPERS = "custom_components.polygonal_zones.services.helpers"


def _target(editable: bool = True):
    entity = SimpleNamespace(
        _config_entry_id="entry-1", editable_file=editable, zone_urls=["/config/zones.json"]
    )
    return [entity], entity


def test_resolve_mutation_target_rate_limits_a_second_call_for_the_same_entry() -> None:
    """Every mutation action relies on this shared step for its rate limit."""
    reset_mutation_rate_limit()
    entities, entity = _target()
    call = SimpleNamespace(data={"device_id": "dev"}, context=SimpleNamespace(user_id="u"))

    with patch(f"{_HELPERS}.get_entities_from_device_id", return_value=entities):
        assert resolve_mutation_target(SimpleNamespace(), call, "add_new_zone") == (
            entities,
            entity,
        )
        with pytest.raises(RateLimited):
            resolve_mutation_target(SimpleNamespace(), call, "add_new_zone")
    reset_mutation_rate_limit()


def test_resolve_mutation_target_refuses_a_non_editable_file() -> None:
    reset_mutation_rate_limit()
    entities, _ = _target(editable=False)
    call = SimpleNamespace(data={"device_id": "dev"}, context=SimpleNamespace(user_id="u"))

    with (
        patch(f"{_HELPERS}.get_entities_from_device_id", return_value=entities),
        pytest.raises(ZoneFileNotEditable),
    ):
        resolve_mutation_target(SimpleNamespace(), call, "add_new_zone")
    reset_mutation_rate_limit()


def _hass(tmp_path: Path) -> SimpleNamespace:
    async def _executor_job(func, *args):
        return func(*args)

    return SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=_executor_job,
    )


async def test_modify_zone_file_serializes_concurrent_edits(tmp_path) -> None:
    """Two edits of one file must not interleave: each reads, changes and saves alone."""
    entities, entity = _target()
    entity.zone_urls = ["zones.json"]
    (tmp_path / "zones.json").write_text("{}")
    events: list[str] = []

    def fake_read(_config_dir, _uri):
        events.append("read")
        return json.dumps({"features": []})

    def fake_write(_content, _path):
        events.append("save")

    def mutate(_doc):
        events.append("mutate")

    with (
        patch(f"{_HELPERS}.read_local_file", new=fake_read),
        patch(f"{_HELPERS}.write_zones", new=fake_write),
        patch(f"{_HELPERS}.sync_entities_after_write", new=AsyncMock()),
    ):
        await asyncio.gather(
            modify_zone_file(_hass(tmp_path), entities, entity, mutate),
            modify_zone_file(_hass(tmp_path), entities, entity, mutate),
        )

    assert events == ["read", "mutate", "save", "read", "mutate", "save"]


@pytest.mark.parametrize(
    ("raised", "message"),
    [
        (OSError("disk"), "Failed to access zone file"),
        (ValueError("bad"), "Zone file content or path is invalid"),
    ],
)
async def test_modify_zone_file_maps_failures_to_invalid_zone_data(
    tmp_path, raised, message
) -> None:
    entities, entity = _target()
    entity.zone_urls = ["zones.json"]

    with (
        patch(f"{_HELPERS}.read_local_file", new=MagicMock(side_effect=raised)),
        pytest.raises(InvalidZoneData, match=message),
    ):
        await modify_zone_file(_hass(tmp_path), entities, entity, lambda _doc: None)


async def test_modify_zone_file_times_out_on_a_held_lock(tmp_path) -> None:
    """A lock held past the deadline is a translated error, not a hang."""
    entities, entity = _target()
    entity.zone_urls = ["zones.json"]
    (tmp_path / "zones.json").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    held = file_lock(tmp_path / "zones.json")
    held.acquire()
    try:
        with (
            patch(f"{_HELPERS}.LOCK_ACQUIRE_TIMEOUT", 0.01),
            pytest.raises(InvalidZoneData, match="Timed out waiting for zone file lock"),
        ):
            await modify_zone_file(_hass(tmp_path), entities, entity, lambda _doc: None)
    finally:
        held.release()


async def test_a_write_slower_than_the_lock_timeout_still_commits(tmp_path) -> None:
    """The timeout bounds the wait for the lock only — never the write.

    A write that outlives it used to raise a lock timeout after the file had
    already been written, inviting a retry that duplicated the change.
    """
    entities, entity = _target()
    entity.zone_urls = ["zones.json"]
    (tmp_path / "zones.json").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    real_write = write_zones

    def slow_write(content, path):
        time.sleep(0.05)
        real_write(content, path)

    def add_home(doc):
        doc["features"].append(
            {
                "type": "Feature",
                "properties": {"name": "Home"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                },
            }
        )

    with (
        patch(f"{_HELPERS}.LOCK_ACQUIRE_TIMEOUT", 0.01),
        patch(f"{_HELPERS}.write_zones", new=slow_write),
        patch(f"{_HELPERS}.sync_entities_after_write", new=AsyncMock()),
    ):
        await modify_zone_file(_hass(tmp_path), entities, entity, add_home)

    names = [
        f["properties"]["name"]
        for f in json.loads((tmp_path / "zones.json").read_text())["features"]
    ]
    assert names == ["Home"]


@pytest.mark.parametrize("document", [{}, [], {"features": None}, {"features": {}}])
def test_get_zone_idx_rejects_a_document_without_features(document) -> None:
    """A readable but malformed file is a validation failure, not a raw
    KeyError/TypeError escaping the service call."""
    with pytest.raises(InvalidZoneData):
        get_zone_idx("Home", document)


def test_get_zone_idx_skips_features_without_properties() -> None:
    document = {"features": [{"properties": None}, {"properties": {"name": "Home"}}]}

    assert get_zone_idx("Home", document) == 1


async def test_a_cancelled_mutation_cannot_lose_its_update(tmp_path) -> None:
    """Cancelling a mutation must not hand the file to the next one.

    The write runs in a thread and cannot be cancelled. When the lock was an
    asyncio one, the cancelled caller released it mid-write and the next
    mutation read the pre-write document, erasing the first change.
    """
    entities, entity = _target()
    entity.zone_urls = ["zones.json"]
    zones = tmp_path / "zones.json"
    zones.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    loop = asyncio.get_running_loop()

    async def real_executor(func, *args):
        return await loop.run_in_executor(None, func, *args)

    hass = SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=real_executor,
    )
    in_write = threading.Event()
    release = threading.Event()
    real_write = write_zones

    def blocking_write(content, path):
        in_write.set()
        release.wait(5)
        real_write(content, path)

    def add(name):
        def mutate(doc):
            doc["features"].append(
                {
                    "type": "Feature",
                    "properties": {"name": name},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                    },
                }
            )

        return mutate

    with (
        patch(f"{_HELPERS}.write_zones", new=blocking_write),
        patch(f"{_HELPERS}.sync_entities_after_write", new=AsyncMock()),
    ):
        first = asyncio.create_task(modify_zone_file(hass, entities, entity, add("Home")))
        assert await asyncio.to_thread(in_write.wait, 5)
        first.cancel()
        second = asyncio.create_task(modify_zone_file(hass, entities, entity, add("Work")))
        await asyncio.sleep(0.05)  # the second must still be waiting for the lock
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        await second

    names = [f["properties"]["name"] for f in json.loads(zones.read_text())["features"]]
    assert names == ["Home", "Work"]
