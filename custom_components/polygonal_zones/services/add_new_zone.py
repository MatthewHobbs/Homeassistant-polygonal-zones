"""definition file for the add new zone action."""

import asyncio
from collections.abc import Awaitable, Callable
import json

import aiohttp
from homeassistant.core import HomeAssistant, ServiceCall

from ..utils.general import load_data, safe_config_path
from ..utils.local_zones import (
    LOCK_ACQUIRE_TIMEOUT,
    dump_feature_collection,
    get_file_lock,
    save_zones,
)
from .errors import InvalidZoneData, ZoneAlreadyExists, ZoneFileNotEditable
from .helpers import (
    get_entities_from_device_id,
    parse_zone_feature,
    require_device_id,
    zone_already_defined,
)


def action_builder(hass: HomeAssistant) -> Callable[[ServiceCall], Awaitable[None]]:
    """Builder for the add new zone action."""

    async def add_new_zone(call: ServiceCall) -> None:
        """Handle the service action call."""
        device_id = require_device_id(call.data)
        entity = get_entities_from_device_id(device_id, hass)[0]

        if not entity.editable_file:
            raise ZoneFileNotEditable("Zone files of entity are not editable")

        new_zone = parse_zone_feature(call.data.get("zone"))
        new_name = new_zone["properties"]["name"]
        filename = entity.zone_urls[0]

        try:
            filepath = safe_config_path(hass.config.config_dir, filename)
            async with asyncio.timeout(LOCK_ACQUIRE_TIMEOUT), get_file_lock(filepath):
                existing_zones = json.loads(await load_data(filename, hass))

                if zone_already_defined(new_name, existing_zones):
                    raise ZoneAlreadyExists(f'The zone with name "{new_name}" already exists')

                existing_zones["features"].append(new_zone)
                new_content = dump_feature_collection(
                    existing_zones["features"], existing=existing_zones
                )
                await save_zones(new_content, filepath, hass)
        except TimeoutError as err:
            raise InvalidZoneData(
                f"Timed out waiting for lock on {filename}; another operation may be in progress"
            ) from err
        except aiohttp.ClientError as err:
            raise InvalidZoneData(f"Failed to fetch zone file: {err}") from err
        except OSError as err:
            raise InvalidZoneData(f"Failed to access zone file {filename}: {err}") from err
        except ValueError as err:
            raise InvalidZoneData(f"Zone file content or path is invalid: {err}") from err

    return add_new_zone
