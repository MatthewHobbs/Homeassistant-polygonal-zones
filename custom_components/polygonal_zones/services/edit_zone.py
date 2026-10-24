"""definition file for the edit zone action."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall

from .errors import ZoneDoesNotExists
from .helpers import (
    ensure_unique_zone,
    get_zone_idx,
    modify_zone_file,
    parse_zone_feature,
    resolve_mutation_target,
    zone_features,
)


def action_builder(hass: HomeAssistant) -> Callable[[ServiceCall], Awaitable[None]]:
    """Builder for the edit zone action."""

    async def edit_zone(call: ServiceCall) -> None:
        """Handle the service action call."""
        entities, entity = resolve_mutation_target(hass, call, "edit_zone")
        old_name: str = call.data.get("zone_name") or ""
        if not old_name:
            raise ZoneDoesNotExists("Service call is missing 'zone_name'")
        new_zone = parse_zone_feature(call.data.get("zone"))

        def replace(existing_zones: dict[str, Any]) -> None:
            idx = get_zone_idx(old_name, existing_zones)
            if idx is None:
                raise ZoneDoesNotExists(f'The zone with name "{old_name}" does not exist')
            features = zone_features(existing_zones)
            features[idx] = new_zone
            # Renaming one zone to another's name, or reusing its id, would make
            # the target ambiguous for every later action.
            ensure_unique_zone(features)

        await modify_zone_file(hass, entities, entity, replace)

    return edit_zone
