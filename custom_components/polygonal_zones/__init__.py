"""The polygonal_zones integration."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .services import register_services
from .utils.general import safe_config_path
from .utils.local_zones import release_file_lock

if TYPE_CHECKING:
    from .device_tracker import PolygonalZoneEntity

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS: list[Platform] = [Platform.DEVICE_TRACKER]
_LOGGER = logging.getLogger(__name__)


@dataclass
class PolygonalZonesData:
    """Runtime data for a polygonal_zones config entry."""

    entities: list[PolygonalZoneEntity] = field(default_factory=list)


type PolygonalZonesConfigEntry = ConfigEntry[PolygonalZonesData]


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Set up the polygonal_zones component (registers global services)."""
    await register_services(
        hass,
        ["add_new_zone", "delete_zone", "edit_zone", "replace_all_zones"],
        admin=True,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PolygonalZonesConfigEntry) -> bool:
    """Set up polygonal_zones from a config entry.

    The platform's ``async_setup_entry`` populates ``entry.runtime_data.entities``;
    we just initialise the container and forward.
    """
    entry.runtime_data = PolygonalZonesData()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PolygonalZonesConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Drop the per-file lock so it doesn't accumulate across reloads.
        # If download_zones was never enabled, this is a harmless no-op.
        try:
            download_path = safe_config_path(
                hass.config.config_dir, f"polygonal_zones/{entry.entry_id}.json"
            )
        except ValueError:
            download_path = (
                Path(hass.config.config_dir) / "polygonal_zones" / f"{entry.entry_id}.json"
            )
        release_file_lock(download_path)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: PolygonalZonesConfigEntry) -> None:
    """Reload polygonal_zones config entry — full unload/setup cycle.

    Triggered by the options flow via ``add_update_listener`` so the tracked-entity
    list is rebuilt and add/remove in options flow takes effect without HA restart.
    """
    await hass.config_entries.async_reload(entry.entry_id)
