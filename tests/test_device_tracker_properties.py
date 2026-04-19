"""Coverage for PolygonalZoneEntity property accessors and setup_entry."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.polygonal_zones.const import DOMAIN
from custom_components.polygonal_zones.device_tracker import (
    PolygonalZoneEntity,
    async_setup_entry,
)


def _make_entity(editable_file: bool = False) -> PolygonalZoneEntity:
    return PolygonalZoneEntity(
        tracked_entity_id="device_tracker.phone",
        config_entry_id="entry-id",
        zone_urls=["https://example.com/zones.json"],
        own_id="device_tracker.polygonal_zones_phone",
        prioritized_zone_files=False,
        editable_file=editable_file,
    )


def test_zones_property_starts_empty() -> None:
    entity = _make_entity()
    assert entity.zones.empty


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


@pytest.fixture
def hass_with_setup(tmp_path):
    forward = AsyncMock()

    register_mock = MagicMock()
    platform = SimpleNamespace(async_register_entity_service=register_mock)

    hass = SimpleNamespace(
        data={DOMAIN: {}},
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=AsyncMock(return_value=True),
        config_entries=SimpleNamespace(async_forward_entry_setups=forward),
    )
    return hass, platform


async def test_async_setup_entry_no_download(hass_with_setup) -> None:
    """async_setup_entry creates an entity per CONF_ENTITIES and stores them in hass.data."""
    hass, platform = hass_with_setup

    entry = SimpleNamespace(
        entry_id="entry-1",
        data={
            "zone_urls": ["https://example.com/zones.json"],
            "entities": ["device_tracker.alice", "device_tracker.bob"],
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
    ):
        await async_setup_entry(hass, entry, add_entities)

    assert add_entities.call_count == 1
    entities = add_entities.call_args.args[0]
    assert len(entities) == 2
    assert hass.data[DOMAIN]["entry-1"] == entities


async def test_async_setup_entry_download_creates_local_path(hass_with_setup, tmp_path) -> None:
    """When download_zones is true, a local path is generated under config_dir/polygonal_zones/."""
    hass, platform = hass_with_setup
    # async_add_executor_job(Path.exists) → False so download_zones is invoked
    hass.async_add_executor_job = AsyncMock(return_value=False)

    entry = SimpleNamespace(
        entry_id="entry-1",
        data={
            "zone_urls": ["https://example.com/zones.json"],
            "entities": ["device_tracker.alice"],
            "download_zones": True,
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
    ):
        await async_setup_entry(hass, entry, add_entities)

    download_mock.assert_awaited_once()
    entities = add_entities.call_args.args[0]
    assert entities[0].editable_file is True
    assert entities[0].zone_urls == ["/polygonal_zones/entry-1.json"]
