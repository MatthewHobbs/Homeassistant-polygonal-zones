"""Companion zone-name sensor for the polygonal_zones integration.

Part of the location_name migration: the matched zone's name as a plain string — the exact value
``device_tracker``'s ``location_name`` publishes today — living on its own
entity that survives the removal of ``location_name``. Additive:
nothing about ``device_tracker.py`` changes here.

Deliberately a separate resolution, not a listener chained off the
device_tracker mirror entity: reads the same shared :class:`ZoneSource` and
the same original source tracker directly, so it never depends on the other
platform's entity existing or its setup order.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ENTITIES,
    EVENT_STATE_CHANGED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
)

from .const import CONF_EXPOSE_COORDINATES, COORDINATE_GATED_ATTRIBUTES
from .utils import event_should_trigger
from .zone_source import ZoneSource

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up one zone-name sensor per tracked device_tracker.

    ``__init__.async_setup_entry`` builds the shared ``ZoneSource`` on
    ``entry.runtime_data.source`` before this platform is forwarded —
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

    async_add_entities(
        [
            PolygonalZoneLastReportedSensor(
                entity_id,
                generate_entity_id(
                    "sensor.polygonal_zones_{}_last_reported", entity_id.split(".")[-1], hass=hass
                ),
                source.entry_id,
            )
            for entity_id in entry.data.get(CONF_ENTITIES, [])
        ]
    )


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
            restored = dict(last_state.attributes)
            if not self._expose_coordinates:
                for gated in COORDINATE_GATED_ATTRIBUTES:
                    restored.pop(gated, None)
            self._attr_extra_state_attributes = restored

        self._unsub_source = self._source.add_listener(self._handle_source_reloaded)
        self._unsub = async_track_state_change_event(
            self.hass, [self._entity_id], self._handle_state_change_builder()
        )
        # See device_tracker.PolygonalZoneEntity.async_added_to_hass: the shared
        # source's one-shot initial-load notification can fire (as a separate
        # task, via async_at_started) before this entity's own add_listener()
        # above has run, since the two platforms are forwarded concurrently.
        # Resolving here too makes the initial state correct regardless of
        # that ordering.
        await self._update_state()

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
        zone = await self._source.async_resolve(self.hass, latitude, longitude, gps_accuracy)
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


class PolygonalZoneLastReportedSensor(RestoreSensor):
    """When the source tracker last reported, so automations can detect a silent one.

    Staleness is ``now() - states(<this sensor>)``; keeping the timestamp here, not
    a ticking "seconds since" value, means the entity only writes state when the
    tracker actually reports. Disabled by default: the user opts in per device.

    Restored across restarts, so a tracker that died while HA was down is still
    flagged. Known limit: after a restart the source's own ``last_reported`` is the
    restart time, so the restored value (older, truer) deliberately wins.

    Must follow both ``state_changed`` and ``state_reported``: a phone that
    re-reports an unchanged position fires only the latter, and listening to
    ``state_changed`` alone would call a healthy stationary tracker stale.
    """

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, tracked_entity_id: str, own_id: str, entry_id: str) -> None:
        """Initialize the sensor."""
        self._entity_id = tracked_entity_id
        self._unsubs: list[Callable[[], None]] = []

        self.entity_id = own_id
        self._entry_id = entry_id
        # Not own_id: generate_entity_id suffixes "_2" when the id is already in
        # the state machine (e.g. a setup retry after start), which would mint a
        # new, disabled registry entry and silently drop the user's opt-in.
        self._attr_unique_id = f"{entry_id}_{tracked_entity_id}_last_reported"
        self._attr_name = f"{tracked_entity_id.split('.')[-1].replace('_', ' ')} last reported"
        self._attr_extra_state_attributes = {"source_entity": tracked_entity_id}

    async def async_added_to_hass(self) -> None:
        """Restore the prior value (else seed from the source) and follow its reports."""
        last_data = await self.async_get_last_sensor_data()
        if last_data is not None and isinstance(last_data.native_value, datetime):
            self._attr_native_value = last_data.native_value
        else:
            self._refresh()
        self._unsubs = [
            async_track_state_change_event(self.hass, [self._entity_id], self._handle_event),
            async_track_state_report_event(self.hass, [self._entity_id], self._handle_event),
        ]

    async def async_will_remove_from_hass(self) -> None:
        """Handle cleanup when the entity is removed."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    @callback
    def _handle_event(self, event: Any) -> None:
        # A source's first write after HA starts or after the source reloads (no
        # previous state, or the "restored" placeholder HA writes) is not counted
        # as a report. For a source that restores its state that write is its old
        # position re-published with the restart time, and counting it would
        # overwrite the restored value and hide a tracker that died while HA was
        # down. A polling source's genuine first write is dropped too; the next
        # report corrects it. state_reported events are always genuine.
        if event.event_type == EVENT_STATE_CHANGED:
            old_state = event.data.get("old_state")
            if old_state is None or old_state.attributes.get("restored"):
                return
        self._refresh()
        self.async_write_ha_state()

    def _refresh(self) -> None:
        # Advances only on a real report. HA stamps an "unavailable"/"unknown"
        # state with a fresh last_reported too, but that is the silence this
        # sensor exists to expose, not the tracker speaking, so keep the old
        # value (likewise if the source entity is gone).
        state = self.hass.states.get(self._entity_id)
        if state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._attr_native_value = state.last_reported

    @property
    def device_info(self) -> DeviceInfo | None:
        """Share the config entry's device, as the other platforms' entities do."""
        return {
            "identifiers": {("polygonal_zones", self._entry_id)},
            "name": "Polygonal Zones",
            "manufacturer": "Polygonal Zones Community",
            "entry_type": DeviceEntryType.SERVICE,
        }
