"""definition file for the delete zone action."""

import asyncio
from collections.abc import Awaitable, Callable
import json

from homeassistant.core import HomeAssistant, ServiceCall

from ..utils.general import load_data, safe_config_path
from ..utils.local_zones import LOCK_ACQUIRE_TIMEOUT, get_file_lock, save_zones
from .errors import InvalidZoneData, ZoneDoesNotExists, ZoneFileNotEditable
from .helpers import get_entities_from_device_id, get_zone_idx, require_device_id


def action_builder(hass: HomeAssistant) -> Callable[[ServiceCall], Awaitable[None]]:
    """Builder for the delete zone action."""

    async def delete_new_zone(call: ServiceCall) -> None:
        """Handle the service action call."""
        device_id = require_device_id(call.data)
        entity = get_entities_from_device_id(device_id, hass)[0]

        if not entity.editable_file:
            raise ZoneFileNotEditable("Zone files of entity are not editable")

        filename = entity.zone_urls[0]
        filepath = safe_config_path(hass.config.config_dir, filename)
        new_name: str = call.data.get("zone_name") or ""
        if not new_name:
            raise ZoneDoesNotExists("Service call is missing 'zone_name'")

        try:
            async with asyncio.timeout(LOCK_ACQUIRE_TIMEOUT), get_file_lock(filepath):
                existing_zones = json.loads(await load_data(filename, hass))

                if (idx := get_zone_idx(new_name, existing_zones)) is None:
                    raise ZoneDoesNotExists(f'The zone with name "{new_name}" does not exists')

                del existing_zones["features"][idx]
                new_content = json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": existing_zones["features"],
                    }
                )
                await save_zones(new_content, filepath, hass)
        except TimeoutError as err:
            raise InvalidZoneData(
                f"Timed out waiting for lock on {filepath}; another operation may be in progress"
            ) from err

    return delete_new_zone
