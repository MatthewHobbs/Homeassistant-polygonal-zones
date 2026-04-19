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
