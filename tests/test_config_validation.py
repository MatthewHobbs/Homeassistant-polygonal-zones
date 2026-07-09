"""Tests for utils.config_validation.validate_zone_urls."""

import asyncio
from types import SimpleNamespace

from custom_components.polygonal_zones.utils.config_validation import (
    validate_zone_urls,
)


def _hass(tmp_path) -> SimpleNamespace:
    """Minimal hass stub — only the attributes ``validate_zone_urls`` reaches into."""
    config = SimpleNamespace(config_dir=str(tmp_path))

    async def async_add_executor_job(func, *args):
        return func(*args)

    return SimpleNamespace(config=config, async_add_executor_job=async_add_executor_job)


def _run(coro):
    return asyncio.run(coro)


def test_http_url_with_no_hostname_rejected(tmp_path) -> None:
    """A malformed http URL like ``http://`` (no host) must surface invalid_url."""
    hass = _hass(tmp_path)
    errors = _run(validate_zone_urls(["http:///path-only"], hass))
    assert errors == {"zone_urls": "invalid_url"}


def test_unsupported_scheme_rejected(tmp_path) -> None:
    """Schemes other than http/https are refused."""
    hass = _hass(tmp_path)
    errors = _run(validate_zone_urls(["ftp://example.com/zones.json"], hass))
    assert errors == {"zone_urls": "invalid_url"}


def test_valid_https_url_accepted(tmp_path) -> None:
    hass = _hass(tmp_path)
    errors = _run(validate_zone_urls(["https://example.com/zones.json"], hass))
    assert errors == {}


def test_existing_local_file_accepted(tmp_path) -> None:
    f = tmp_path / "zones.json"
    f.write_text("{}")
    hass = _hass(tmp_path)
    errors = _run(validate_zone_urls(["zones.json"], hass))
    assert errors == {}


def test_missing_local_file_rejected(tmp_path) -> None:
    hass = _hass(tmp_path)
    errors = _run(validate_zone_urls(["nonexistent.json"], hass))
    assert errors == {"zone_urls": "invalid_path"}


def test_path_traversal_rejected(tmp_path) -> None:
    """A relative path that escapes config_dir must surface invalid_path."""
    hass = _hass(tmp_path)
    errors = _run(validate_zone_urls(["../../../etc/hosts"], hass))
    assert errors == {"zone_urls": "invalid_path"}


def test_empty_entries_skipped(tmp_path) -> None:
    """Empty/None entries in the list must not fail validation."""
    hass = _hass(tmp_path)
    errors = _run(validate_zone_urls(["", "https://example.com/zones.json"], hass))
    assert errors == {}


def test_mixed_valid_and_invalid_rejected(tmp_path) -> None:
    """If any entry is invalid, the whole call fails (``all`` semantics)."""
    hass = _hass(tmp_path)
    errors = _run(
        validate_zone_urls(
            ["https://example.com/zones.json", "ftp://nope.example/zones.json"], hass
        )
    )
    assert errors == {"zone_urls": "invalid_url"}


def test_literal_private_ip_blocked_with_actionable_error(tmp_path) -> None:
    """A LAN IP URL with allow_private off gets the specific toggle-naming error,
    not a generic invalid_url — this is the primary add-on onboarding case."""
    hass = _hass(tmp_path)
    errors = _run(validate_zone_urls(["http://192.168.1.5:8000/zones.json"], hass))
    assert errors == {"zone_urls": "private_url_blocked"}


def test_literal_loopback_ip_blocked(tmp_path) -> None:
    hass = _hass(tmp_path)
    errors = _run(validate_zone_urls(["http://127.0.0.1:8000/zones.json"], hass))
    assert errors == {"zone_urls": "private_url_blocked"}


def test_private_ip_accepted_when_allow_private_urls(tmp_path) -> None:
    """With the toggle on, the same LAN URL passes validation."""
    hass = _hass(tmp_path)
    errors = _run(
        validate_zone_urls(["http://192.168.1.5:8000/zones.json"], hass, allow_private_urls=True)
    )
    assert errors == {}


def test_public_hostname_not_flagged_as_private(tmp_path) -> None:
    """A non-literal-IP hostname is left to the fetch-time resolver, not blocked here."""
    hass = _hass(tmp_path)
    errors = _run(validate_zone_urls(["https://example.com/zones.json"], hass))
    assert errors == {}
