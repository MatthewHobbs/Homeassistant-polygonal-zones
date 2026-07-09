"""Entry-scoped zone source shared by every mirror entity in one config entry.

Every ``device_tracker`` mirror under a single config entry reads the *same*
zone definitions. Historically each entity fetched, parsed, and stored its own
copy — N identical HTTP GETs and N identical shapely parses per entry, plus a
``sync_entities_after_write`` fan-out that existed only to keep those copies in
step. ``ZoneSource`` lifts that ownership to the entry: one fetch/parse, one
retry/backoff lifecycle, one repair issue, and a listener list so each entity
re-resolves its state when the shared zones (re)load.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
import random

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .utils.zones import Zone, ZoneFileCorrupt, load_zones

_LOGGER = logging.getLogger(__name__)

_MAX_LOAD_ATTEMPTS = 5
_BASE_RETRY_DELAY = 30  # seconds; doubles on each attempt, capped at 10 min


class ZoneSource:
    """Shared, refreshable zone dataset for one config entry."""

    def __init__(
        self,
        entry_id: str,
        zone_urls: list[str],
        prioritize: bool,
        editable_file: bool,
        *,
        allow_private_urls: bool = False,
    ) -> None:
        """Initialise the source (does not load — see ``async_schedule_initial_load``)."""
        self.entry_id = entry_id
        self.zone_urls = zone_urls
        self.prioritize = prioritize
        self.editable_file = editable_file
        self.allow_private_urls = allow_private_urls

        self.zones: list[Zone] = []
        self.last_load_failures: list[tuple[str, str]] = []
        # Observability: outcome of the most recent attempt + when the last
        # successful load completed. Surfaced in diagnostics and entity attrs.
        self.last_load_result: str = "never"
        self.last_zones_loaded_at: datetime | None = None
        # True once a load has succeeded; entities stay unavailable until then.
        self.loaded_ok = False

        self._listeners: list[Callable[[], None]] = []
        self._unsub_at_started: Callable[[], None] | None = None
        self._unsub_retry: Callable[[], None] | None = None

    @property
    def issue_id(self) -> str:
        """Repair-issue id for a fully-failed load on this entry."""
        return f"zone_load_failed_{self.entry_id}"

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a callback fired after every (re)load; returns an unsubscribe."""
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    def async_schedule_initial_load(self, hass: HomeAssistant) -> None:
        """Load once HA has started (or immediately if already running).

        ``async_at_started`` fires immediately when HA is already running and
        otherwise waits for the start event, avoiding the check/subscribe race.
        """
        self._unsub_at_started = async_at_started(hass, self._async_initial_load)

    async def _async_initial_load(self, hass: HomeAssistant, attempt: int = 1) -> None:
        """Initial load with jittered exponential backoff, then a repair issue."""
        try:
            await self._async_load(hass)
        except Exception:
            self.last_load_result = "failed"
            if attempt < _MAX_LOAD_ATTEMPTS:
                capped = min(600, _BASE_RETRY_DELAY * (2 ** (attempt - 1)))
                # Equal jitter across [capped/2, capped] — a shared source means a
                # single schedule, but jitter still avoids hammering a flaky host
                # in a tight, perfectly-periodic loop.
                delay = capped / 2 + random.uniform(0, capped / 2)
                _LOGGER.warning(
                    "Failed to load zones for entry=%s (attempt %d/%d); retrying in %.0fs",
                    self.entry_id,
                    attempt,
                    _MAX_LOAD_ATTEMPTS,
                    delay,
                    exc_info=True,
                )

                @callback
                def _retry(_now, _next_attempt=attempt + 1) -> None:
                    # Without @callback, HA's job-type inference schedules this
                    # plain function on the executor thread pool (it can't tell
                    # it won't block) — hass.async_create_task then raises since
                    # it's called off the event loop. See issue #39.
                    self._unsub_retry = None
                    hass.async_create_task(self._async_initial_load(hass, _next_attempt))

                self._unsub_retry = async_call_later(hass, delay, _retry)
            else:
                _LOGGER.exception(
                    "Giving up loading zones for entry=%s after %d attempts; "
                    "call reload_zones or reload the integration to retry",
                    self.entry_id,
                    _MAX_LOAD_ATTEMPTS,
                )
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    self.issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="zone_load_failed",
                    translation_placeholders={"entity_id": self.entry_id},
                )
                # Wake entities so they reflect the unavailable state.
                self._notify()
            return
        ir.async_delete_issue(hass, DOMAIN, self.issue_id)
        self._notify()

    async def _async_load(self, hass: HomeAssistant) -> None:
        """Fetch + parse every URI once; raise ``ZoneFileCorrupt`` if all fail."""
        result = await load_zones(
            self.zone_urls, hass, self.prioritize, allow_private_urls=self.allow_private_urls
        )
        if self.zone_urls and not result.zones and result.failures:
            first_uri, first_msg = result.failures[0]
            raise ZoneFileCorrupt(
                f"All {len(result.failures)} zone URIs failed; first: {first_uri}: {first_msg}"
            )
        self.zones = result.zones
        self.last_load_failures = result.failures
        self.last_zones_loaded_at = dt_util.utcnow()
        self.last_load_result = "ok"
        self.loaded_ok = True

    async def async_reload(self, hass: HomeAssistant) -> None:
        """Reload from source and notify listeners. Raises on failure.

        Used by the ``reload_zones`` service and the mutation-service post-write
        sync. Unlike the initial load this does not arm a retry — the caller
        (service handler) surfaces the error to the user.
        """
        try:
            await self._async_load(hass)
        except Exception:
            self.last_load_result = "failed"
            raise
        ir.async_delete_issue(hass, DOMAIN, self.issue_id)
        self._notify()

    def async_shutdown(self) -> None:
        """Cancel any pending start/retry callbacks on unload."""
        if self._unsub_at_started is not None:
            self._unsub_at_started()
            self._unsub_at_started = None
        if self._unsub_retry is not None:
            self._unsub_retry()
            self._unsub_retry = None
