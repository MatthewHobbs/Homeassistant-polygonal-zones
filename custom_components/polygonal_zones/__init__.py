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

    # register all the actions
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
    if entry.entry_id in hass.data[DOMAIN]:
        return True

    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform.DEVICE_TRACKER]
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["device_tracker"]
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload polygonal_zones config entry."""
    entities = hass.data[DOMAIN][entry.entry_id]
    for entity in entities:
        await entity.async_update_config(entry)
