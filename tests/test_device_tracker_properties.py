"""Coverage for PolygonalZoneEntity property accessors and setup_entry."""

from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.polygonal_zones.device_tracker import (
    async_setup_entry,
)
from tests.helpers import make_entity as _make_entity


@pytest.fixture(autouse=True)
def _stub_schedule_initial_load():
    """async_setup_entry kicks off the shared load via async_at_started, which
    needs a real hass; these tests use stub hass objects, so no-op the schedule."""
    with patch(
        "custom_components.polygonal_zones.device_tracker.ZoneSource.async_schedule_initial_load"
    ):
        yield


def test_zones_property_starts_empty() -> None:
    entity = _make_entity()
    assert entity.zones == []


def test_editable_file_property_returns_constructor_value() -> None:
    assert _make_entity(editable_file=True).editable_file is True
    assert _make_entity(editable_file=False).editable_file is False


def test_zone_urls_property_returns_constructor_value() -> None:
    entity = _make_entity()
    assert entity.zone_urls == ["https://example.com/zones.json"]


def test_source_type_returns_gps() -> None:
    from homeassistant.components.device_tracker import SourceType

    assert _make_entity().source_type == SourceType.GPS


def test_location_name_starts_none() -> None:
    assert _make_entity().location_name is None


def test_should_poll_is_false() -> None:
    assert _make_entity().should_poll is False


def test_unique_id_combines_entry_and_entity() -> None:
    entity = _make_entity()
    assert entity.unique_id == "entry-id_device_tracker.phone"


def test_device_info_uses_entry_id_identifier() -> None:
    info = _make_entity().device_info
    assert info["identifiers"] == {("polygonal_zones", "entry-id")}
    assert info["name"] == "Polygonal Zones"


def test_private_read_properties_delegate_to_source() -> None:
    """The historical private attrs are read-only views over the shared source —
    services and diagnostics rely on this stable read interface."""
    from datetime import datetime

    from shapely.geometry import Polygon

    from custom_components.polygonal_zones.utils.zones import Zone
    from tests.helpers import make_source

    zones = [Zone(name="Home", geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), priority=0)]
    source = make_source(
        entry_id="entry-9",
        zone_urls=["https://x/z.json"],
        prioritize=True,
        editable_file=True,
        allow_private_urls=True,
        zones=zones,
    )
    source.last_load_result = "ok"
    source.last_load_failures = [("https://x/z.json", "boom")]
    source.last_zones_loaded_at = datetime(2026, 1, 1, tzinfo=UTC)
    entity = _make_entity(source=source)

    assert entity._config_entry_id == "entry-9"
    assert entity._zones == zones
    assert entity._zones_urls == ["https://x/z.json"]
    assert entity._editable_file is True
    assert entity._prioritize_zone_files is True
    assert entity._allow_private_urls is True
    assert entity._last_load_result == "ok"
    assert entity._last_load_failures == [("https://x/z.json", "boom")]
    assert entity._last_zones_loaded_at == datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def hass_with_setup(tmp_path):
    forward = AsyncMock()

    register_mock = MagicMock()
    platform = SimpleNamespace(async_register_entity_service=register_mock)

    hass = SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=AsyncMock(return_value=True),
        config_entries=SimpleNamespace(async_forward_entry_setups=forward),
    )
    return hass, platform


async def test_async_setup_entry_no_download(hass_with_setup) -> None:
    """async_setup_entry creates an entity per CONF_ENTITIES and stores in runtime_data."""
    from custom_components.polygonal_zones import PolygonalZonesData

    hass, platform = hass_with_setup

    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=PolygonalZonesData(),
        data={
            "zone_urls": ["https://example.com/zones.json"],
            "entities": ["device_tracker.alice", "device_tracker.bob"],
            "expose_coordinates": True,
        },
    )

    add_entities = MagicMock()

    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.entity_platform.async_get_current_platform",
            return_value=platform,
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.generate_entity_id",
            side_effect=lambda fmt, name, hass=None: fmt.format(name),
        ),
        # modern entry (expose_coordinates present) → setup clears any legacy
        # privacy issue via ir.async_delete_issue; patch it (stub hass has no
        # issue registry).
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
    ):
        await async_setup_entry(hass, entry, add_entities)

    assert add_entities.call_count == 1
    entities = add_entities.call_args.args[0]
    assert len(entities) == 2
    assert entry.runtime_data.entities == entities


async def test_async_setup_entry_clears_legacy_per_entity_load_issue(hass_with_setup) -> None:
    """Upgrade migration: the old per-entity ``zone_load_failed_<id>`` repair issue
    is cleared on setup now that the shared source uses a per-entry id."""
    from custom_components.polygonal_zones import PolygonalZonesData

    hass, platform = hass_with_setup
    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=PolygonalZonesData(),
        data={
            "zone_urls": ["https://example.com/zones.json"],
            "entities": ["device_tracker.alice"],
            "expose_coordinates": True,
        },
    )
    add_entities = MagicMock()
    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.entity_platform.async_get_current_platform",
            return_value=platform,
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.generate_entity_id",
            side_effect=lambda fmt, name, hass=None: fmt.format(name),
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"
        ) as del_issue,
    ):
        await async_setup_entry(hass, entry, add_entities)

    cleared = {call.args[2] for call in del_issue.call_args_list}
    assert "zone_load_failed_device_tracker.polygonal_zones_alice" in cleared


async def test_async_setup_entry_legacy_entry_raises_expose_coordinates_issue(
    hass_with_setup,
) -> None:
    """A legacy entry with no expose_coordinates key raises a privacy repair issue."""
    from custom_components.polygonal_zones import PolygonalZonesData

    hass, platform = hass_with_setup
    entry = SimpleNamespace(
        entry_id="entry-legacy",
        title="Legacy",
        runtime_data=PolygonalZonesData(),
        data={
            "zone_urls": ["https://example.com/zones.json"],
            "entities": ["device_tracker.alice"],
        },  # no expose_coordinates key -> legacy default True
    )
    add_entities = MagicMock()
    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.entity_platform.async_get_current_platform",
            return_value=platform,
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.generate_entity_id",
            side_effect=lambda fmt, name, hass=None: fmt.format(name),
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.ir.async_create_issue"
        ) as create_issue,
        # The per-entity legacy-load-issue migration cleanup also fires.
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
    ):
        await async_setup_entry(hass, entry, add_entities)

    create_issue.assert_called_once()
    assert create_issue.call_args.args[2] == "legacy_expose_coordinates_entry-legacy"


async def test_async_setup_entry_download_creates_local_path(hass_with_setup, tmp_path) -> None:
    """When download_zones is true, a local path is generated under config_dir/polygonal_zones/."""
    from custom_components.polygonal_zones import PolygonalZonesData

    hass, platform = hass_with_setup
    # async_add_executor_job(Path.exists) → False so download_zones is invoked
    hass.async_add_executor_job = AsyncMock(return_value=False)

    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=PolygonalZonesData(),
        data={
            "zone_urls": ["https://example.com/zones.json"],
            "entities": ["device_tracker.alice"],
            "download_zones": True,
            "expose_coordinates": True,
        },
    )

    add_entities = MagicMock()

    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.entity_platform.async_get_current_platform",
            return_value=platform,
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.generate_entity_id",
            side_effect=lambda fmt, name, hass=None: fmt.format(name),
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.download_zones",
            new=AsyncMock(),
        ) as download_mock,
        # modern entry → setup clears any legacy privacy issue (stub hass has
        # no issue registry, so patch the delete call).
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
    ):
        await async_setup_entry(hass, entry, add_entities)

    download_mock.assert_awaited_once()
    entities = add_entities.call_args.args[0]
    assert entities[0].editable_file is True
    assert entities[0].zone_urls == ["/polygonal_zones/entry-1.json"]


async def test_async_setup_entry_download_failure_raises_config_entry_not_ready(
    hass_with_setup, tmp_path
) -> None:
    """A failed initial download must raise ConfigEntryNotReady (HA retries setup)
    rather than propagating a raw error that hard-fails the entry with no entities."""
    from homeassistant.exceptions import ConfigEntryNotReady

    from custom_components.polygonal_zones import PolygonalZonesData

    hass, platform = hass_with_setup
    hass.async_add_executor_job = AsyncMock(return_value=False)  # file doesn't exist yet

    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=PolygonalZonesData(),
        data={
            "zone_urls": ["https://example.com/zones.json"],
            "entities": ["device_tracker.alice"],
            "download_zones": True,
            "expose_coordinates": True,
        },
    )
    add_entities = MagicMock()

    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.entity_platform.async_get_current_platform",
            return_value=platform,
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.download_zones",
            new=AsyncMock(side_effect=OSError("host unreachable")),
        ),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry, add_entities)

    # No entities were registered on the failed attempt.
    add_entities.assert_not_called()


async def test_async_setup_entry_download_unsupported_schema_raises_config_entry_error(
    hass_with_setup, tmp_path
) -> None:
    """An unsupported schema version is permanent — surface ConfigEntryError so HA
    stops retrying, rather than ConfigEntryNotReady which would spin forever."""
    from homeassistant.exceptions import ConfigEntryError

    from custom_components.polygonal_zones import PolygonalZonesData
    from custom_components.polygonal_zones.utils.zones import UnsupportedSchemaVersion

    hass, platform = hass_with_setup
    hass.async_add_executor_job = AsyncMock(return_value=False)  # file doesn't exist yet

    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=PolygonalZonesData(),
        data={
            "zone_urls": ["https://example.com/zones.json"],
            "entities": ["device_tracker.alice"],
            "download_zones": True,
            "expose_coordinates": True,
        },
    )
    add_entities = MagicMock()

    with (
        patch(
            "custom_components.polygonal_zones.device_tracker.entity_platform.async_get_current_platform",
            return_value=platform,
        ),
        patch(
            "custom_components.polygonal_zones.device_tracker.download_zones",
            new=AsyncMock(side_effect=UnsupportedSchemaVersion("schema 2 > max 1")),
        ),
        patch("custom_components.polygonal_zones.device_tracker.ir.async_delete_issue"),
        pytest.raises(ConfigEntryError),
    ):
        await async_setup_entry(hass, entry, add_entities)

    add_entities.assert_not_called()
