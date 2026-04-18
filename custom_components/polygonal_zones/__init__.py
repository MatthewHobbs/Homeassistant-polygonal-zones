"""The polygonal_zones integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .services import register_services

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
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload polygonal_zones config entry — full unload/setup cycle.

    This is triggered by the options flow via ``add_update_listener`` and
    ensures the tracked-entity list is rebuilt so add/remove in options flow
    takes effect without a HA restart.
    """
    await hass.config_entries.async_reload(entry.entry_id)
