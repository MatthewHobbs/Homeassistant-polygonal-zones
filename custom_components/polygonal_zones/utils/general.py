"""General helper functions for the polygonal_zones integration."""

import ipaddress
import logging
from pathlib import Path
import socket
from urllib.parse import urlparse

import aiohttp
from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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


async def _validate_public_host(hass: HomeAssistant, hostname: str) -> None:
    """Reject hostnames that resolve to private, loopback, or metadata IPs."""
    try:
        infos = await hass.loop.getaddrinfo(hostname, None)
    except socket.gaierror as err:
        raise ValueError(f"Cannot resolve host '{hostname}'") from err
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(f"Refusing to fetch '{hostname}': resolves to non-public address {ip}")


async def load_data(uri: str, hass: HomeAssistant) -> str:
    """Load data from an HTTP(S) URL or a file inside the HA config directory."""
    parsed = urlparse(uri)

    if parsed.scheme in ("http", "https"):
        if not parsed.hostname:
            raise ValueError(f"URL '{uri}' has no hostname")
        await _validate_public_host(hass, parsed.hostname)

        session = async_get_clientsession(hass)
        async with session.get(uri, timeout=FETCH_TIMEOUT, allow_redirects=False) as response:
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
        with open(safe_path, encoding="utf-8") as f:
            return f.read()

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
