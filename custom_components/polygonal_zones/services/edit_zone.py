"""definition file for the edit zone action."""

import asyncio
from collections.abc import Callable
import json

from homeassistant.core import HomeAssistant, ServiceCall

from ..utils.general import load_data, safe_config_path
from ..utils.local_zones import LOCK_ACQUIRE_TIMEOUT, get_file_lock, save_zones
from .errors import InvalidZoneData, ZoneDoesNotExists, ZoneFileNotEditable
from .helpers import (
    get_entities_from_device_id,
    get_zone_idx,
    parse_zone_feature,
    require_device_id,
)


def action_builder(hass: HomeAssistant) -> Callable[[ServiceCall], None]:
    """Builder for the edit zone action."""

    async def edit_zone(call: ServiceCall) -> None:
        """Handle the service action call."""
        device_id = require_device_id(call.data)
        entity = get_entities_from_device_id(device_id, hass)[0]

        if not entity.editable_file:
            raise ZoneFileNotEditable("Zone files of entity are not editable")

        filename = entity.zone_urls[0]
        filepath = safe_config_path(hass.config.config_dir, filename)
        old_name = call.data.get("zone_name")
        new_zone = parse_zone_feature(call.data.get("zone"))

        try:
            async with asyncio.timeout(LOCK_ACQUIRE_TIMEOUT), get_file_lock(filepath):
                existing_zones = json.loads(await load_data(filename, hass))

                idx = get_zone_idx(old_name, existing_zones)
                if idx is None:
                    raise ZoneDoesNotExists(f'The zone with name "{old_name}" does not exists')

                del existing_zones["features"][idx]
                existing_zones["features"].append(new_zone)

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

    return edit_zone
