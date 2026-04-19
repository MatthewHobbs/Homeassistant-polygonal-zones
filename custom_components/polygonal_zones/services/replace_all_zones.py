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
from .errors import InvalidZoneData, ZoneFileNotEditable
from .helpers import (
    audit_mutation_call,
    enforce_mutation_rate_limit,
    get_entities_from_device_id,
    parse_zone_collection,
    require_device_id,
    sync_entities_after_write,
)


def action_builder(
    hass: HomeAssistant,
) -> Callable[[ServiceCall], Awaitable[None]]:
    """Builder for the replace all zones action."""

    async def replace_all_zones(call: ServiceCall) -> None:
        """Handle the service action call."""
        device_id = require_device_id(call.data)
        entities = get_entities_from_device_id(device_id, hass)
        entity = entities[0]

        audit_mutation_call(call, "replace_all_zones", entity._config_entry_id)
        enforce_mutation_rate_limit(entity._config_entry_id)

        if not entity.editable_file:
            raise ZoneFileNotEditable("Zone files of entity are not editable")

        filename = entity.zone_urls[0]

        collection = parse_zone_collection(call.data.get("zone"))
        new_content = dump_feature_collection(collection["features"], existing=collection)

        try:
            filepath = safe_config_path(hass.config.config_dir, filename)
            async with asyncio.timeout(LOCK_ACQUIRE_TIMEOUT), get_file_lock(filepath):
                await save_zones(new_content, filepath, hass)
                await sync_entities_after_write(entities)
        except TimeoutError as err:
            raise InvalidZoneData(
                "Timed out waiting for zone file lock; another operation may be in progress"
            ) from err
        except OSError as err:
            raise InvalidZoneData("Failed to access zone file") from err
        except ValueError as err:
            raise InvalidZoneData("Zone file path is invalid") from err

    return replace_all_zones
