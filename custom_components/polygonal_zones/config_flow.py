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
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import CONF_CONSENT_CONFIRMED_AT, DOMAIN
from .utils.config_validation import validate_zone_urls

_LOGGER = logging.getLogger(__name__)

# Shown next to the tracking-consent checkbox on both the initial setup form
# and the reconfigure form (when a new tracker is being added).
_CONSENT_NOTICE = (
    "This integration continuously monitors the GPS position of the "
    "device_tracker entities you select. Please ensure everyone whose "
    "device is being tracked is aware of this."
)


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
            errors = await validate_zone_urls(
                user_input["zone_urls"],
                self.hass,
                allow_private_urls=user_input.get("allow_private_urls", False),
            )
            # Affirmative tracking consent: a required checkbox the installer must
            # tick. The integration continuously records the GPS position of the
            # selected device_tracker entities — possibly belonging to other
            # people — so an explicit opt-in is the lawful-basis floor, not a
            # passive notice. ``consent`` is a gate, not a stored setting.
            if not user_input.get("consent"):
                errors["consent"] = "consent_required"
            if not errors:
                user_input.pop("consent", None)
                # Persist evidence that consent was attested (GDPR Art. 7(1)
                # accountability). The tick itself is a gate, not a setting, but
                # a timestamp lets the operator demonstrate when it happened.
                user_input[CONF_CONSENT_CONFIRMED_AT] = dt_util.utcnow().isoformat()
                return self.async_create_entry(title="Polygonal Zones", data=user_input)

        user_input = user_input or {}

        return self.async_show_form(
            step_id="user",
            data_schema=build_create_flow(user_input, new_entry=True).extend(
                {vol.Required("consent", default=False): selector.BooleanSelector()}
            ),
            errors=errors,
            description_placeholders={"consent_notice": _CONSENT_NOTICE},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure flow — edit URLs, tracked entities, and flags in place.

        Adding a device_tracker that wasn't already covered introduces a new
        data subject, so the tracking-consent gate is re-applied whenever the
        submitted entity set grows. Editing URLs/flags on the existing set does
        not re-prompt (no new subject). See the consent notice in
        ``async_step_user`` for the lawful-basis rationale.
        """
        entry = self._get_reconfigure_entry()
        stored_entities = set(entry.data.get(CONF_ENTITIES, []))
        errors: dict[str, str] = {}
        adding_entities = False
        if user_input is not None:
            errors = await validate_zone_urls(
                user_input["zone_urls"],
                self.hass,
                allow_private_urls=user_input.get("allow_private_urls", False),
            )
            adding_entities = bool(set(user_input.get(CONF_ENTITIES, [])) - stored_entities)
            if adding_entities and not user_input.get("consent"):
                errors["consent"] = "consent_required"
            if not errors:
                data = {k: v for k, v in user_input.items() if k != "consent"}
                if adding_entities:
                    # New subject introduced — record a fresh attestation.
                    data[CONF_CONSENT_CONFIRMED_AT] = dt_util.utcnow().isoformat()
                elif entry.data.get(CONF_CONSENT_CONFIRMED_AT):
                    # No new subject; carry the prior attestation forward so it
                    # isn't dropped by the full data replacement below.
                    data[CONF_CONSENT_CONFIRMED_AT] = entry.data[CONF_CONSENT_CONFIRMED_AT]
                return self.async_update_reload_and_abort(entry, data=data)

        defaults = user_input if user_input is not None else dict(entry.data)
        schema = build_create_flow(defaults)
        description_placeholders: dict[str, str] | None = None
        if adding_entities:
            schema = schema.extend(
                {vol.Required("consent", default=False): selector.BooleanSelector()}
            )
            description_placeholders = {"consent_notice": _CONSENT_NOTICE}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
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
            errors = await validate_zone_urls(
                user_input["zone_urls"],
                self.hass,
                allow_private_urls=user_input.get("allow_private_urls", False),
            )
            if not errors:
                merged = {**self.config_entry.data, **user_input}
                self.hass.config_entries.async_update_entry(self.config_entry, data=merged)
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=build_options_flow(self.config_entry.data),
            errors=errors,
        )
