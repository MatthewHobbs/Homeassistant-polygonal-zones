"""Custom errors for the polygonal zones integration."""

from homeassistant.exceptions import HomeAssistantError

from ..const import DOMAIN


class ZoneFileNotEditable(HomeAssistantError):
    """Error to signal that the source zone file for the entities is not editable."""

    translation_domain = DOMAIN
    translation_key = "zone_file_not_editable"


class ZoneAlreadyExists(HomeAssistantError):
    """Error to signal that the zone already exists in that file."""

    translation_domain = DOMAIN
    translation_key = "zone_already_exists"


class ZoneDoesNotExists(HomeAssistantError):
    """Error to signal that the zone does not exist in that file."""

    translation_domain = DOMAIN
    translation_key = "zone_does_not_exist"


class InvalidZoneData(HomeAssistantError):
    """Error to signal that the supplied zone payload failed validation."""

    translation_domain = DOMAIN
    translation_key = "invalid_zone_data"
