"""Input schemas for the zone-editing services, matching services.yaml.

Without one, `async_register_admin_service` falls back to a schema that refuses every
key, so the service rejects its own fields before the handler runs.
"""

from typing import TYPE_CHECKING

from homeassistant.helpers import config_validation as cv

if TYPE_CHECKING:
    # HA >= 2026.9 types schemas as probatio, not voluptuous. Runtime keeps
    # `voluptuous`, which HA aliases to probatio. Use only names both have.
    import probatio as vol
else:
    import voluptuous as vol

# The device selector sends one id; the handlers also accept a list.
_DEVICE_ID = {vol.Required("device_id"): vol.Any(cv.string, [cv.string])}
# GeoJSON as text: a Feature, or a FeatureCollection for replace_all_zones.
_ZONE = {vol.Required("zone"): cv.string}
_ZONE_NAME = {vol.Required("zone_name"): cv.string}

SERVICE_SCHEMAS = {
    "add_new_zone": vol.Schema({**_DEVICE_ID, **_ZONE}),
    "edit_zone": vol.Schema({**_DEVICE_ID, **_ZONE_NAME, **_ZONE}),
    "delete_zone": vol.Schema({**_DEVICE_ID, **_ZONE_NAME}),
    "replace_all_zones": vol.Schema({**_DEVICE_ID, **_ZONE}),
}
