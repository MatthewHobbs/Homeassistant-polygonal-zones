"""General helper functions for the polygonal_zones integration."""

import ipaddress
import logging
from pathlib import Path
import re
import socket
from urllib.parse import urlparse

import aiohttp
from aiohttp.resolver import DefaultResolver
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, State

_LOGGER = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
# Sub-timeouts as well as the overall budget: a slow TLS handshake or a
# server that dribbles the body must not consume the whole 10s window and
# starve the retry budget. connect caps the handshake; sock_read caps any
# single read stall.
FETCH_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5, sock_read=8)


# A URL in free text runs to the next whitespace. Do not stop at a quote: yarl
# leaves a raw ``'`` in a query, Python then switches the error repr to ``"…"``
# quoting, and a pattern that ends at the first ``'`` would leave the token.
_URL_IN_TEXT = re.compile(r"https?://\S+", re.IGNORECASE)
_USERINFO = re.compile(r"(https?://)[^/?#\s@]*@", re.IGNORECASE)


def _strip_credentials_and_query(uri: str) -> str:
    """Redaction for a URI ``urlparse`` cannot take apart (bad port, no host).

    Deliberately blunt: everything up to the last ``@`` is treated as userinfo,
    even when a malformed password holds ``/``, ``?`` or ``#``, then the query and
    fragment go. It may drop a real ``@`` from a path; it never keeps a credential.
    """
    # The scheme may be followed by "://", ":/" or just ":" (urlparse accepts all
    # three and reports no host), so split off whatever prefix is there.
    prefix = re.match(r"[A-Za-z][A-Za-z0-9+.-]*:/{0,2}", uri)
    head = prefix.group(0) if prefix else ""
    rest = uri[len(head) :].rpartition("@")[2]
    return f"{head}{re.split(r'[?#]', rest, maxsplit=1)[0]}"


def redact_uri(uri: str) -> str:
    """Return a log/diagnostics-safe form of an HTTP(S) URI.

    Strips ``user:pass@`` credentials and the query string / fragment (which can
    carry access tokens), keeping ``scheme://host[:port]/path``. Non-HTTP URIs
    (e.g. ``/config`` file paths) carry no credential component and are returned
    unchanged. An HTTP(S) URI that cannot be parsed (a malformed port, no host)
    is stripped by hand rather than returned raw: the config validator used to
    accept such strings and they are exactly what carries credentials.
    """
    try:
        parsed = urlparse(uri)
        if parsed.scheme not in ("http", "https"):
            return uri
        if not parsed.hostname:
            return _strip_credentials_and_query(uri)
        port = parsed.port
    except ValueError:
        return _strip_credentials_and_query(uri)
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    netloc = host if port is None else f"{host}:{port}"
    return f"{parsed.scheme}://{netloc}{parsed.path}"


def redact_text(text: str) -> str:
    """Redact every HTTP(S) URL inside free text, such as an exception message.

    aiohttp builds its error text from a URL it has already rewritten (it drops
    ``user:pass@`` but keeps the query), so the configured string is not in the
    message and a literal replace misses it. Match URLs by shape instead, and
    drop userinfo everywhere first so a URL nested in another URL's path is
    covered too.
    """
    text = _USERINFO.sub(r"\1", text)
    return _URL_IN_TEXT.sub(lambda m: redact_uri(m.group(0)), text)


def download_zone_relative_path(entry_id: str) -> str:
    """The managed local zone-snapshot path for an entry, relative to ``/config``.

    Single source of truth for the on-disk layout: the download materialiser, the
    entry unload (lock cleanup), and the mutation services all derive from this.
    """
    return f"polygonal_zones/{entry_id}.json"


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


def literal_host_policy(host: str) -> str | None:
    """Classify a URL host that is an IP literal; ``None`` for a hostname.

    ``"public"``; ``"private"`` (RFC 1918 / ULA, allowed only with the LAN option);
    or ``"blocked"`` (loopback, link-local, multicast, reserved, unspecified, and
    numeric forms ``ipaddress`` cannot parse such as ``127.1`` or ``2130706433``,
    which aiohttp may still treat as a literal). A name falls to the resolver.
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "blocked" if re.fullmatch(r"[0-9.]+", host) or ":" in host else None
    if not _is_public_ip(ip, allow_private=True):
        return "blocked"
    return "public" if _is_public_ip(ip) else "private"


def _refuse_non_public_literal(host: str, *, allow_private: bool) -> None:
    """Apply the address policy to a host that is already an IP literal.

    aiohttp does not call the resolver for a literal IP, so ``_PublicOnlyResolver``
    never sees one. Without this a stored ``http://127.0.0.1:8123/`` or
    ``http://169.254.169.254/`` was fetched regardless of the policy.
    """
    policy = literal_host_policy(host)
    if policy == "blocked" or (policy == "private" and not allow_private):
        raise OSError(f"Refusing to connect to '{host}': no reachable addresses available")


def is_local_add_on_host(uri: str) -> bool:
    """Return True if ``uri``'s host looks like a LAN-installed companion add-on.

    Used to pick a staleness-safe ``download_zones`` default for new installs
    (otherwise a stale snapshot would silently hide edits made in the
    add-on). Only classifies what's cheap to check synchronously — a private/loopback/link-local IP literal, ``localhost``,
    or an mDNS ``.local`` name — since resolving a real DNS hostname just to
    pick a form default isn't worth a network round-trip. A public https://
    URL or a /config file path returns False.
    """
    parsed = urlparse(uri)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    if host == "localhost" or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


async def load_data(
    uri: str, hass: HomeAssistant, *, allow_private_urls: bool = False, token: str | None = None
) -> str:
    """Load data from an HTTP(S) URL or a file inside the HA config directory.

    ``allow_private_urls=True`` relaxes the SSRF resolver to accept RFC-1918
    private addresses so a user can point the integration at a LAN-installed
    zone source (e.g. the companion editor add-on at ``http://192.168.x.x:8000``).
    Loopback / link-local / multicast / metadata addresses stay blocked.

    ``token``, if given, is sent as the ``X-Save-Token`` header — but ONLY when
    ``uri`` classifies as :func:`is_local_add_on_host`, so a token configured
    for the companion add-on is never sent to an unrelated public URL. This is
    the add-on's own read-gate (its ``save_token`` option protects GET
    ``/zones.json``/``/trackers.json`` too, by design — see that repo's ADR
    0002); it is never sent across a redirect, since ``allow_redirects=False``
    below already refuses redirects outright.
    """
    parsed = urlparse(uri)

    if parsed.scheme in ("http", "https"):
        if not parsed.hostname:
            raise ValueError("URL has no hostname")
        _refuse_non_public_literal(parsed.hostname, allow_private=allow_private_urls)

        connector = aiohttp.TCPConnector(
            resolver=_PublicOnlyResolver(allow_private=allow_private_urls)
        )
        headers = {"X-Save-Token": token} if token and is_local_add_on_host(uri) else None
        # ``trust_env=False`` explicitly: do NOT inherit HTTP_PROXY / HTTPS_PROXY
        # / NO_PROXY / .netrc from the environment. aiohttp defaults to False
        # already; pinning it keeps the SSRF-hardened resolver authoritative and
        # guards against a future env-proxy leak that would bypass our DNS gate.
        async with (
            aiohttp.ClientSession(connector=connector, trust_env=False) as session,
            session.get(
                uri, timeout=FETCH_TIMEOUT, allow_redirects=False, headers=headers
            ) as response,
        ):
            if 300 <= response.status < 400:
                raise ValueError(
                    f"Refusing redirect from '{redact_uri(uri)}' (status {response.status})"
                )
            response.raise_for_status()
            if response.content_length is not None and response.content_length > MAX_RESPONSE_BYTES:
                raise ValueError(
                    f"Response from '{redact_uri(uri)}' too large: {response.content_length} bytes"
                )
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.content.iter_chunked(65536):
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise ValueError(f"Response from '{redact_uri(uri)}' exceeded max size")
                chunks.append(chunk)
            return b"".join(chunks).decode(response.charset or "utf-8")

    if parsed.scheme and parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URI scheme: {parsed.scheme}")

    return await hass.async_add_executor_job(read_local_file, hass.config.config_dir, uri)


def read_local_file(config_dir: str, uri: str) -> str:
    """Read a zone file from the config directory.

    Sync on purpose: the mutation services run it inside their executor job,
    under the file lock, so the read cannot straddle another write.
    """
    return safe_config_path(config_dir, uri).read_text(encoding="utf-8")


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

    if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        # Source removed or unavailable: GPS attributes are cleared, so the
        # check below would filter this event out. Always trigger, so
        # _update_state's unavailable branch (which re-reads live state) runs;
        # otherwise a source going unavailable was never reflected.
        return True
    if old_state is None:
        # First state a tracker ever reports, for one created after setup: no
        # previous position to compare against, so trigger whenever it already
        # carries a fix. The initial load covers trackers that existed at setup.
        return all(attr in new_state.attributes for attr in REQUIRED_ATTRIBUTES)
    if not all(attr in new_state.attributes for attr in REQUIRED_ATTRIBUTES):
        return False
    # the old state's attributes are missing when it is the first real update
    if not all(attr in old_state.attributes for attr in REQUIRED_ATTRIBUTES):
        return True

    return any(
        new_state.attributes[attr] != old_state.attributes[attr] for attr in REQUIRED_ATTRIBUTES
    )
