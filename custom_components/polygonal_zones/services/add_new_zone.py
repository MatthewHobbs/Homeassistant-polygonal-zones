"""definition file for the add new zone action."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall

from .errors import ZoneAlreadyExists
from .helpers import (
    modify_zone_file,
    parse_zone_feature,
    resolve_mutation_target,
    zone_already_defined,
)


def action_builder(hass: HomeAssistant) -> Callable[[ServiceCall], Awaitable[None]]:
    """Builder for the add new zone action."""

    async def add_new_zone(call: ServiceCall) -> None:
        """Handle the service action call."""
        entities, entity = resolve_mutation_target(hass, call, "add_new_zone")
        new_zone = parse_zone_feature(call.data.get("zone"))
        new_name = new_zone["properties"]["name"]

        def add(existing_zones: dict[str, Any]) -> None:
            if zone_already_defined(new_name, existing_zones):
                raise ZoneAlreadyExists(f'The zone with name "{new_name}" already exists')
            existing_zones["features"].append(new_zone)

        await modify_zone_file(hass, entities, entity, add)

    return add_new_zone
