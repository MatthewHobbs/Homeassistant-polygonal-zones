"""Tests for services.helpers — get_entities_from_device_id branches."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.polygonal_zones.const import DOMAIN
from custom_components.polygonal_zones.services.errors import InvalidZoneData, RateLimited
from custom_components.polygonal_zones.services.helpers import (
    audit_mutation_call,
    enforce_mutation_rate_limit,
    get_entities_from_device_id,
    get_zone_idx,
    require_device_id,
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


async def test_sync_entities_after_write_calls_reload_on_each() -> None:
    """Every entity under a single entry must be re-synced after a mutation write."""
    a = SimpleNamespace(async_reload_zones=AsyncMock())
    b = SimpleNamespace(async_reload_zones=AsyncMock())

    await sync_entities_after_write([a, b])

    a.async_reload_zones.assert_awaited_once_with()
    b.async_reload_zones.assert_awaited_once_with()


async def test_sync_entities_after_write_empty_list_is_noop() -> None:
    """An empty entity list is a clean no-op, not an error."""
    await sync_entities_after_write([])


# ---------- enforce_mutation_rate_limit ----------


def test_rate_limit_first_call_passes() -> None:
    """A fresh entry_id is always allowed through."""
    enforce_mutation_rate_limit("fresh-entry-1")


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


def test_rate_limit_zero_interval_effectively_disables_gate() -> None:
    """A min_interval of 0 lets back-to-back calls through (useful for tests)."""
    enforce_mutation_rate_limit("elastic-entry", min_interval=0)
    enforce_mutation_rate_limit("elastic-entry", min_interval=0)


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
