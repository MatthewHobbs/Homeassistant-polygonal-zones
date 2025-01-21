"""definition file for the add new zone action."""

from collections.abc import Callable
import json
from pathlib import Path

from homeassistant.core import HomeAssistant, ServiceCall

from ..utils.local_zones import save_zones
from .errors import ZoneFileNotEditable
from .helpers import get_entities_from_device_id


def action_builder(
    hass: HomeAssistant,
) -> Callable[[ServiceCall], None]:
    """Builder for the add new zone action."""

    async def replace_all_zones(call: ServiceCall) -> None:
        """Handle the service action call."""
        device_id = call.data.get("device_id")[0]
        entity = get_entities_from_device_id(device_id, hass)[0]

        if not entity.editable_file:
            raise ZoneFileNotEditable("Zone files of entity are not editable")

        # get the source path for the zones
        filename = entity.zone_urls[0]
        filepath = Path(f"{hass.config.config_dir}/{filename}")

        # get the name and data of the new zone
        new_zone = json.loads(call.data.get("zone"))
        new_content = json.dumps(new_zone)
        await save_zones(new_content, filepath, hass)

    return replace_all_zones
