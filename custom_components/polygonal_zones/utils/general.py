"""General helper functions for the polygonal_zones integration."""

import ipaddress
import logging
from pathlib import Path
import socket
from urllib.parse import urlparse

import aiohttp
from aiohttp.resolver import DefaultResolver
from homeassistant.core import Event, HomeAssistant, State

_LOGGER = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
FETCH_TIMEOUT = aiohttp.ClientTimeout(total=10)


def safe_config_path(config_dir: str, user_path: str) -> Path:
    """Resolve ``user_path`` inside ``config_dir``.

    Raises ValueError if the resolved path escapes the config directory.
    """
    base = Path(config_dir).resolve()
    candidate = (base / user_path.lstrip("/")).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as err:
        raise ValueError(f"Path '{user_path}' resolves outside config directory") from err
    return candidate


def _is_public_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_private: bool = False
) -> bool:
    """Return True if the address is reachable under the integration's policy.

    By default, reachable means "on the public internet": not private, not
    loopback, not link-local, not multicast, not reserved, not unspecified.
    Set ``allow_private=True`` to relax only the ``is_private`` bucket (RFC-1918
    IPv4 + RFC-4193 ULA IPv6) — loopback, link-local (including cloud metadata
    169.254.169.254), multicast, reserved, and unspecified stay blocked.
    """
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return False
    return allow_private or not ip.is_private


class _PublicOnlyResolver(DefaultResolver):  # type: ignore[misc, valid-type]
    """Resolver that rejects addresses on private/loopback/metadata ranges.

    Applying the check inside the aiohttp resolver closes the DNS-rebinding
    TOCTOU window: aiohttp's own connect path goes through ``resolve`` and
    therefore every IP the socket actually connects to has passed the check.

    When constructed with ``allow_private=True``, RFC-1918 / ULA addresses
    are allowed through. Loopback / link-local / metadata ranges remain
    blocked regardless.
    """

    def __init__(self, *args, allow_private: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._allow_private = allow_private

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET) -> list[dict]:
        infos = await super().resolve(host, port, family)
        filtered: list[dict] = []
        for info in infos:
            try:
                ip = ipaddress.ip_address(info["host"])
            except ValueError:
                continue
            if _is_public_ip(ip, allow_private=self._allow_private):
                filtered.append(info)
        if not filtered:
            raise OSError(f"Refusing to connect to '{host}': no reachable addresses available")
        return filtered


async def load_data(uri: str, hass: HomeAssistant, *, allow_private_urls: bool = False) -> str:
    """Load data from an HTTP(S) URL or a file inside the HA config directory.

    ``allow_private_urls=True`` relaxes the SSRF resolver to accept RFC-1918
    private addresses so a user can point the integration at a LAN-installed
    zone source (e.g. the companion editor add-on at ``http://192.168.x.x:8000``).
    Loopback / link-local / multicast / metadata addresses stay blocked.
    """
    parsed = urlparse(uri)

    if parsed.scheme in ("http", "https"):
        if not parsed.hostname:
            raise ValueError(f"URL '{uri}' has no hostname")

        connector = aiohttp.TCPConnector(
            resolver=_PublicOnlyResolver(allow_private=allow_private_urls)
        )
        async with (
            aiohttp.ClientSession(connector=connector) as session,
            session.get(uri, timeout=FETCH_TIMEOUT, allow_redirects=False) as response,
        ):
            if 300 <= response.status < 400:
                raise ValueError(f"Refusing redirect from '{uri}' (status {response.status})")
            response.raise_for_status()
            if response.content_length is not None and response.content_length > MAX_RESPONSE_BYTES:
                raise ValueError(
                    f"Response from '{uri}' too large: {response.content_length} bytes"
                )
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.content.iter_chunked(65536):
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise ValueError(f"Response from '{uri}' exceeded max size")
                chunks.append(chunk)
            return b"".join(chunks).decode(response.charset or "utf-8")

    if parsed.scheme and parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URI scheme: {parsed.scheme}")

    safe_path = safe_config_path(hass.config.config_dir, uri)

    def _read() -> str:
        return safe_path.read_text(encoding="utf-8")

    return await hass.async_add_executor_job(_read)


REQUIRED_ATTRIBUTES = {"latitude", "longitude", "gps_accuracy"}


def event_should_trigger(event: Event, entity_id: str) -> bool:
    """Decide if the event should trigger the sensor.

    Args:
        event: The event to check.
        entity_id: The entity id to check.

    Returns:
        True if the event should trigger the sensor, False otherwise.

    """
    if event.data.get("entity_id") != entity_id:
        return False

    old_state: State | None = event.data.get("old_state")
    new_state: State | None = event.data.get("new_state")

    if not (old_state and new_state):
        return False
    if not all(attr in new_state.attributes for attr in REQUIRED_ATTRIBUTES):
        return False
    # the old state is none when it is the first update of the entity
    if not all(attr in old_state.attributes for attr in REQUIRED_ATTRIBUTES):
        return True

    # Check if any location attributes changed
    return any(
        new_state.attributes[attr] != old_state.attributes[attr] for attr in REQUIRED_ATTRIBUTES
    )
