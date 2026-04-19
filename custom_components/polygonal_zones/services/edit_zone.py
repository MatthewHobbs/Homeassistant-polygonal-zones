"""definition file for the edit zone action."""

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
from .errors import InvalidZoneData, ZoneDoesNotExists, ZoneFileNotEditable
from .helpers import (
    audit_mutation_call,
    enforce_mutation_rate_limit,
    get_entities_from_device_id,
    get_zone_idx,
    parse_zone_feature,
    require_device_id,
    sync_entities_after_write,
)


def action_builder(hass: HomeAssistant) -> Callable[[ServiceCall], Awaitable[None]]:
    """Builder for the edit zone action."""

    async def edit_zone(call: ServiceCall) -> None:
        """Handle the service action call."""
        device_id = require_device_id(call.data)
        entities = get_entities_from_device_id(device_id, hass)
        entity = entities[0]

        audit_mutation_call(call, "edit_zone", entity._config_entry_id)
        enforce_mutation_rate_limit(entity._config_entry_id)

        if not entity.editable_file:
            raise ZoneFileNotEditable("Zone files of entity are not editable")

        old_name: str = call.data.get("zone_name") or ""
        if not old_name:
            raise ZoneDoesNotExists("Service call is missing 'zone_name'")
        new_zone = parse_zone_feature(call.data.get("zone"))
        filename = entity.zone_urls[0]

        try:
            filepath = safe_config_path(hass.config.config_dir, filename)
            async with asyncio.timeout(LOCK_ACQUIRE_TIMEOUT), get_file_lock(filepath):
                existing_zones = json.loads(await load_data(filename, hass))

                idx = get_zone_idx(old_name, existing_zones)
                if idx is None:
                    raise ZoneDoesNotExists(f'The zone with name "{old_name}" does not exists')

                existing_zones["features"][idx] = new_zone

                new_content = dump_feature_collection(
                    existing_zones["features"], existing=existing_zones
                )
                await save_zones(new_content, filepath, hass)
                await sync_entities_after_write(entities)
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

    return edit_zone
