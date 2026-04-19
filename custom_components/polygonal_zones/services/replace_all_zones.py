"""definition file for the replace all zones action."""

import asyncio
from collections.abc import Awaitable, Callable
import json

from homeassistant.core import HomeAssistant, ServiceCall

from ..utils.general import safe_config_path
from ..utils.local_zones import LOCK_ACQUIRE_TIMEOUT, get_file_lock, save_zones
from .errors import InvalidZoneData, ZoneFileNotEditable
from .helpers import (
    get_entities_from_device_id,
    parse_zone_collection,
    require_device_id,
)


def action_builder(
    hass: HomeAssistant,
) -> Callable[[ServiceCall], Awaitable[None]]:
    """Builder for the replace all zones action."""

    async def replace_all_zones(call: ServiceCall) -> None:
        """Handle the service action call."""
        device_id = require_device_id(call.data)
        entity = get_entities_from_device_id(device_id, hass)[0]

        if not entity.editable_file:
            raise ZoneFileNotEditable("Zone files of entity are not editable")

        filename = entity.zone_urls[0]
        filepath = safe_config_path(hass.config.config_dir, filename)

        collection = parse_zone_collection(call.data.get("zone"))
        new_content = json.dumps(collection)

        try:
            async with asyncio.timeout(LOCK_ACQUIRE_TIMEOUT), get_file_lock(filepath):
                await save_zones(new_content, filepath, hass)
        except TimeoutError as err:
            raise InvalidZoneData(
                f"Timed out waiting for lock on {filepath}; another operation may be in progress"
            ) from err

    return replace_all_zones
