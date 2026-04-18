"""The config validation helpers for the polygonal zones integration."""

from urllib.parse import urlparse

from homeassistant.core import HomeAssistant

from .general import safe_config_path


async def validate_zone_urls(
    value: list[str], hass: HomeAssistant
) -> dict[str, str]:
    """Validate every non-empty entry is either an http(s) URL or a file under config_dir.

    Returns a Home Assistant-style errors dict keyed by the ``zone_urls`` field,
    or an empty dict when validation passes.
    """
    for item in value:
        if not item:
            continue
        parsed = urlparse(item)
        if parsed.scheme in ("http", "https"):
            if not parsed.hostname:
                return {"zone_urls": "invalid_url"}
            continue
        if parsed.scheme:
            return {"zone_urls": "invalid_url"}
        try:
            path = safe_config_path(hass.config.config_dir, item)
        except ValueError:
            return {"zone_urls": "invalid_path"}
        if not await hass.async_add_executor_job(path.is_file):
            return {"zone_urls": "invalid_path"}
    return {}
