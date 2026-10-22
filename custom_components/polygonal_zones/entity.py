"""What the zone entities share: following one tracked device through a ZoneSource."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event

from .utils import event_should_trigger
from .zone_source import ZoneSource


def zone_device_info(entry_id: str) -> DeviceInfo:
    """The one device every entity of a config entry hangs off."""
    return {
        "identifiers": {("polygonal_zones", entry_id)},
        "name": "Polygonal Zones",
        "manufacturer": "Polygonal Zones Community",
        "entry_type": DeviceEntryType.SERVICE,
    }


class ZoneSourceFollower(Entity):
    """Mixin for an entity that re-resolves a zone whenever its tracked device or the
    shared source changes. The host sets ``_source`` and ``_entity_id`` and provides
    ``update_location``; it may override ``_set_available``."""

    _source: ZoneSource
    _entity_id: str
    _unsub: Callable[[], None] | None = None
    _unsub_source: Callable[[], None] | None = None

    async def update_location(self, latitude: float, longitude: float, gps_accuracy: float) -> None:
        """Publish the zone for this position (implemented by the entity)."""
        raise NotImplementedError

    async def _follow_source(self) -> None:
        """Subscribe to source reloads and the tracked device, then resolve once.

        The shared source's one-shot initial-load notification is scheduled via
        ``async_at_started`` as a separate task, so with the platforms forwarded
        concurrently it can fire before ``add_listener`` below has run and is then
        never retried. Resolving here too makes the initial state correct whatever
        the ordering. HA indexes state-change subscriptions by entity_id, so only
        the tracked device wakes this entity.
        """
        self._unsub_source = self._source.add_listener(self._handle_source_reloaded)
        self._unsub = async_track_state_change_event(
            self.hass, [self._entity_id], self._handle_state_change_builder()
        )
        await self._update_state()

    def _handle_source_reloaded(self) -> None:
        """Source (re)loaded: re-resolve off the event loop."""
        self.hass.async_create_task(self._update_state())

    async def async_will_remove_from_hass(self) -> None:
        """Drop both subscriptions."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._unsub_source:
            self._unsub_source()
            self._unsub_source = None

    def _set_available(self, available: bool) -> None:
        self._attr_available = available

    def _handle_state_change_builder(self) -> Callable[[Any], Coroutine[Any, Any, None]]:
        """Build the listener that acts only on events that change the position."""

        async def func(event: Any) -> None:
            if event_should_trigger(event, self._entity_id):
                await self._update_state()

        return func

    async def _update_state(self) -> None:
        # Only the success path writes HA state; the early returns just flip
        # availability for the next successful write to pick up.
        #
        # Zones not (yet) loaded, or the shared load exhausted its retries: reflect
        # unavailable rather than acting on an empty or stale zone set.
        if not self._source.loaded_ok:
            self._set_available(False)
            return

        entity_state = self.hass.states.get(self._entity_id)

        # The tracked device was removed or reports unavailable/unknown. Reflect it so
        # downstream automations can see the gap. (A tracker that merely lacks GPS
        # attributes for one update, common for wifi-only trackers between fixes, is
        # handled below without flipping availability.)
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
