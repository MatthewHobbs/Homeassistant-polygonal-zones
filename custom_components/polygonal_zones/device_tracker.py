"""Sensor for the polygonal_zones integration."""

from collections.abc import Callable, Coroutine
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITIES
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import entity_platform
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.start import async_at_started

from .const import (
    CONF_DOWNLOAD_ZONES,
    CONF_PRIORITIZE_ZONE_FILES,
    CONF_ZONES_URL,
    DOMAIN,
)
from .utils import event_should_trigger, get_locations_zone
from .utils.local_zones import download_zones
from .utils.zones import Zone, get_zones

_LOGGER = logging.getLogger(__name__)

_MAX_LOAD_ATTEMPTS = 5
_BASE_RETRY_DELAY = 30  # seconds; doubles on each attempt, capped at 10 min

# Push-based: zone resolution runs in response to source-tracker state_changed
# events, not on a polled schedule. Unlimited concurrency is safe.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the entities from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry.
        async_add_entities: A callable to add the entities.

    Returns:
        None

    """
    zone_uris: list[str] = entry.data.get(CONF_ZONES_URL) or []
    zone_uris = [zone_uri for zone_uri in zone_uris if zone_uri]
    prioritize: bool = bool(entry.data.get(CONF_PRIORITIZE_ZONE_FILES))

    editable_file = False

    if entry.data.get(CONF_DOWNLOAD_ZONES):
        download_path = Path(f"{hass.config.config_dir}/polygonal_zones/{entry.entry_id}.json")

        exists = await hass.async_add_executor_job(download_path.exists)
        if not exists:
            await download_zones(zone_uris, download_path, prioritize, hass)

        zone_uris = [f"/polygonal_zones/{entry.entry_id}.json"]
        editable_file = True

    entities = []
    for entity_id in entry.data.get(CONF_ENTITIES, []):
        entitiy_name = entity_id.split(".")[-1]
        base_id = generate_entity_id("device_tracker.polygonal_zones_{}", entitiy_name, hass=hass)

        entity = PolygonalZoneEntity(
            entity_id,
            entry.entry_id,
            zone_uris,
            base_id,
            prioritize,
            editable_file,
        )
        entities.append(entity)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "reload_zones",
        {},
        PolygonalZoneEntity.async_reload_zones,
        supports_response=SupportsResponse.OPTIONAL,
    )

    async_add_entities(entities, True)
    entry.runtime_data.entities = entities


class PolygonalZoneEntity(TrackerEntity, RestoreEntity):
    """Representation of a polygonal zone entity."""

    _attr_location_name: str | None = None
    _attr_latitude: float | None = None
    _attr_longitude: float | None = None
    _attr_gps_accuracy: float | None = None

    def __init__(
        self,
        tracked_entity_id: str,
        config_entry_id: str,
        zone_urls: list[str],
        own_id: str,
        prioritized_zone_files: bool,
        editable_file: bool,
    ) -> None:
        """Initialize the entity."""
        self._config_entry_id = config_entry_id
        self._entity_id = tracked_entity_id
        self._zones_urls = zone_urls
        self._prioritize_zone_files = prioritized_zone_files

        self._zones: list[Zone] = []
        self._unsub: Callable[[], None] | None = None
        self._unsub_at_started: Callable[[], None] | None = None
        self._unsub_retry: Callable[[], None] | None = None

        self.entity_id = own_id
        self._attr_unique_id = own_id

        self._attr_source_type = SourceType.GPS
        self._editable_file = editable_file

    async def async_added_to_hass(self) -> None:
        """Run when the entity is added to homeassistant.

        Registers the state listener and schedules zone initialization via
        ``async_at_started``, which fires immediately if Home Assistant is
        already running and otherwise waits for the start event. This avoids
        the race where ``hass.is_running`` flips between check and
        subscription.
        """
        last_state = await self.async_get_last_state()

        if last_state is not None:
            _LOGGER.debug("Restoring previous state for '%s'", self._entity_id)
            self._attr_location_name = last_state.state
            self._attr_extra_state_attributes = last_state.attributes

        async def _initialize_zones(_hass: HomeAssistant, attempt: int = 1) -> None:
            _LOGGER.debug(
                "Initializing zones for entity: %s (attempt %d)",
                self._entity_id,
                attempt,
            )
            try:
                self._zones = await get_zones(
                    self._zones_urls, self.hass, self._prioritize_zone_files
                )
            except Exception:
                if attempt < _MAX_LOAD_ATTEMPTS:
                    delay = min(600, _BASE_RETRY_DELAY * (2 ** (attempt - 1)))
                    _LOGGER.warning(
                        "Failed to load zones for entry=%s entity=%s (attempt %d/%d); retrying in %ds",
                        self._config_entry_id,
                        self._entity_id,
                        attempt,
                        _MAX_LOAD_ATTEMPTS,
                        delay,
                        exc_info=True,
                    )

                    def _retry(_now, _next_attempt=attempt + 1):
                        self._unsub_retry = None
                        self.hass.async_create_task(_initialize_zones(self.hass, _next_attempt))

                    self._unsub_retry = async_call_later(self.hass, delay, _retry)
                else:
                    _LOGGER.exception(
                        "Giving up loading zones for entry=%s entity=%s after %d attempts; "
                        "call the reload_zones service or reload the integration to retry",
                        self._config_entry_id,
                        self._entity_id,
                        _MAX_LOAD_ATTEMPTS,
                    )
                    self._set_available(False)
                    ir.async_create_issue(
                        self.hass,
                        DOMAIN,
                        f"zone_load_failed_{self._attr_unique_id}",
                        is_fixable=False,
                        severity=ir.IssueSeverity.WARNING,
                        translation_key="zone_load_failed",
                        translation_placeholders={"entity_id": str(self._attr_unique_id)},
                    )
                return
            # Successful load — clear any open repair issue from a prior failure.
            ir.async_delete_issue(self.hass, DOMAIN, f"zone_load_failed_{self._attr_unique_id}")
            self._set_available(True)
            await self._update_state()

        self._unsub_at_started = async_at_started(self.hass, _initialize_zones)

        self._unsub = self.hass.bus.async_listen(
            "state_changed", self._handle_state_change_builder()
        )

    async def async_update_config(self, config_entry: ConfigEntry) -> None:
        """Update the configuration of the entity."""
        self._zones_urls = config_entry.data.get(CONF_ZONES_URL) or []
        self._prioritize_zone_files = bool(config_entry.data.get(CONF_PRIORITIZE_ZONE_FILES))

        try:
            self._zones = await get_zones(self._zones_urls, self.hass, self._prioritize_zone_files)
        except Exception:
            _LOGGER.warning(
                "Failed to reload zones for entry=%s entity=%s; keeping previous zones",
                self._config_entry_id,
                self._entity_id,
                exc_info=True,
            )
            return

        self._set_available(True)
        await self._update_state()

    def _set_available(self, available: bool) -> None:
        """Toggle entity availability and log transitions at INFO."""
        if self._attr_available == available:
            return
        self._attr_available = available
        if available:
            _LOGGER.info(
                "Entity %s is available again (zones loaded)",
                self._attr_unique_id,
            )
        else:
            _LOGGER.info(
                "Entity %s is unavailable (zone loading exhausted retries)",
                self._attr_unique_id,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Handle cleanup when the entity is removed."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._unsub_at_started:
            self._unsub_at_started()
            self._unsub_at_started = None
        if self._unsub_retry:
            self._unsub_retry()
            self._unsub_retry = None

    async def update_location(self, latitude, longitude, gps_accuracy) -> None:
        """Update the location of the entity.

        Resolves the location to a zone via the executor so the (sync, CPU-bound)
        shapely geometry math doesn't block the event loop. Should only
        be called when latitude, longitude, or gps_accuracy actually changes.
        """
        zone = await self.hass.async_add_executor_job(
            get_locations_zone, latitude, longitude, gps_accuracy, self._zones
        )
        _LOGGER.debug("State of entity '%s' changed. new zone: %s", self._attr_unique_id, zone)
        self._attr_location_name = zone["name"] if zone is not None else "away"
        self._attr_extra_state_attributes = {
            "source_entity": self._entity_id,
            "latitude": latitude,
            "longitude": longitude,
            "gps_accuracy": gps_accuracy,
            "zone_uris": self._zones_urls,
        }

    def _handle_state_change_builder(
        self,
    ) -> Callable[[Any], Coroutine[Any, Any, None]]:
        """Create a callback for the state updates.

        This listener will check if it should operate on the event and then update the state.
        """

        async def func(event: Any) -> None:
            # check if it is the entity we should listen to.
            if event_should_trigger(event, self._entity_id):
                await self._update_state()

        return func

    async def _update_state(self) -> None:
        entity_state = self.hass.states.get(self._entity_id)
        if entity_state is not None and all(
            key in entity_state.attributes for key in ["latitude", "longitude", "gps_accuracy"]
        ):
            await self.update_location(
                entity_state.attributes["latitude"],
                entity_state.attributes["longitude"],
                entity_state.attributes["gps_accuracy"],
            )

            self.async_write_ha_state()

    async def async_reload_zones(self, call=None) -> dict | list | None:
        """Reload the zones.

        Called from two paths:
        - The ``polygonal_zones.reload_zones`` entity service, which passes
          a ``ServiceCall`` carrying ``return_response``.
        - Mutation service handlers (``add_new_zone`` / ``edit_zone`` /
          ``delete_zone`` / ``replace_all_zones``) which invoke it with no
          ``call`` to sync in-memory state after writing to disk.
        """
        try:
            self._zones = await get_zones(self._zones_urls, self.hass, self._prioritize_zone_files)
        except Exception:
            _LOGGER.warning(
                "Failed to reload zones for entry=%s entity=%s",
                self._config_entry_id,
                self._attr_unique_id,
                exc_info=True,
            )
            return None
        _LOGGER.debug("Reloaded zones of entity: %s", self._attr_unique_id)

        await self._update_state()
        if call is not None and call.return_response:
            return [
                {
                    "name": z.name,
                    "priority": z.priority,
                    "geometry": list(z.geometry.exterior.coords),
                }
                for z in self._zones
            ]
        return None

    @property
    def zones(self) -> list[Zone]:
        """The loaded zones."""
        return self._zones

    @property
    def editable_file(self) -> bool:
        """Is the zone file editable."""
        return self._editable_file

    @property
    def zone_urls(self) -> list[str]:
        """List of the urls where the zones are stored."""
        return self._zones_urls

    @property
    def source_type(self) -> SourceType:
        """The source type for the location service."""
        return self._attr_source_type

    @property
    def location_name(self) -> str | None:
        """Name of the zone the entity is in."""
        return self._attr_location_name

    @property
    def device_info(self) -> DeviceInfo | None:
        """Information about the polygonal_zones device."""
        return {
            "identifiers": {("polygonal_zones", self._config_entry_id)},
            "name": "Polygonal Zones",
            "manufacturer": "Polygonal Zones Community",
            "entry_type": DeviceEntryType.SERVICE,
        }

    @property
    def should_poll(self) -> bool:
        """Return False because entity will be updated via callback."""
        return False

    @property
    def unique_id(self) -> str:
        """Return a unique id for the entity."""
        return f"{self._config_entry_id}_{self._entity_id}"
