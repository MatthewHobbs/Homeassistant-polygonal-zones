"""HTTP-fetch branch of utils.general.load_data — mocked aiohttp roundtrip."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.polygonal_zones.utils.general import (
    _PublicOnlyResolver,
    load_data,
)


def _hass(tmp_path) -> SimpleNamespace:
    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=aaej,
    )


class _FakeResponse:
    """Minimal aiohttp response stand-in supporting the fields load_data uses."""

    def __init__(
        self, *, status: int = 200, body: bytes = b'{"ok": true}', charset: str = "utf-8"
    ) -> None:
        self.status = status
        self._body = body
        self.charset = charset
        self.content_length = len(body)

        async def _iter(_chunk_size: int):
            yield body

        self.content = SimpleNamespace(iter_chunked=_iter)

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def get(self, *_a, **_kw) -> _FakeResponse:
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def close(self) -> None:
        return None


async def test_load_data_http_returns_decoded_body(tmp_path) -> None:
    response = _FakeResponse(body=b'{"hello": "world"}')

    with (
        patch(
            "custom_components.polygonal_zones.utils.general.aiohttp.TCPConnector",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.polygonal_zones.utils.general.aiohttp.ClientSession",
            return_value=_FakeSession(response),
        ),
    ):
        content = await load_data("https://example.com/zones.json", _hass(tmp_path))

    assert content == '{"hello": "world"}'


async def test_load_data_rejects_3xx(tmp_path) -> None:
    response = _FakeResponse(status=302)
    with (
        patch(
            "custom_components.polygonal_zones.utils.general.aiohttp.TCPConnector",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.polygonal_zones.utils.general.aiohttp.ClientSession",
            return_value=_FakeSession(response),
        ),
        pytest.raises(ValueError),
    ):
        await load_data("https://example.com/zones.json", _hass(tmp_path))


async def test_load_data_rejects_oversized_content_length(tmp_path) -> None:
    body = b"x" * 32
    response = _FakeResponse(body=body)
    response.content_length = 10 * 1024 * 1024  # advertise 10 MiB → over the cap
    with (
        patch(
            "custom_components.polygonal_zones.utils.general.aiohttp.TCPConnector",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.polygonal_zones.utils.general.aiohttp.ClientSession",
            return_value=_FakeSession(response),
        ),
        pytest.raises(ValueError),
    ):
        await load_data("https://example.com/zones.json", _hass(tmp_path))


async def test_public_only_resolver_filters_private_addresses() -> None:
    resolver = _PublicOnlyResolver()
    private = [{"host": "10.0.0.1"}]
    with (
        patch.object(resolver, "_resolver", create=True),
        patch(
            "aiohttp.resolver.DefaultResolver.resolve",
            new=AsyncMock(return_value=private),
        ),
        pytest.raises(OSError),
    ):
        await resolver.resolve("evil.example", 443)


async def test_public_only_resolver_accepts_public_addresses() -> None:
    resolver = _PublicOnlyResolver()
    public = [{"host": "8.8.8.8"}]
    with patch(
        "aiohttp.resolver.DefaultResolver.resolve",
        new=AsyncMock(return_value=public),
    ):
        infos = await resolver.resolve("example.com", 443)
        assert infos == public


async def test_public_only_resolver_allow_private_accepts_private_addresses() -> None:
    """With allow_private=True a private IP is permitted (LAN add-on path)."""
    resolver = _PublicOnlyResolver(allow_private=True)
    private = [{"host": "192.168.1.50"}]
    with patch(
        "aiohttp.resolver.DefaultResolver.resolve",
        new=AsyncMock(return_value=private),
    ):
        infos = await resolver.resolve("addon.local", 8000)
        assert infos == private


@pytest.mark.parametrize("flag", [True, False])
async def test_load_data_wires_allow_private_urls_to_resolver(tmp_path, flag) -> None:
    """End-to-end wiring: the allow_private_urls argument to load_data must reach the
    SSRF resolver's allow_private setting. A regression here would silently re-block
    (or un-block) LAN URLs without any unit test noticing."""
    captured = {}

    def fake_connector(*_a, resolver=None, **_k):
        captured["resolver"] = resolver
        return MagicMock()

    with (
        patch(
            "custom_components.polygonal_zones.utils.general.aiohttp.TCPConnector",
            side_effect=fake_connector,
        ),
        patch(
            "custom_components.polygonal_zones.utils.general.aiohttp.ClientSession",
            return_value=_FakeSession(_FakeResponse()),
        ),
    ):
        await load_data("https://example.com/zones.json", _hass(tmp_path), allow_private_urls=flag)

    assert isinstance(captured["resolver"], _PublicOnlyResolver)
    assert captured["resolver"]._allow_private is flag
