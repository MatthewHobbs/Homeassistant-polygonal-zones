"""definition file for the replace all zones action."""

from collections.abc import Awaitable, Callable

from homeassistant.core import HomeAssistant, ServiceCall

from ..utils.general import safe_config_path
from ..utils.local_zones import dump_feature_collection, write_zones
from .helpers import (
    ensure_loadable,
    ensure_unique_zone,
    locked,
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
        ensure_unique_zone(collection["features"])
        new_content = dump_feature_collection(collection["features"], existing=collection)

        # Unlike the other actions this never reads the existing file: replacing
        # a corrupt file is exactly when it is needed.
        def _replace() -> None:
            path = safe_config_path(hass.config.config_dir, entity.zone_urls[0])
            with locked(path):
                ensure_loadable(new_content)
                write_zones(new_content, path)

        with zone_file_errors("Zone file path is invalid"):
            await hass.async_add_executor_job(_replace)
        await sync_entities_after_write(entities)

    return replace_all_zones
