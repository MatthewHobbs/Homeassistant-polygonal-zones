"""module root for the services for the polygonal zones integration."""

import importlib

from homeassistant.core import HomeAssistant

from ..const import DOMAIN


async def register_services(hass: HomeAssistant, names: list[str]) -> None:
    """Register the services for the polygonal zones integration."""
    for name in names:
        # load the builder
        module = await hass.async_add_executor_job(
            importlib.import_module, f".{name}", __package__
        )
        func = getattr(module, "action_builder")

        # register the action
        hass.services.async_register(DOMAIN, name, func(hass))
