"""Constants for polygonal zones integration."""

CONF_DOWNLOAD_ZONES = "download_zones"
CONF_ENSURE_UNIQUE_ENTITIES = "ensure_unique_entities"
CONF_EXPOSE_COORDINATES = "expose_coordinates"
CONF_PRIORITIZE_ZONE_FILES = "prioritize_zone_files"
CONF_ZONES_URL = "zone_urls"

DOMAIN = "polygonal_zones"

# Polygonal-zones file-format version (see docs/ZONES_FORMAT.md).
# Producers stamp ``polygonal_zones.schema_version`` on write; the reader
# treats a missing member as implicit 1 and rejects any value greater than
# MAX_SUPPORTED_SCHEMA_VERSION with a clear error.
SCHEMA_VERSION = 1
MAX_SUPPORTED_SCHEMA_VERSION = 1
