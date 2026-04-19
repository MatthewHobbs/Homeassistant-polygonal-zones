"""The polygonal_zones integration."""

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .services import register_services
from .utils.general import safe_config_path
from .utils.local_zones import release_file_lock

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS: list[Platform] = [Platform.DEVICE_TRACKER]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Set up the polygonal_zones component."""
    hass.data.setdefault(DOMAIN, {})

    await register_services(
        hass,
        [
            "add_new_zone",
            "delete_zone",
            "edit_zone",
            "replace_all_zones",
        ],
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up polygonal_zones from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
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


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload polygonal_zones config entry — full unload/setup cycle.

    This is triggered by the options flow via ``add_update_listener`` and
    ensures the tracked-entity list is rebuilt so add/remove in options flow
    takes effect without a HA restart.
    """
    await hass.config_entries.async_reload(entry.entry_id)
