"""module root for the services for the polygonal zones integration."""

import importlib

from homeassistant.core import HomeAssistant

from ..const import DOMAIN


async def register_services(hass: HomeAssistant, names: list[str], *, admin: bool = False) -> None:
    """Register the services for the polygonal zones integration.

    When ``admin`` is True, services are registered via
    ``async_register_admin_service`` so only HA admin users can invoke them.
    The four mutation services (``add_new_zone`` / ``edit_zone`` /
    ``delete_zone`` / ``replace_all_zones``) must be admin-only because they
    write to disk and can silently alter presence automations.
    """
    for name in names:
        module = await hass.async_add_executor_job(importlib.import_module, f".{name}", __package__)
        func = module.action_builder

        if admin:
            hass.services.async_register_admin_service(DOMAIN, name, func(hass))
        else:
            hass.services.async_register(DOMAIN, name, func(hass))
