"""definition file for the reload all zones action."""

import asyncio
from collections.abc import Callable, Coroutine
import time
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall

from ..const import DOMAIN

# One reload per entry this often, matching the mutation budget the rest of the
# integration enforces. A request inside the window waits for it instead of
# being dropped: the add-on calls this after every save and reports the result,
# so dropping one would mean stale zones with a success message.
RELOAD_FLOOR_SECONDS = 2.0

_last_reload: dict[str, float] = {}


def action_builder(hass: HomeAssistant) -> Callable[[ServiceCall], Coroutine[Any, Any, None]]:
    """Reload every loaded entry's zones, for a producer that just changed them.

    The add-on writes its file itself, so it cannot use the entity-targeted
    ``reload_zones`` action: it does not know entity ids.
    """

    async def action(_call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            source = getattr(entry.runtime_data, "source", None)
            if source is None:
                continue
            last = _last_reload.get(entry.entry_id)
            if last is not None:
                wait = RELOAD_FLOOR_SECONDS - (time.monotonic() - last)
                if wait > 0:
                    await asyncio.sleep(wait)
            _last_reload[entry.entry_id] = time.monotonic()
            await source.async_reload(hass)

    return action
