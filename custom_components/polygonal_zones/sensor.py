"""Companion zone-name sensor for the polygonal_zones integration.

Release A, PR A4 of the location_name migration (see BACKLOG.md / the linked
RFC): the matched zone's name as a plain string — the exact value
``device_tracker``'s ``location_name`` publishes today — living on its own
entity that survives Release B's removal of ``location_name``. Additive:
nothing about ``device_tracker.py`` changes here.

Deliberately a separate resolution, not a listener chained off the
device_tracker mirror entity: reads the same shared :class:`ZoneSource` and
the same original source tracker directly, so it never depends on the other
platform's entity existing or its setup order.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from homeassistant.components.sensor import RestoreSensor
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITIES
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_EXPOSE_COORDINATES
from .utils import event_should_trigger, get_locations_zone
from .zone_source import ZoneSource

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up one zone-name sensor per tracked device_tracker.

    ``__init__.async_setup_entry`` builds the shared ``ZoneSource`` on
    ``entry.runtime_data.source`` before this platform is forwarded (PR A2) —
    this just builds a thin sensor per tracked ``device_tracker`` that reads
    from it, mirroring ``device_tracker.py``'s own entity construction.
    """
    source: ZoneSource = entry.runtime_data.source
    expose_coordinates: bool = bool(entry.data.get(CONF_EXPOSE_COORDINATES, True))

    entities = [
        PolygonalZoneSensor(
            source,
            entity_id,
            generate_entity_id("sensor.polygonal_zones_{}", entity_id.split(".")[-1], hass=hass),
            expose_coordinates,
        )
        for entity_id in entry.data.get(CONF_ENTITIES, [])
    ]
    async_add_entities(entities, True)


class PolygonalZoneSensor(RestoreSensor):
    """The matched zone's name (or ``away``) as a plain string sensor."""

    _attr_should_poll = False

    def __init__(
        self,
        source: ZoneSource,
        tracked_entity_id: str,
        own_id: str,
        expose_coordinates: bool = True,
    ) -> None:
        """Initialize the sensor."""
        self._source = source
        self._entity_id = tracked_entity_id
        self._expose_coordinates = expose_coordinates

        self._unsub: Callable[[], None] | None = None
        self._unsub_source: Callable[[], None] | None = None

        self.entity_id = own_id
        self._attr_unique_id = f"{own_id}_zone"

    async def async_added_to_hass(self) -> None:
        """Restore prior state, subscribe to the source tracker, and to reloads."""
        last_data = await self.async_get_last_sensor_data()
        if last_data is not None:
            self._attr_native_value = last_data.native_value
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_extra_state_attributes = dict(last_state.attributes)

        self._unsub_source = self._source.add_listener(self._handle_source_reloaded)
        self._unsub = async_track_state_change_event(
            self.hass, [self._entity_id], self._handle_state_change_builder()
        )

    def _handle_source_reloaded(self) -> None:
        """Source (re)loaded — re-resolve this sensor's state off the event loop."""
        self.hass.async_create_task(self._update_state())

    async def async_will_remove_from_hass(self) -> None:
        """Handle cleanup when the entity is removed."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._unsub_source:
            self._unsub_source()
            self._unsub_source = None

    async def _update_state(self) -> None:
        # Mirrors device_tracker.py's PolygonalZoneEntity._update_state exactly:
        # only the success path below writes HA state; the early-return branches
        # just flip _attr_available for the next successful write to pick up.
        if not self._source.loaded_ok:
            self._attr_available = False
            return

        entity_state = self.hass.states.get(self._entity_id)
        if entity_state is None or entity_state.state in ("unavailable", "unknown"):
            self._attr_available = False
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
        self._attr_available = True

        self.async_write_ha_state()

    async def update_location(self, latitude: float, longitude: float, gps_accuracy: float) -> None:
        """Resolve the location to a zone and publish it as this sensor's value."""
        zone = await self.hass.async_add_executor_job(
            get_locations_zone, latitude, longitude, gps_accuracy, self._source.zones
        )
        self._attr_native_value = zone["name"] if zone is not None else "away"
        attributes: dict[str, Any] = {"source_entity": self._entity_id}
        if self._expose_coordinates:
            attributes["matched_zones"] = zone["matched_zones"] if zone is not None else []
        self._attr_extra_state_attributes = attributes

    def _handle_state_change_builder(
        self,
    ) -> Callable[[Any], Coroutine[Any, Any, None]]:
        async def _handler(event: Any) -> None:
            if event_should_trigger(event, self._entity_id):
                await self._update_state()

        return _handler

    @property
    def device_info(self) -> DeviceInfo | None:
        """Share the same device as the source config entry's device_tracker mirror."""
        return {
            "identifiers": {("polygonal_zones", self._source.entry_id)},
            "name": "Polygonal Zones",
            "manufacturer": "Polygonal Zones Community",
            "entry_type": DeviceEntryType.SERVICE,
        }
