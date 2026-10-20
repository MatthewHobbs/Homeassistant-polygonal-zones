"""definition file for the replace all zones action."""

import asyncio
from collections.abc import Awaitable, Callable

from homeassistant.core import HomeAssistant, ServiceCall

from ..utils.general import safe_config_path
from ..utils.local_zones import (
    LOCK_ACQUIRE_TIMEOUT,
    dump_feature_collection,
    get_file_lock,
    save_zones,
)
from .helpers import (
    parse_zone_collection,
    resolve_mutation_target,
    sync_entities_after_write,
    zone_file_errors,
)


def action_builder(
    hass: HomeAssistant,
) -> Callable[[ServiceCall], Awaitable[None]]:
    """Builder for the replace all zones action."""

    async def replace_all_zones(call: ServiceCall) -> None:
        """Handle the service action call."""
        entities, entity = resolve_mutation_target(hass, call, "replace_all_zones")
        collection = parse_zone_collection(call.data.get("zone"))
        new_content = dump_feature_collection(collection["features"], existing=collection)

        # Unlike the other actions this never reads the existing file: replacing
        # a corrupt file is exactly when it is needed.
        with zone_file_errors("Zone file path is invalid"):
            filepath = safe_config_path(hass.config.config_dir, entity.zone_urls[0])
            async with asyncio.timeout(LOCK_ACQUIRE_TIMEOUT), get_file_lock(filepath):
                await save_zones(new_content, filepath, hass)
                await sync_entities_after_write(entities)

    return replace_all_zones
