"""Config flow for Polygonal zones integrations."""

import logging
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.config_entries import (
    ConfigFlow as EntryConfigFlow,
)
from homeassistant.const import CONF_ENTITIES
from homeassistant.data_entry_flow import callback
from homeassistant.helpers import selector
from homeassistant.helpers.selector import TextSelectorType
import voluptuous as vol

from .const import DOMAIN
from .utils.config_validation import validate_zone_urls

_LOGGER = logging.getLogger(__name__)


def build_create_flow(
    defaults: dict[str, Any] | MappingProxyType[str, Any] | None = None,
    *,
    new_entry: bool = False,
) -> vol.Schema:
    """Create the schema for the configuration flow.

    ``new_entry`` swaps the fallbacks for ``expose_coordinates`` and
    ``download_zones`` between the new-install default and the back-compat
    default for an existing entry created before the option existed:

    - ``expose_coordinates``: ``False`` for new installs (privacy-safe),
      ``True`` for reconfigured legacy entries.
    - ``download_zones``: ``True`` for new installs (CRUD works out of the
      box), ``False`` for reconfigured legacy entries — so opening the
      reconfigure form on an old read-only entry and submitting without
      touching the toggle does NOT silently convert it to a writable local
      snapshot.

    Keys already present in ``defaults`` always win over both fallbacks.
    """
    defaults = defaults or {}
    expose_fallback = not new_entry
    download_fallback = new_entry

    return vol.Schema(
        {
            vol.Required(
                "zone_urls",
                default=defaults.get("zone_urls", []),
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
                default=defaults.get("download_zones", download_fallback),
                description={"advanced": True},
            ): selector.BooleanSelector(),
            vol.Optional(
                "expose_coordinates",
                default=defaults.get("expose_coordinates", expose_fallback),
                description={"advanced": True},
            ): selector.BooleanSelector(),
            vol.Optional(
                "allow_private_urls",
                default=defaults.get("allow_private_urls", False),
                description={"advanced": True},
            ): selector.BooleanSelector(),
        }
    )


def build_options_flow(
    defaults: dict[str, Any] | MappingProxyType[str, Any] | None = None,
) -> vol.Schema:
    """Create the schema for the options flow.

    This function differs from the config schema by not adding the options for the entities.
    Existing entries created before the ``expose_coordinates`` option existed keep
    their current behaviour (coordinates exposed) until the user opts out.

    ``download_zones`` is exposed here too so it can be toggled after setup
    without a full reconfigure. Its fallback is ``False`` so a legacy entry
    that never stored the key stays read-only until the user opts in.
    """
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                "zone_urls",
                default=defaults.get("zone_urls", []),
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiple=True, type=TextSelectorType.URL)
            ),
            vol.Required(
                "prioritize_zone_files",
                default=defaults.get("prioritize_zone_files", False),
            ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
            vol.Required(
                "download_zones",
                default=defaults.get("download_zones", False),
            ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
            vol.Required(
                "expose_coordinates",
                default=defaults.get("expose_coordinates", True),
            ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
            vol.Required(
                "allow_private_urls",
                default=defaults.get("allow_private_urls", False),
            ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
        }
    )


class ConfigFlow(EntryConfigFlow, domain=DOMAIN):
    """Config flow handler."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Perform the initial step of the configuration flow, handling user input."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await validate_zone_urls(user_input["zone_urls"], self.hass)
            if not errors:
                return self.async_create_entry(title="Polygonal Zones", data=user_input)

        user_input = user_input or {}

        return self.async_show_form(
            step_id="user",
            data_schema=build_create_flow(user_input, new_entry=True),
            errors=errors,
            description_placeholders={
                "consent_notice": (
                    "This integration continuously monitors the GPS position of the "
                    "device_tracker entities you select. Please ensure everyone whose "
                    "device is being tracked is aware of this."
                )
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure flow — edit URLs, tracked entities, and flags in place."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await validate_zone_urls(user_input["zone_urls"], self.hass)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=user_input)

        defaults = user_input if user_input is not None else dict(entry.data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=build_create_flow(defaults),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Get the options flow handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(OptionsFlow):
    """Options flow handler.

    Home Assistant injects ``self.config_entry`` automatically; do not assign it.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Perform the initial step of the options flow, handling user input."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await validate_zone_urls(user_input["zone_urls"], self.hass)
            if not errors:
                merged = {**self.config_entry.data, **user_input}
                self.hass.config_entries.async_update_entry(self.config_entry, data=merged)
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=build_options_flow(self.config_entry.data),
            errors=errors,
        )
