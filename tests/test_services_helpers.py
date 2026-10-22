"""Tests for services.helpers — get_entities_from_device_id branches."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
    return SimpleNamespace(config=SimpleNamespace(config_dir=str(tmp_path)))


async def test_modify_zone_file_serializes_concurrent_edits(tmp_path) -> None:
    """Two edits of one file must not interleave: each reads, changes and saves alone."""
    entities, entity = _target()
    entity.zone_urls = ["zones.json"]
    (tmp_path / "zones.json").write_text("{}")
    events: list[str] = []

    async def fake_load(_uri, _hass):
        events.append("read")
        await asyncio.sleep(0.01)  # a second caller would interleave here without the lock
        return json.dumps({"features": []})

    async def fake_save(*_args):
        events.append("save")

    def mutate(_doc):
        events.append("mutate")

    with (
        patch(f"{_HELPERS}.load_data", new=fake_load),
        patch(f"{_HELPERS}.save_zones", new=fake_save),
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
        (
            TimeoutError(),
            "Timed out waiting for zone file lock; another operation may be in progress",
        ),
    ],
)
async def test_modify_zone_file_maps_failures_to_invalid_zone_data(
    tmp_path, raised, message
) -> None:
    entities, entity = _target()
    entity.zone_urls = ["zones.json"]

    with (
        patch(f"{_HELPERS}.load_data", new=AsyncMock(side_effect=raised)),
        pytest.raises(InvalidZoneData, match=message),
    ):
        await modify_zone_file(_hass(tmp_path), entities, entity, lambda _doc: None)
