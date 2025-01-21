"""Config flow for Polygonal zones integrations."""

import logging
from types import MappingProxyType
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow as EntryConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ENTITIES
from homeassistant.data_entry_flow import callback
from homeassistant.helpers import selector
from homeassistant.helpers.selector import TextSelectorType

from .const import DOMAIN
from .utils.config_validation import are_urls_or_files

_LOGGER = logging.getLogger(__name__)


def build_create_flow(
    defaults: dict[str, Any] | MappingProxyType[str, Any] | None = None,
) -> vol.Schema:
    """Create the schema for the configuration flow."""
    defaults = defaults or {}

    # Basic section
    return vol.Schema(
        {
            vol.Required(
                "zone_urls",
                default=defaults.get("zone_urls", ["http://localhost:8000/zones.json"]),
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiple=True, type=TextSelectorType.URL),
            ),
            vol.Required(
                CONF_ENTITIES,
                default=defaults.get(CONF_ENTITIES, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["device_tracker"], multiple=True)
            ),
            vol.Optional(
                "prioritize_zone_files",
                default=defaults.get("prioritize_zone_files", False),
                description={"advanced": True},
            ): selector.BooleanSelector(),
            vol.Optional(
                "download_zones",
                default=defaults.get("download_zones", False),
                description={"advanced": True},
            ): selector.BooleanSelector(),
        }
    )


def build_options_flow(
    defaults: dict[str, Any] | MappingProxyType[str, Any] | None = None,
) -> vol.Schema:
    """Create the schema for the options flow.

    This function differs from the config schema by not adding the options for the entities.
    """
    return vol.Schema(
        {
            vol.Required(
                "zone_urls",
                default=defaults.get("zone_urls", ["http://localhost:8000/zones.json"]),
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    multiple=True,
                )
            ),
            vol.Required(
                "prioritize_zone_files",
                default=defaults.get("prioritize_zone_files", False),
            ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
        }
    )


class ConfigFlow(EntryConfigFlow, domain=DOMAIN):
    """Config flow handler."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Perform the initial step of the configuration flow, handling user input."""
        errors = {}
        if user_input is not None:
            errors = are_urls_or_files(user_input["zone_urls"])
            if errors:
                return self.async_create_entry(title="Polygonal Zones", data=user_input)

        user_input = user_input or {}

        return self.async_show_form(
            step_id="user",
            data_schema=build_create_flow(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Get the options flow handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    """Options flow handler."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize the OptionsFlowHandler with configuration data."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Perform the initial step of the options flow, handling user input."""
        if user_input is not None:
            errors = are_urls_or_files(user_input["zone_urls"])
            if not errors:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=user_input
                )
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=build_options_flow(self.config_entry.data),
            errors=errors,
        )
