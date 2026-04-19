"""Lifecycle tests for PolygonalZoneEntity beyond restore-on-restart."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.util import dt as dt_util
from shapely.geometry import Polygon

from custom_components.polygonal_zones.device_tracker import PolygonalZoneEntity
from custom_components.polygonal_zones.utils.zones import Zone, ZoneLoadResult


def _make_entity(zone_urls=None) -> PolygonalZoneEntity:
    return PolygonalZoneEntity(
        tracked_entity_id="device_tracker.phone",
        config_entry_id="entry-id",
        zone_urls=zone_urls or ["https://example.com/zones.json"],
        own_id="device_tracker.polygonal_zones_phone",
        prioritized_zone_files=False,
        editable_file=False,
    )


def _make_hass() -> SimpleNamespace:
    bus = SimpleNamespace(async_listen=MagicMock(return_value=lambda: None))

    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        bus=bus,
        states=SimpleNamespace(get=MagicMock(return_value=None)),
        async_create_task=MagicMock(),
        async_add_executor_job=aaej,
    )


async def test_set_available_logs_only_on_transition() -> None:
    entity = _make_entity()
    # Default _attr_available is True; first call to _set_available(True) is a no-op
    entity._set_available(True)
    entity._set_available(False)
    assert entity._attr_available is False
    entity._set_available(True)
    assert entity._attr_available is True


async def test_will_remove_releases_all_unsubs() -> None:
    entity = _make_entity()
    # Pre-populate the unsub handles with mocks
    entity._unsub = MagicMock()
    entity._unsub_at_started = MagicMock()
    entity._unsub_retry = MagicMock()

    await entity.async_will_remove_from_hass()

    assert entity._unsub is None
    assert entity._unsub_at_started is None
    assert entity._unsub_retry is None


async def test_update_location_sets_attributes() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._zones = [
        Zone(name="Home", geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), priority=0)
    ]

    await entity.update_location(latitude=0.5, longitude=0.5, gps_accuracy=10)

    assert entity._attr_location_name == "Home"
    assert entity._attr_extra_state_attributes["latitude"] == 0.5
    assert entity._attr_extra_state_attributes["longitude"] == 0.5
    assert entity._attr_extra_state_attributes["gps_accuracy"] == 10


async def test_update_location_outside_zones_marks_away() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._zones = [
        Zone(name="Home", geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), priority=0)
    ]
    await entity.update_location(latitude=10, longitude=10, gps_accuracy=1)
    assert entity._attr_location_name == "away"


async def test_update_location_expose_coordinates_false_omits_gps_attributes() -> None:
    """With the privacy toggle off, lat/lon/gps_accuracy are stripped from attributes."""
    entity = PolygonalZoneEntity(
        tracked_entity_id="device_tracker.phone",
        config_entry_id="entry-id",
        zone_urls=["https://example.com/zones.json"],
        own_id="device_tracker.polygonal_zones_phone",
        prioritized_zone_files=False,
        editable_file=False,
        expose_coordinates=False,
    )
    entity.hass = _make_hass()
    entity._zones = [
        Zone(name="Home", geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), priority=0)
    ]

    await entity.update_location(latitude=0.5, longitude=0.5, gps_accuracy=10)

    assert entity._attr_location_name == "Home"
    attrs = entity._attr_extra_state_attributes
    assert "latitude" not in attrs
    assert "longitude" not in attrs
    assert "gps_accuracy" not in attrs
    assert attrs["source_entity"] == "device_tracker.phone"
    assert attrs["zone_uris"] == ["https://example.com/zones.json"]


async def test_update_location_expose_coordinates_default_is_true() -> None:
    """Backward-compat: the constructor default keeps coordinates exposed."""
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._zones = [
        Zone(name="Home", geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), priority=0)
    ]

    await entity.update_location(latitude=0.5, longitude=0.5, gps_accuracy=10)

    attrs = entity._attr_extra_state_attributes
    assert attrs["latitude"] == 0.5
    assert attrs["longitude"] == 0.5
    assert attrs["gps_accuracy"] == 10


async def test_async_reload_zones_returns_payload_when_requested() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._async_write_ha_state = MagicMock()

    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    zones = [Zone(name="Home", geometry=polygon, priority=0)]

    call = SimpleNamespace(return_response=True)
    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=zones)),
        ),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
    ):
        result = await entity.async_reload_zones(call)

    assert isinstance(result, list)
    assert result[0]["name"] == "Home"
    # geometry is a list of (lon,lat) tuples
    assert isinstance(result[0]["geometry"], list)


async def test_async_reload_zones_empty_returns_empty_list() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._async_write_ha_state = MagicMock()
    entity._zones_urls = []  # no URIs so the all-fail branch isn't triggered

    call = SimpleNamespace(return_response=True)
    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=[])),
        ),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
    ):
        result = await entity.async_reload_zones(call)

    assert result == []


async def test_async_reload_zones_returns_none_when_response_not_requested() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._async_write_ha_state = MagicMock()
    entity._zones_urls = []

    call = SimpleNamespace(return_response=False)
    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=[])),
        ),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
    ):
        result = await entity.async_reload_zones(call)

    assert result is None


async def test_async_reload_zones_handles_failure() -> None:
    entity = _make_entity()
    entity.hass = _make_hass()

    call = SimpleNamespace(return_response=False)
    with patch(
        "custom_components.polygonal_zones.device_tracker.load_zones",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await entity.async_reload_zones(call)

    assert result is None


async def test_async_reload_zones_accepts_no_call() -> None:
    """Callable with ``call=None`` from the mutation-service path — no response."""
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._async_write_ha_state = MagicMock()

    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    zones = [Zone(name="Home", geometry=polygon, priority=0)]

    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=zones)),
        ),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
    ):
        result = await entity.async_reload_zones()

    assert result is None
    assert entity._zones == zones


async def test_async_reload_zones_sets_last_load_observability_on_success() -> None:
    """A successful reload updates last_zones_loaded_at + sets last_load_result='ok'."""
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._async_write_ha_state = MagicMock()

    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])

    assert entity._last_load_result == "never"
    assert entity._last_zones_loaded_at is None

    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=[Zone(name="Home", geometry=polygon)])),
        ),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
    ):
        await entity.async_reload_zones()

    assert entity._last_load_result == "ok"
    assert entity._last_zones_loaded_at is not None


async def test_async_reload_zones_clears_repair_issue_on_success() -> None:
    """Recovering via reload_zones clears the repair issue raised by a prior failure."""
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._async_write_ha_state = MagicMock()

    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])

    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=[Zone(name="Home", geometry=polygon)])),
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"
        ) as mock_delete,
    ):
        await entity.async_reload_zones()

    mock_delete.assert_called_once()
    _hass, domain, issue_id = mock_delete.call_args.args
    assert domain == "polygonal_zones"
    assert issue_id.startswith("zone_load_failed_")


async def test_async_reload_zones_warning_does_not_leak_entity_id(caplog) -> None:
    """Per-dpo: WARNING logs name entry_id only, never the source entity_id.

    Entity IDs such as ``device_tracker.alice_phone`` carry personal names and
    end up in external log aggregators. entry_id is an opaque string; it's
    sufficient for maintainer correlation via diagnostics.
    """
    entity = PolygonalZoneEntity(
        tracked_entity_id="device_tracker.alice_phone",
        config_entry_id="entry-xyz",
        zone_urls=["https://example.com/zones.json"],
        own_id="device_tracker.polygonal_zones_alice_phone",
        prioritized_zone_files=False,
        editable_file=False,
    )
    entity.hass = _make_hass()

    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.load_zones",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        caplog.at_level("WARNING", logger="custom_components.polygonal_zones.device_tracker"),
    ):
        await entity.async_reload_zones(SimpleNamespace(return_response=False))

    warnings = [rec.getMessage() for rec in caplog.records if rec.levelname == "WARNING"]
    assert warnings, "Expected at least one WARNING log from the failed reload"
    combined = " | ".join(warnings)
    assert "entry-xyz" in combined
    assert "alice_phone" not in combined
    assert "polygonal_zones_alice_phone" not in combined


async def test_async_reload_zones_marks_failed_on_exception() -> None:
    """A reload failure flips last_load_result to 'failed' without touching the timestamp."""
    entity = _make_entity()
    entity.hass = _make_hass()
    # Seed a prior-success state so we can confirm the timestamp is NOT overwritten.
    entity._last_load_result = "ok"
    prior_ts = entity._last_zones_loaded_at

    with patch(
        "custom_components.polygonal_zones.device_tracker.load_zones",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await entity.async_reload_zones()

    assert entity._last_load_result == "failed"
    assert entity._last_zones_loaded_at is prior_ts


async def test_update_location_exposes_load_observability_attributes() -> None:
    """last_load_result + last_zones_loaded_at are written to entity attributes."""
    entity = _make_entity()
    entity.hass = _make_hass()
    entity._last_load_result = "ok"
    entity._last_zones_loaded_at = dt_util.utcnow()
    entity._zones = [
        Zone(name="Home", geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), priority=0)
    ]

    await entity.update_location(latitude=0.5, longitude=0.5, gps_accuracy=10)

    attrs = entity._attr_extra_state_attributes
    assert attrs["last_load_result"] == "ok"
    assert attrs["last_zones_loaded_at"] is not None
    # ISO-8601 string with timezone
    assert "T" in attrs["last_zones_loaded_at"]
