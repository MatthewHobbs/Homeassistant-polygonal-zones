"""Tests for utils.general.load_data — file path branch + scheme guards."""

import ipaddress
from types import SimpleNamespace

import pytest

from custom_components.polygonal_zones.utils.general import (
    _is_public_ip,
    load_data,
)


def _make_hass(tmp_path) -> SimpleNamespace:
    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        async_add_executor_job=aaej,
    )


async def test_load_data_reads_local_file(tmp_path) -> None:
    f = tmp_path / "zones.json"
    f.write_text('{"hello": "world"}')
    hass = _make_hass(tmp_path)

    content = await load_data("zones.json", hass)
    assert content == '{"hello": "world"}'


async def test_load_data_rejects_unsupported_scheme(tmp_path) -> None:
    hass = _make_hass(tmp_path)
    with pytest.raises(ValueError):
        await load_data("ftp://example.com/zones.json", hass)


async def test_load_data_rejects_url_with_no_hostname(tmp_path) -> None:
    hass = _make_hass(tmp_path)
    with pytest.raises(ValueError):
        await load_data("http:///no-host", hass)


async def test_load_data_rejects_traversal(tmp_path) -> None:
    hass = _make_hass(tmp_path)
    with pytest.raises(ValueError):
        await load_data("../../../etc/hosts", hass)


def test_is_public_ip_rejects_private() -> None:
    assert not _is_public_ip(ipaddress.ip_address("10.0.0.1"))
    assert not _is_public_ip(ipaddress.ip_address("192.168.1.1"))
    assert not _is_public_ip(ipaddress.ip_address("172.16.0.1"))
    assert not _is_public_ip(ipaddress.ip_address("127.0.0.1"))
    assert not _is_public_ip(ipaddress.ip_address("169.254.169.254"))
    assert not _is_public_ip(ipaddress.ip_address("0.0.0.0"))
    assert not _is_public_ip(ipaddress.ip_address("224.0.0.1"))


def test_is_public_ip_accepts_public() -> None:
    assert _is_public_ip(ipaddress.ip_address("8.8.8.8"))
    assert _is_public_ip(ipaddress.ip_address("1.1.1.1"))


@pytest.mark.parametrize(
    ("address", "label"),
    [
        ("::1", "IPv6 loopback"),
        ("fd00::1", "IPv6 unique-local (ULA, RFC 4193)"),
        ("fc00::1", "IPv6 unique-local (fc00::/7 lower half)"),
        ("fe80::1", "IPv6 link-local (RFC 4291)"),
        ("ff02::1", "IPv6 multicast"),
        ("::", "IPv6 unspecified"),
        ("::ffff:7f00:1", "IPv4-mapped IPv6 loopback (::ffff:127.0.0.1)"),
        ("::ffff:a00:1", "IPv4-mapped IPv6 private (::ffff:10.0.0.1)"),
    ],
)
def test_is_public_ip_rejects_ipv6_non_public(address: str, label: str) -> None:
    """IPv6 private / loopback / link-local / multicast / mapped-private ranges must fail the SSRF gate."""
    assert not _is_public_ip(ipaddress.ip_address(address)), label


@pytest.mark.parametrize(
    "address",
    [
        "2001:4860:4860::8888",  # Google DNS v6
        "2606:4700:4700::1111",  # Cloudflare DNS v6
    ],
)
def test_is_public_ip_accepts_ipv6_public(address: str) -> None:
    assert _is_public_ip(ipaddress.ip_address(address))


@pytest.mark.parametrize(
    "address",
    [
        "192.168.1.50",
        "10.0.0.1",
        "172.16.5.10",
        "fd00::1",  # IPv6 ULA
    ],
)
def test_is_public_ip_allow_private_accepts_rfc1918(address: str) -> None:
    """allow_private=True opens the RFC-1918 / ULA bucket specifically."""
    assert _is_public_ip(ipaddress.ip_address(address), allow_private=True)


@pytest.mark.parametrize(
    ("address", "label"),
    [
        ("127.0.0.1", "loopback stays blocked"),
        ("::1", "IPv6 loopback stays blocked"),
        ("169.254.169.254", "cloud-metadata link-local stays blocked"),
        ("fe80::1", "IPv6 link-local stays blocked"),
        ("224.0.0.1", "multicast stays blocked"),
        ("0.0.0.0", "unspecified stays blocked"),
    ],
)
def test_is_public_ip_allow_private_still_rejects_non_lan(address: str, label: str) -> None:
    """allow_private is scoped to RFC-1918 only — other risky buckets stay blocked."""
    assert not _is_public_ip(ipaddress.ip_address(address), allow_private=True), label
