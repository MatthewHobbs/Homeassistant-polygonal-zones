"""The config validation helpers for the polygonal zones integration."""

import ipaddress
from urllib.parse import urlparse

from homeassistant.core import HomeAssistant

from .general import _is_public_ip, safe_config_path


async def validate_zone_urls(
    value: list[str], hass: HomeAssistant, *, allow_private_urls: bool = False
) -> dict[str, str]:
    """Validate every non-empty entry is either an http(s) URL or a file under config_dir.

    Returns a Home Assistant-style errors dict keyed by the ``zone_urls`` field,
    or an empty dict when validation passes.

    When ``allow_private_urls`` is off and a URL's host is a literal private /
    loopback / link-local IP (the common "companion add-on on the LAN" case),
    returns the specific ``private_url_blocked`` error naming the toggle — so the
    user fixes it at the form instead of the entry silently failing to load at
    startup. Hostnames that aren't literal IPs are left to the fetch-time SSRF
    resolver (we don't resolve DNS during form validation).
    """
    for item in value:
        if not item:
            continue
        parsed = urlparse(item)
        if parsed.scheme in ("http", "https"):
            if not parsed.hostname:
                return {"zone_urls": "invalid_url"}
            if not allow_private_urls:
                try:
                    ip = ipaddress.ip_address(parsed.hostname)
                except ValueError:
                    ip = None  # a hostname, not a literal IP — defer to fetch time
                if ip is not None and not _is_public_ip(ip, allow_private=False):
                    return {"zone_urls": "private_url_blocked"}
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
