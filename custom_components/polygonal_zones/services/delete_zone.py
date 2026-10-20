"""definition file for the delete zone action."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall

from .errors import ZoneDoesNotExists
from .helpers import get_zone_idx, modify_zone_file, resolve_mutation_target


def action_builder(hass: HomeAssistant) -> Callable[[ServiceCall], Awaitable[None]]:
    """Builder for the delete zone action."""

    async def delete_new_zone(call: ServiceCall) -> None:
        """Handle the service action call."""
        entities, entity = resolve_mutation_target(hass, call, "delete_zone")
        zone_name: str = call.data.get("zone_name") or ""
        if not zone_name:
            raise ZoneDoesNotExists("Service call is missing 'zone_name'")

        def delete(existing_zones: dict[str, Any]) -> None:
            if (idx := get_zone_idx(zone_name, existing_zones)) is None:
                raise ZoneDoesNotExists(f'The zone with name "{zone_name}" does not exist')
            del existing_zones["features"][idx]

        await modify_zone_file(hass, entities, entity, delete)

    return delete_new_zone
