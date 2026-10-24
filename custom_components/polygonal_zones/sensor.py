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

from collections.abc import Callable
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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
)

from .const import CONF_EXPOSE_COORDINATES, COORDINATE_GATED_ATTRIBUTES
from .entity import ZoneSourceFollower, zone_device_info
from .utils.general import redact_uri
from .zone_source import ZoneSource

PARALLEL_UPDATES = 0


def _slug(tracked_entity_id: str) -> str:
    """Readable object id of the tracked entity, for entity names."""
    return tracked_entity_id.split(".")[-1].replace("_", " ")


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


class PolygonalZoneSensor(ZoneSourceFollower, RestoreSensor):
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

        self.entity_id = own_id
        # Not own_id: generate_entity_id suffixes "_2" when the id is taken, which
        # minted a new registry entry on every reload (#131).
        self._attr_unique_id = f"{source.entry_id}_{tracked_entity_id}_zone"
        self._attr_name = f"{_slug(tracked_entity_id)} zone"

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
            # State saved by an older release may hold raw URLs (credentials,
            # query tokens); never re-publish them, matching the mirror tracker.
            if isinstance(restored.get("zone_uris"), list):
                restored["zone_uris"] = [redact_uri(str(u)) for u in restored["zone_uris"]]
            self._attr_extra_state_attributes = restored

        await self._follow_source()

    async def update_location(
        self, latitude: float, longitude: float, gps_accuracy: float | None
    ) -> None:
        """Resolve the location to a zone and publish it as this sensor's value."""
        zone = await self._source.async_resolve(self.hass, latitude, longitude, gps_accuracy)
        self._attr_native_value = zone["name"] if zone is not None else "away"
        attributes: dict[str, Any] = {"source_entity": self._entity_id}
        if self._expose_coordinates:
            attributes["matched_zones"] = zone["matched_zones"] if zone is not None else []
        self._attr_extra_state_attributes = attributes

    @property
    def device_info(self) -> DeviceInfo | None:
        """Share the same device as the config entry's mirror trackers."""
        return zone_device_info(self._source.entry_id)


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
        self._attr_name = f"{_slug(tracked_entity_id)} last reported"
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
        # A source's first write after HA starts or reloads is its restored
        # position re-stamped with the restart time, not a report: counting it
        # would hide a tracker that died while HA was down. A polling source's
        # first write is dropped too; state_reported events are always genuine.
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
        return zone_device_info(self._entry_id)
