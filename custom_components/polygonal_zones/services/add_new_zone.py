"""definition file for the add new zone action."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall

from .errors import ZoneAlreadyExists
from .helpers import (
    ensure_unique_zone,
    get_zone_idx,
    modify_zone_file,
    parse_zone_feature,
    resolve_mutation_target,
    zone_features,
)


def action_builder(hass: HomeAssistant) -> Callable[[ServiceCall], Awaitable[None]]:
    """Builder for the add new zone action."""

    async def add_new_zone(call: ServiceCall) -> None:
        """Handle the service action call."""
        entities, entity = resolve_mutation_target(hass, call, "add_new_zone")
        new_zone = parse_zone_feature(call.data.get("zone"))
        new_name = new_zone["properties"]["name"]

        def add(existing_zones: dict[str, Any]) -> None:
            if get_zone_idx(new_name, existing_zones) is not None:
                raise ZoneAlreadyExists(f'The zone with name "{new_name}" already exists')
            features = zone_features(existing_zones)
            features.append(new_zone)
            # The id must be unique too: an add-on file always carries one, and
            # two features sharing it make home_zone_id ambiguous.
            ensure_unique_zone(features)

        await modify_zone_file(hass, entities, entity, add)

    return add_new_zone
