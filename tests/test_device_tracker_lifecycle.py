"""Lifecycle tests for PolygonalZoneEntity beyond restore-on-restart.

Zone loading/reload now happens on the shared ``ZoneSource``; the entity's
``async_reload_zones`` delegates to it, so reload tests patch
``zone_source.load_zones``.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
import pytest
from shapely.geometry import Polygon

from custom_components.polygonal_zones.utils.zones import Zone, ZoneLoadResult
from tests.helpers import make_entity as _make_entity
from tests.helpers import make_source

_HOME = Zone(name="Home", geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), priority=0)


def _make_hass() -> SimpleNamespace:
    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        states=SimpleNamespace(get=MagicMock(return_value=None)),
        async_create_task=MagicMock(),
        async_add_executor_job=aaej,
    )


async def test_set_available_logs_only_on_transition() -> None:
    entity = _make_entity()
    entity._set_available(True)
    entity._set_available(False)
    assert entity._attr_available is False
    entity._set_available(True)
    assert entity._attr_available is True


async def test_will_remove_releases_unsubs() -> None:
    entity = _make_entity()
    entity._unsub = MagicMock()
    entity._unsub_source = MagicMock()

    await entity.async_will_remove_from_hass()

    assert entity._unsub is None
    assert entity._unsub_source is None


async def test_update_location_sets_attributes() -> None:
    entity = _make_entity(zones=[_HOME])
    entity.hass = _make_hass()

    await entity.update_location(latitude=0.5, longitude=0.5, gps_accuracy=10)

    assert entity._attr_location_name == "Home"
    assert entity._attr_extra_state_attributes["latitude"] == 0.5
    assert entity._attr_extra_state_attributes["longitude"] == 0.5
    assert entity._attr_extra_state_attributes["gps_accuracy"] == 10


async def test_update_location_outside_zones_marks_away() -> None:
    entity = _make_entity(zones=[_HOME])
    entity.hass = _make_hass()
    await entity.update_location(latitude=10, longitude=10, gps_accuracy=1)
    assert entity._attr_location_name == "away"


async def test_update_location_expose_coordinates_false_omits_gps_attributes() -> None:
    """With the privacy toggle off, lat/lon/gps_accuracy are stripped from attributes."""
    entity = _make_entity(expose_coordinates=False, zones=[_HOME])
    entity.hass = _make_hass()

    await entity.update_location(latitude=0.5, longitude=0.5, gps_accuracy=10)

    assert entity._attr_location_name == "Home"
    attrs = entity._attr_extra_state_attributes
    assert "latitude" not in attrs
    assert "longitude" not in attrs
    assert "gps_accuracy" not in attrs
    # Non-location load diagnostics stay visible even with the toggle off.
    assert attrs["source_entity"] == "device_tracker.phone"
    assert "last_load_result" in attrs
    # But location-revealing attributes are gated with coordinates.
    assert "zone_uris" not in attrs
    assert "matched_zones" not in attrs


async def test_update_location_expose_coordinates_default_is_true() -> None:
    """Backward-compat: the constructor default keeps coordinates exposed."""
    entity = _make_entity(zones=[_HOME])
    entity.hass = _make_hass()

    await entity.update_location(latitude=0.5, longitude=0.5, gps_accuracy=10)

    attrs = entity._attr_extra_state_attributes
    assert attrs["latitude"] == 0.5
    assert attrs["longitude"] == 0.5
    assert attrs["gps_accuracy"] == 10
    # With coordinates on, the location-revealing attributes are published too.
    assert attrs["zone_uris"] == ["https://example.com/zones.json"]
    assert attrs["matched_zones"] == ["Home"]


def _patch_reload(zones=None, *, fail=False):
    """Patch the source's load_zones + issue-registry delete for a reload test."""
    load = (
        AsyncMock(side_effect=RuntimeError("boom"))
        if fail
        else AsyncMock(return_value=ZoneLoadResult(zones=zones or []))
    )
    return (
        patch("custom_components.polygonal_zones.zone_source.load_zones", new=load),
        patch("custom_components.polygonal_zones.zone_source.ir.async_delete_issue"),
    )


async def test_async_reload_zones_returns_payload_when_requested() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()

    load, del_issue = _patch_reload(zones=[_HOME])
    with load, del_issue:
        result = await entity.async_reload_zones(SimpleNamespace(return_response=True))

    assert isinstance(result, list)
    assert result[0]["name"] == "Home"
    assert isinstance(result[0]["geometry"], list)


async def test_async_reload_zones_empty_returns_empty_list() -> None:
    entity = _make_entity(zone_urls=[])  # no URIs so the all-fail branch isn't triggered
    entity.hass = _make_hass()

    load, del_issue = _patch_reload(zones=[])
    with load, del_issue:
        result = await entity.async_reload_zones(SimpleNamespace(return_response=True))

    assert result == []


async def test_async_reload_zones_returns_none_when_response_not_requested() -> None:
    entity = _make_entity(zone_urls=[])
    entity.hass = _make_hass()

    load, del_issue = _patch_reload(zones=[])
    with load, del_issue:
        result = await entity.async_reload_zones(SimpleNamespace(return_response=False))

    assert result is None


async def test_async_reload_zones_service_failure_raises() -> None:
    """A reload_zones *service* call that fails surfaces a HomeAssistantError."""
    entity = _make_entity()
    entity.hass = _make_hass()

    load, del_issue = _patch_reload(fail=True)
    with load, del_issue, pytest.raises(HomeAssistantError):
        await entity.async_reload_zones(SimpleNamespace(return_response=False))
    assert entity._source.last_load_result == "failed"


async def test_async_reload_zones_accepts_no_call() -> None:
    """Callable with ``call=None`` from the mutation-service path — no response."""
    entity = _make_entity()
    entity.hass = _make_hass()

    load, del_issue = _patch_reload(zones=[_HOME])
    with load, del_issue:
        result = await entity.async_reload_zones()

    assert result is None
    assert entity._source.zones == [_HOME]


async def test_async_reload_zones_service_is_rate_limited() -> None:
    """A second reload_zones *service* call within the window is refused; the
    internal (call=None) mutation-sync path is never rate-limited."""
    entity = _make_entity()
    entity.hass = _make_hass()

    load, del_issue = _patch_reload(zones=[_HOME])
    with load, del_issue:
        await entity.async_reload_zones(SimpleNamespace(return_response=False))  # first: ok
        with pytest.raises(HomeAssistantError):
            await entity.async_reload_zones(SimpleNamespace(return_response=False))  # too fast
        # Internal sync path is exempt from the rate limit.
        assert await entity.async_reload_zones() is None


async def test_async_reload_zones_multi_entity_same_call_not_rate_limited() -> None:
    """One service call fans out to every targeted entity (same context id); those
    must all proceed — only *distinct* calls are rate-limited."""
    entity_a = _make_entity(own_id="device_tracker.polygonal_zones_a")
    entity_b = _make_entity(source=entity_a._source, own_id="device_tracker.polygonal_zones_b")
    entity_a.hass = entity_b.hass = _make_hass()

    call = SimpleNamespace(return_response=False, context=SimpleNamespace(id="one-call"))
    load, del_issue = _patch_reload(zones=[_HOME])
    with load, del_issue:
        await entity_a.async_reload_zones(call)  # first entity in the call
        await entity_b.async_reload_zones(call)  # same call, same entry — must not trip
        # A *different* call to the same entry within the window is refused.
        with pytest.raises(HomeAssistantError):
            await entity_a.async_reload_zones(
                SimpleNamespace(return_response=False, context=SimpleNamespace(id="other-call"))
            )


async def test_async_reload_zones_sets_last_load_observability_on_success() -> None:
    """A successful reload updates last_zones_loaded_at + sets last_load_result='ok'."""
    entity = _make_entity(loaded_ok=False)
    entity.hass = _make_hass()
    assert entity._last_load_result == "never"
    assert entity._last_zones_loaded_at is None

    load, del_issue = _patch_reload(zones=[_HOME])
    with load, del_issue:
        await entity.async_reload_zones()

    assert entity._last_load_result == "ok"
    assert entity._last_zones_loaded_at is not None


async def test_async_reload_zones_clears_repair_issue_on_success() -> None:
    """Recovering via reload_zones clears the repair issue raised by a prior failure."""
    entity = _make_entity()
    entity.hass = _make_hass()

    load = AsyncMock(return_value=ZoneLoadResult(zones=[_HOME]))
    with (
        patch("custom_components.polygonal_zones.zone_source.load_zones", new=load),
        patch("custom_components.polygonal_zones.zone_source.ir.async_delete_issue") as mock_delete,
    ):
        await entity.async_reload_zones()

    mock_delete.assert_called_once()
    _hass, domain, issue_id = mock_delete.call_args.args
    assert domain == "polygonal_zones"
    assert issue_id == "zone_load_failed_entry-id"


async def test_async_reload_zones_warning_does_not_leak_entity_id(caplog) -> None:
    """WARNING logs name entry_id only, never the source entity_id."""
    source = make_source(entry_id="entry-xyz")
    entity = _make_entity(
        source=source,
        tracked_entity_id="device_tracker.alice_phone",
        own_id="device_tracker.polygonal_zones_alice_phone",
    )
    entity.hass = _make_hass()

    load, del_issue = _patch_reload(fail=True)
    with (
        load,
        del_issue,
        caplog.at_level("WARNING", logger="custom_components.polygonal_zones.device_tracker"),
        pytest.raises(HomeAssistantError),
    ):
        await entity.async_reload_zones(SimpleNamespace(return_response=False))

    warnings = [rec.getMessage() for rec in caplog.records if rec.levelname == "WARNING"]
    assert warnings, "Expected at least one WARNING log from the failed reload"
    combined = " | ".join(warnings)
    assert "entry-xyz" in combined
    assert "alice_phone" not in combined


async def test_async_reload_zones_marks_failed_on_exception() -> None:
    """A reload failure flips last_load_result to 'failed' without touching the timestamp."""
    entity = _make_entity()
    entity.hass = _make_hass()
    # Seed a prior-success state so we can confirm the timestamp is NOT overwritten.
    entity._source.last_load_result = "ok"
    prior_ts = dt_util.utcnow()
    entity._source.last_zones_loaded_at = prior_ts

    load, del_issue = _patch_reload(fail=True)
    with load, del_issue:
        # call=None (mutation-sync path) → swallowed, no raise.
        result = await entity.async_reload_zones()

    assert result is None
    assert entity._last_load_result == "failed"
    assert entity._last_zones_loaded_at is prior_ts


async def test_update_location_exposes_load_observability_attributes() -> None:
    """last_load_result + last_zones_loaded_at are written to entity attributes."""
    source = make_source(zones=[_HOME])
    source.last_load_result = "ok"
    source.last_zones_loaded_at = dt_util.utcnow()
    entity = _make_entity(source=source)
    entity.hass = _make_hass()

    await entity.update_location(latitude=0.5, longitude=0.5, gps_accuracy=10)

    attrs = entity._attr_extra_state_attributes
    assert attrs["last_load_result"] == "ok"
    assert attrs["last_zones_loaded_at"] is not None
    assert "T" in attrs["last_zones_loaded_at"]
