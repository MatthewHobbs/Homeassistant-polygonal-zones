"""Tests for utils.general — path containment + state-change filter."""

from types import SimpleNamespace

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
import pytest

from custom_components.polygonal_zones.utils.general import (
    event_should_trigger,
    is_local_add_on_host,
    redact_text,
    redact_uri,
    safe_config_path,
)


def test_redact_uri_strips_credentials_and_query() -> None:
    assert (
        redact_uri("http://user:pass@10.0.0.9:8000/zones.json?token=secret")
        == "http://10.0.0.9:8000/zones.json"
    )


def test_redact_uri_keeps_plain_http_url_intact() -> None:
    assert redact_uri("https://example.com/zones.json") == "https://example.com/zones.json"


def test_redact_uri_passes_through_non_http() -> None:
    # File paths and non-http schemes carry no credential component; unchanged.
    assert redact_uri("/config/zones.json") == "/config/zones.json"
    assert redact_uri("ftp://host/x") == "ftp://host/x"


def test_redact_uri_malformed_port_does_not_raise() -> None:
    """A non-numeric port makes urlparse.port raise ValueError; redact must degrade
    to the raw string rather than crash a diagnostics dump."""
    assert redact_uri("http://example.com:bad/zones.json") == "http://example.com:bad/zones.json"


def test_redact_uri_malformed_port_still_strips_credentials_and_query() -> None:
    """A URI urlparse cannot take apart must not be returned raw."""
    out = redact_uri("http://u:p@host:bad/x?token=T#frag")
    assert out == "http://host:bad/x"


def test_redact_uri_keeps_ipv6_brackets() -> None:
    assert redact_uri("http://[fd00::1]:8000/z?t=1") == "http://[fd00::1]:8000/z"
    assert redact_uri("https://[::1]/z") == "https://[::1]/z"


def test_redact_text_cleans_urls_inside_an_aiohttp_error() -> None:
    """aiohttp's own message holds a URL it already rewrote (credentials dropped,
    query kept), which a literal replace of the configured string cannot match."""
    import aiohttp
    from yarl import URL

    raw = "https://user:pa55@zones.example.com/z.json?token=s3cr3t"
    info = aiohttp.RequestInfo(
        url=URL(raw), method="GET", headers={}, real_url=URL(raw).with_user(None)
    )
    err = aiohttp.ClientResponseError(info, (), status=401, message="Unauthorized")

    assert "s3cr3t" in str(err)  # the premise: the raw error does leak
    cleaned = redact_text(str(err))

    assert "s3cr3t" not in cleaned
    assert "pa55" not in cleaned
    assert "https://zones.example.com/z.json" in cleaned


def test_is_local_add_on_host_private_ipv4() -> None:
    assert is_local_add_on_host("http://192.168.1.50:8000/zones.json") is True


def test_is_local_add_on_host_loopback() -> None:
    assert is_local_add_on_host("http://127.0.0.1:8000/zones.json") is True


def test_is_local_add_on_host_link_local() -> None:
    assert is_local_add_on_host("http://169.254.1.2/zones.json") is True


def test_is_local_add_on_host_dot_local_name() -> None:
    assert is_local_add_on_host("http://polygonal-zones-editor.local/zones.json") is True


def test_is_local_add_on_host_localhost_name() -> None:
    assert is_local_add_on_host("http://localhost:8000/zones.json") is True


def test_is_local_add_on_host_public_url() -> None:
    assert is_local_add_on_host("https://example.com/zones.json") is False


def test_is_local_add_on_host_public_ip() -> None:
    assert is_local_add_on_host("http://8.8.8.8/zones.json") is False


def test_is_local_add_on_host_non_http_scheme() -> None:
    # File paths / non-http schemes are never add-on-classified.
    assert is_local_add_on_host("/config/zones.json") is False
    assert is_local_add_on_host("ftp://192.168.1.50/zones.json") is False


def test_is_local_add_on_host_no_hostname() -> None:
    assert is_local_add_on_host("http://") is False


def test_download_zone_relative_path() -> None:
    from custom_components.polygonal_zones.utils.general import download_zone_relative_path

    assert download_zone_relative_path("abc123") == "polygonal_zones/abc123.json"


def test_safe_config_path_inside_config_dir(tmp_path) -> None:
    """A simple relative path resolves to the expected location inside config_dir."""
    target = tmp_path / "polygonal_zones" / "entry.json"
    target.parent.mkdir()
    target.write_text("{}")
    resolved = safe_config_path(str(tmp_path), "polygonal_zones/entry.json")
    assert resolved == target


def test_safe_config_path_traversal_blocked(tmp_path) -> None:
    """A ``..`` traversal that escapes config_dir must raise ValueError."""
    with pytest.raises(ValueError):
        safe_config_path(str(tmp_path), "../../../etc/passwd")


def test_safe_config_path_absolute_path_treated_as_relative(tmp_path) -> None:
    """Leading slashes are stripped so absolute-looking input stays inside config_dir."""
    target = tmp_path / "absolute" / "thing.json"
    target.parent.mkdir()
    target.write_text("{}")
    resolved = safe_config_path(str(tmp_path), "/absolute/thing.json")
    assert resolved == target


def test_safe_config_path_symlink_escape_blocked(tmp_path) -> None:
    """A symlink inside config_dir pointing outside must be rejected by resolve()."""
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret")
    link = tmp_path / "evil"
    link.symlink_to(outside)
    with pytest.raises(ValueError):
        safe_config_path(str(tmp_path), "evil")


# event_should_trigger uses event.data.get(...) and state.attributes only —
# SimpleNamespace is enough; no HA fixtures needed.

REQUIRED = {"latitude": 1.0, "longitude": 2.0, "gps_accuracy": 5}


def _state(attributes: dict, state: str = "not_home") -> SimpleNamespace:
    return SimpleNamespace(attributes=attributes, state=state)


def _event(
    entity_id: str,
    old_attrs: dict | None,
    new_attrs: dict | None,
    *,
    new_state: str = "not_home",
) -> SimpleNamespace:
    return SimpleNamespace(
        data={
            "entity_id": entity_id,
            "old_state": _state(old_attrs) if old_attrs is not None else None,
            "new_state": _state(new_attrs, new_state) if new_attrs is not None else None,
        }
    )


def test_event_for_other_entity_ignored() -> None:
    event = _event("device_tracker.someone_else", REQUIRED, REQUIRED)
    assert event_should_trigger(event, "device_tracker.me") is False


def test_missing_gps_accuracy_does_not_trigger() -> None:
    """A new state missing one of the required GPS attrs must not fire the listener."""
    new_attrs = {"latitude": 1.0, "longitude": 2.0}  # no gps_accuracy
    event = _event("device_tracker.me", REQUIRED, new_attrs)
    assert event_should_trigger(event, "device_tracker.me") is False


def test_first_update_with_old_state_missing_attrs_triggers() -> None:
    """When the previous state lacks GPS attrs (first real update), allow the trigger."""
    event = _event("device_tracker.me", {}, REQUIRED)
    assert event_should_trigger(event, "device_tracker.me") is True


def test_unchanged_location_does_not_trigger() -> None:
    event = _event("device_tracker.me", REQUIRED, REQUIRED)
    assert event_should_trigger(event, "device_tracker.me") is False


def test_changed_latitude_triggers() -> None:
    new_attrs = {**REQUIRED, "latitude": 1.5}
    event = _event("device_tracker.me", REQUIRED, new_attrs)
    assert event_should_trigger(event, "device_tracker.me") is True


def test_no_prior_state_does_not_trigger() -> None:
    """A truly first-ever event (old_state is None) does not trigger — covered instead
    by the entity's own initial-load path, not this per-event listener."""
    event = _event("device_tracker.me", None, REQUIRED)
    assert event_should_trigger(event, "device_tracker.me") is False


def test_source_removed_triggers() -> None:
    """Source entity removed (new_state is None) must trigger, so _update_state's own
    live-state lookup can reflect the removal — this was the reported bug."""
    event = _event("device_tracker.me", REQUIRED, None)
    assert event_should_trigger(event, "device_tracker.me") is True


def test_source_unavailable_triggers_despite_missing_gps_attrs() -> None:
    """A source going unavailable normally clears its GPS attributes too — must still
    trigger so the mirror reflects it, instead of silently keeping stale state."""
    event = _event("device_tracker.me", REQUIRED, {}, new_state=STATE_UNAVAILABLE)
    assert event_should_trigger(event, "device_tracker.me") is True


def test_source_unknown_triggers_despite_missing_gps_attrs() -> None:
    event = _event("device_tracker.me", REQUIRED, {}, new_state=STATE_UNKNOWN)
    assert event_should_trigger(event, "device_tracker.me") is True


def test_redact_text_survives_a_raw_quote_in_the_query() -> None:
    """yarl keeps a raw ' in the query, so Python's repr of the aiohttp error switches
    to "..." quoting: a URL pattern that stops at the first ' left the token behind."""
    import aiohttp
    from yarl import URL

    raw = "https://h.example/z?n=o'b&token=SECRET"
    info = aiohttp.RequestInfo(url=URL(raw), method="GET", headers={}, real_url=URL(raw))
    err = aiohttp.ClientResponseError(info, (), status=404, message="Not Found")

    assert "SECRET" in str(err)  # the premise: the raw error does leak
    assert "SECRET" not in redact_text(str(err))
    assert "SECRET" not in redact_text(f"Connection timeout to host {raw}")


def test_redact_text_leaves_a_clean_message_readable() -> None:
    msg = "Response from 'https://h/z.json' too large: 99 bytes"
    assert redact_text(msg) == msg


def test_redact_text_strips_userinfo_of_a_url_nested_in_a_path() -> None:
    assert "u:p" not in redact_text("https://proxy/f/https://u:p@x/")


def test_redact_uri_without_a_host_does_not_fail_open() -> None:
    out = redact_uri("http://u:p@/x?t=1")
    assert "u:p" not in out
    assert "t=1" not in out


def test_redact_uri_fallback_survives_a_malformed_password() -> None:
    """A password holding ? or / is invalid, but old entries may still carry one."""
    assert "u:p" not in redact_uri("http://u:p?x@h/")
    assert "u:p" not in redact_uri("http://u:p/x@h:bad/")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # urlparse reads these as host-less; they used to come back raw.
        ("http:u:p@h?t=S", "http:h"),
        ("https:/u:p@h/z?t=S", "https:/h/z"),
        ("http:///u:p@h/z", "http://h/z"),
        ("http://@@h", "http://h"),
        ("http://u:p@h@h2/x?t=1", "http://h2/x"),
        # A malformed port sends the URI through the same fallback.
        ("http://u:p@host:bad/x?token=T#frag", "http://host:bad/x"),
    ],
)
def test_redact_uri_fallback_exact_output(raw: str, expected: str) -> None:
    out = redact_uri(raw)
    assert out == expected
    assert "u:p" not in out
    assert "S" not in out.replace("host", "")  # no token letters left either


def test_redact_text_userinfo_pass_does_not_cross_a_query() -> None:
    """An @ in a query value is not userinfo: it must not eat the host and leak the token."""
    assert redact_text("https://h?e=me@x.io&token=S") == "https://h"
