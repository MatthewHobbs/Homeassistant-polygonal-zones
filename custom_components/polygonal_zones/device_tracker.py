"""Sensor for the polygonal_zones integration."""

from collections.abc import Callable, Coroutine
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITIES, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import entity_platform
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_ALLOW_PRIVATE_URLS,
    CONF_DOWNLOAD_ZONES,
    CONF_EXPOSE_COORDINATES,
    CONF_PRIORITIZE_ZONE_FILES,
    CONF_ZONES_URL,
    DOMAIN,
)
from .utils import event_should_trigger, get_locations_zone
from .utils.geometry import exterior_coords
from .utils.local_zones import download_zones
from .utils.zones import UnsupportedSchemaVersion, Zone
from .zone_source import ZoneSource

_LOGGER = logging.getLogger(__name__)

# Push-based: zone resolution runs in response to source-tracker state_changed
# events, not on a polled schedule. Unlimited concurrency is safe.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the entities from a config entry.

    Builds one entry-scoped :class:`ZoneSource` (a single fetch/parse + load
    lifecycle shared by every mirror), then a thin mirror entity per tracked
    ``device_tracker`` that reads from it.
    """
    zone_uris: list[str] = entry.data.get(CONF_ZONES_URL) or []
    zone_uris = [zone_uri for zone_uri in zone_uris if zone_uri]
    prioritize: bool = bool(entry.data.get(CONF_PRIORITIZE_ZONE_FILES))
    # Existing entries (upgraded from < v1.11) have no stored value; default
    # to True to preserve their current behaviour. New entries default to
    # False via the config flow (privacy by default).
    expose_coordinates: bool = bool(entry.data.get(CONF_EXPOSE_COORDINATES, True))
    # Opt-in SSRF relaxation for LAN addon installs. Default strict; user
    # flips the toggle in config/options. See issue #28.
    allow_private_urls: bool = bool(entry.data.get(CONF_ALLOW_PRIVATE_URLS, False))

    # Legacy entries created before the privacy option existed have no stored
    # CONF_EXPOSE_COORDINATES and default to True — they are silently exposing
    # and recording GPS coordinates. Raise a repair issue so the user can review
    # and opt out. New entries (key present) and opted-out entries do not.
    legacy_privacy_issue = f"legacy_expose_coordinates_{entry.entry_id}"
    if CONF_EXPOSE_COORDINATES not in entry.data and expose_coordinates:
        ir.async_create_issue(
            hass,
            DOMAIN,
            legacy_privacy_issue,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="legacy_expose_coordinates",
            translation_placeholders={"title": entry.title},
        )
    else:
        # The key is now present (or coordinates are off) — the user has opted
        # out (or this is a modern entry). Clear any previously-raised issue so
        # the warning doesn't persist after opt-out. No-op if none exists.
        ir.async_delete_issue(hass, DOMAIN, legacy_privacy_issue)

    editable_file = False

    if entry.data.get(CONF_DOWNLOAD_ZONES):
        download_path = Path(f"{hass.config.config_dir}/polygonal_zones/{entry.entry_id}.json")

        exists = await hass.async_add_executor_job(download_path.exists)
        if not exists:
            try:
                await download_zones(
                    zone_uris,
                    download_path,
                    prioritize,
                    hass,
                    allow_private_urls=allow_private_urls,
                )
            except UnsupportedSchemaVersion as err:
                # The source file's format is newer than this integration
                # understands. Retrying can't fix that — the user must upgrade
                # the integration or downgrade the file. Surface it as a
                # permanent setup error (HA stops retrying and shows it) rather
                # than spinning forever.
                raise ConfigEntryError(
                    f"Zone file for entry {entry.entry_id} uses an unsupported "
                    f"schema version: {err}"
                ) from err
            except Exception as err:
                # Any other failure (unreachable source, SSRF block, corrupt
                # payload, disk error) may be transient — and crucially, an
                # all-URIs-down outage is indistinguishable from a corrupt file
                # at this boundary (get_zones raises ZoneFileCorrupt for both).
                # Don't hard-fail the entry — that would leave no entities and
                # no retry. Signal HA to retry setup with its own backoff.
                raise ConfigEntryNotReady(
                    f"Could not download zone files for entry {entry.entry_id}: {err}"
                ) from err

        zone_uris = [f"/polygonal_zones/{entry.entry_id}.json"]
        editable_file = True

    source = ZoneSource(
        entry.entry_id,
        zone_uris,
        prioritize,
        editable_file,
        allow_private_urls=allow_private_urls,
    )
    entry.runtime_data.source = source

    entities = [
        PolygonalZoneEntity(
            source,
            entity_id,
            generate_entity_id(
                "device_tracker.polygonal_zones_{}", entity_id.split(".")[-1], hass=hass
            ),
            expose_coordinates,
        )
        for entity_id in entry.data.get(CONF_ENTITIES, [])
    ]

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "reload_zones",
        {},
        PolygonalZoneEntity.async_reload_zones,
        supports_response=SupportsResponse.OPTIONAL,
    )

    # Migration: pre-refactor releases raised the zone-load repair issue per
    # entity (``zone_load_failed_<mirror entity_id>``); the shared source now
    # uses a single per-entry id. Clear any stale per-entity issue so an upgraded
    # user whose issue was open doesn't keep a warning that can never clear.
    for entity in entities:
        ir.async_delete_issue(hass, DOMAIN, f"zone_load_failed_{entity.entity_id}")

    async_add_entities(entities, True)
    entry.runtime_data.entities = entities
    # Kick off the single shared load once entities exist to receive the result.
    source.async_schedule_initial_load(hass)


class PolygonalZoneEntity(TrackerEntity, RestoreEntity):
    """A mirror ``device_tracker`` that resolves its source into a polygonal zone.

    Zone data + load lifecycle live on the shared entry-scoped :class:`ZoneSource`;
    this entity holds only its own tracked source id, display prefs, and resolved
    state. The historical private attributes (``_zones``, ``_zones_urls``,
    ``_last_load_*`` …) are preserved as read-only properties that delegate to the
    source, so services/diagnostics keep a stable read interface.
    """

    _attr_location_name: str | None = None
    _attr_latitude: float | None = None
    _attr_longitude: float | None = None
    _attr_gps_accuracy: float | None = None

    def __init__(
        self,
        source: ZoneSource,
        tracked_entity_id: str,
        own_id: str,
        expose_coordinates: bool = True,
    ) -> None:
        """Initialize the entity."""
        self._source = source
        self._entity_id = tracked_entity_id
        self._expose_coordinates = expose_coordinates

        self._unsub: Callable[[], None] | None = None
        self._unsub_source: Callable[[], None] | None = None

        self.entity_id = own_id
        self._attr_unique_id = own_id
        self._attr_source_type = SourceType.GPS

    # --- read interface delegating to the shared source ------------------------
    # Kept so services (which read _config_entry_id / editable_file / zone_urls)
    # and diagnostics (which getattr _zones / _last_load_* …) need no changes.

    @property
    def _config_entry_id(self) -> str:
        return self._source.entry_id

    @property
    def _zones(self) -> list[Zone]:
        return self._source.zones

    @property
    def _zones_urls(self) -> list[str]:
        return self._source.zone_urls

    @property
    def _editable_file(self) -> bool:
        return self._source.editable_file

    @property
    def _prioritize_zone_files(self) -> bool:
        return self._source.prioritize

    @property
    def _allow_private_urls(self) -> bool:
        return self._source.allow_private_urls

    @property
    def _last_load_result(self) -> str:
        return self._source.last_load_result

    @property
    def _last_zones_loaded_at(self):
        return self._source.last_zones_loaded_at

    @property
    def _last_load_failures(self) -> list[tuple[str, str]]:
        return self._source.last_load_failures

    # --------------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Restore prior state, subscribe to the source tracker, and to reloads.

        The shared source drives the actual zone load; this entity re-resolves
        whenever the source (re)loads (``add_listener``) and whenever its tracked
        device reports a new location (``async_track_state_change_event``, which
        HA indexes by entity_id so we're woken only for our own source).
        """
        last_state = await self.async_get_last_state()
        if last_state is not None:
            _LOGGER.debug("Restoring previous state for '%s'", self._entity_id)
            self._attr_location_name = last_state.state
            self._attr_extra_state_attributes = last_state.attributes

        self._unsub_source = self._source.add_listener(self._handle_source_reloaded)
        self._unsub = async_track_state_change_event(
            self.hass, [self._entity_id], self._handle_state_change_builder()
        )

    def _handle_source_reloaded(self) -> None:
        """Source (re)loaded — re-resolve this mirror's state off the event loop."""
        self.hass.async_create_task(self._update_state())

    def _set_available(self, available: bool) -> None:
        """Toggle entity availability and log transitions at INFO."""
        if self._attr_available == available:
            return
        self._attr_available = available
        if available:
            _LOGGER.info("Entity %s is available again (zones loaded)", self._attr_unique_id)
        else:
            _LOGGER.info("Entity %s is unavailable", self._attr_unique_id)

    async def async_will_remove_from_hass(self) -> None:
        """Handle cleanup when the entity is removed."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._unsub_source:
            self._unsub_source()
            self._unsub_source = None

    async def update_location(self, latitude, longitude, gps_accuracy) -> None:
        """Update the location of the entity.

        Resolves the location to a zone via the executor so the (sync, CPU-bound)
        shapely geometry math doesn't block the event loop. Should only
        be called when latitude, longitude, or gps_accuracy actually changes.
        """
        zone = await self.hass.async_add_executor_job(
            get_locations_zone, latitude, longitude, gps_accuracy, self._source.zones
        )
        _LOGGER.debug("State of entity '%s' changed. new zone: %s", self._attr_unique_id, zone)
        self._attr_location_name = zone["name"] if zone is not None else "away"
        # Base attributes are non-location diagnostics — safe to publish even when
        # coordinates are off (they reveal load health, not where the device is).
        loaded_at = self._source.last_zones_loaded_at
        attributes: dict[str, Any] = {
            "source_entity": self._entity_id,
            "last_load_result": self._source.last_load_result,
            "last_zones_loaded_at": loaded_at.isoformat() if loaded_at is not None else None,
        }
        if self._expose_coordinates:
            attributes["latitude"] = latitude
            attributes["longitude"] = longitude
            attributes["gps_accuracy"] = gps_accuracy
            # `matched_zones` reveals fine-grained (overlapping) semantic location
            # and `zone_uris` can leak LAN hostnames/paths on a shared dashboard.
            # Both are gated with coordinates so "expose off" means only the zone
            # name (plus load diagnostics) leaves the entity. See docs/privacy.md.
            attributes["zone_uris"] = self._source.zone_urls
            # Every zone the buffered GPS point currently intersects, not just the
            # winning one — overlap-priority debugging in Developer Tools.
            attributes["matched_zones"] = zone["matched_zones"] if zone is not None else []
        self._attr_extra_state_attributes = attributes

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
        # Zones not (yet) loaded, or the shared load exhausted its retries. The
        # mirror can't resolve a zone, so reflect unavailable rather than acting
        # on an empty/stale zone set.
        if not self._source.loaded_ok:
            self._set_available(False)
            return

        entity_state = self.hass.states.get(self._entity_id)

        # Source tracker has been removed or is reporting unavailable /
        # unknown. Reflect that on the mirror so downstream automations
        # can detect the gap instead of acting on stale zone data.
        # (A tracker that merely lacks GPS attributes for one update — common
        # for wifi-only trackers between fixes — is handled below without
        # flipping availability.)
        if entity_state is None or entity_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._set_available(False)
            return

        if not all(
            key in entity_state.attributes for key in ["latitude", "longitude", "gps_accuracy"]
        ):
            return

        await self.update_location(
            entity_state.attributes["latitude"],
            entity_state.attributes["longitude"],
            entity_state.attributes["gps_accuracy"],
        )
        self._set_available(True)

        self.async_write_ha_state()

    async def async_reload_zones(self, call=None) -> dict | list | None:
        """Reload the shared zone source and re-resolve.

        Called from two paths:
        - The ``polygonal_zones.reload_zones`` entity service, which passes a
          ``ServiceCall`` carrying ``return_response``.
        - Mutation service handlers, which invoke it with no ``call`` to sync
          in-memory state after writing to disk.

        The reload runs once against the entry-scoped source; the source notifies
        every mirror to re-resolve.
        """
        invoked_as_service = call is not None
        try:
            await self._source.async_reload(self.hass)
        except Exception as err:
            _LOGGER.warning(
                "Failed to reload zones for entry=%s",
                self._source.entry_id,
                exc_info=True,
            )
            # When the user invoked the reload_zones service (especially with
            # return_response), surface a real failure instead of a "successful"
            # call that quietly returned nothing. The internal post-write sync
            # path (call is None) keeps the previous zones and stays quiet so a
            # reload hiccup can't mask an already-committed mutation.
            if invoked_as_service:
                raise HomeAssistantError(
                    f"Could not reload zones for {self._attr_unique_id}: {err}"
                ) from err
            return None
        _LOGGER.debug("Reloaded zones of entity: %s", self._attr_unique_id)

        await self._update_state()
        if call is not None and call.return_response:
            return [
                {
                    "name": z.name,
                    "priority": z.priority,
                    "geometry": list(exterior_coords(z.geometry)),
                }
                for z in self._source.zones
            ]
        return None

    @property
    def zones(self) -> list[Zone]:
        """The loaded zones."""
        return self._source.zones

    @property
    def editable_file(self) -> bool:
        """Is the zone file editable."""
        return self._source.editable_file

    @property
    def zone_urls(self) -> list[str]:
        """List of the urls where the zones are stored."""
        return self._source.zone_urls

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
            "identifiers": {("polygonal_zones", self._source.entry_id)},
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
        return f"{self._source.entry_id}_{self._entity_id}"
