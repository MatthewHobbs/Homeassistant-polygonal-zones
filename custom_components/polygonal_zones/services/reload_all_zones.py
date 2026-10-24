"""definition file for the reload all zones action."""

from collections.abc import Callable, Coroutine
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall

from ..const import DOMAIN
from .errors import RateLimited
from .helpers import enforce_mutation_rate_limit


def action_builder(hass: HomeAssistant) -> Callable[[ServiceCall], Coroutine[Any, Any, None]]:
    """Reload every loaded entry's zones, for a producer that just changed them.

    The add-on writes its file itself, so it cannot use the entity-targeted
    ``reload_zones`` action: it does not know entity ids. One domain-wide call
    covers every entry, and an entry inside its 2 s budget is skipped rather
    than failing the whole call.
    """

    async def action(_call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            source = getattr(entry.runtime_data, "source", None)
            if source is None:
                continue
            try:
                enforce_mutation_rate_limit(entry.entry_id)
            except RateLimited:
                continue
            await source.async_reload(hass)

    return action
