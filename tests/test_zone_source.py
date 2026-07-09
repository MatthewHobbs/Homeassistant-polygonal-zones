"""Tests for the entry-scoped ZoneSource — load lifecycle, retry, listeners."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from shapely.geometry import Polygon

from custom_components.polygonal_zones.utils.zones import Zone, ZoneFileCorrupt, ZoneLoadResult
from custom_components.polygonal_zones.zone_source import ZoneSource

_ZONES = [Zone(name="Home", geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), priority=0)]


def _hass() -> SimpleNamespace:
    return SimpleNamespace(async_create_task=MagicMock())


def _source(zone_urls=None) -> ZoneSource:
    return ZoneSource("entry-1", ["http://x"] if zone_urls is None else zone_urls, False, False)


async def test_initial_load_success_sets_state_and_notifies() -> None:
    src = _source()
    listener = MagicMock()
    src.add_listener(listener)
    with (
        patch(
            "custom_components.polygonal_zones.zone_source.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=_ZONES)),
        ),
        patch("custom_components.polygonal_zones.zone_source.ir.async_delete_issue") as del_issue,
    ):
        await src._async_initial_load(_hass())

    assert src.loaded_ok is True
    assert src.last_load_result == "ok"
    assert src.zones == _ZONES
    assert src.last_zones_loaded_at is not None
    listener.assert_called_once()
    del_issue.assert_called_once()


async def test_async_load_raises_when_all_uris_fail() -> None:
    src = _source(zone_urls=["http://x"])
    with (
        patch(
            "custom_components.polygonal_zones.zone_source.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=[], failures=[("http://x", "boom")])),
        ),
        pytest.raises(ZoneFileCorrupt),
    ):
        await src._async_load(_hass())
    assert src.loaded_ok is False


async def test_initial_load_failure_arms_jittered_retry() -> None:
    src = _source()
    call_later = MagicMock(return_value=lambda: None)
    with (
        patch(
            "custom_components.polygonal_zones.zone_source.load_zones",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("custom_components.polygonal_zones.zone_source.async_call_later", new=call_later),
    ):
        await src._async_initial_load(_hass(), attempt=1)

    assert src.last_load_result == "failed"
    call_later.assert_called_once()
    delay = call_later.call_args.args[1]
    assert 15 <= delay <= 30  # equal jitter on the 30s base


async def test_retry_closure_reschedules_the_load() -> None:
    """Invoking the armed retry closure schedules another load attempt."""
    src = _source()
    created: list = []
    hass = SimpleNamespace(async_create_task=created.append)

    def fake_call_later(_hass, _delay, callback):
        callback(None)  # fire the retry closure synchronously to cover its body
        return lambda: None

    with (
        patch(
            "custom_components.polygonal_zones.zone_source.load_zones",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "custom_components.polygonal_zones.zone_source.async_call_later",
            side_effect=fake_call_later,
        ),
    ):
        await src._async_initial_load(hass, attempt=1)

    assert len(created) == 1  # the retry scheduled a follow-up attempt
    created[0].close()


async def test_retry_closure_is_hass_callback() -> None:
    """The retry closure must be a HA ``@callback`` so it runs on the event loop.

    Without ``@callback``, HA's job-type inference schedules a plain function
    passed to ``async_call_later`` on the executor thread pool; calling
    ``hass.async_create_task`` from there raises ``RuntimeError`` and the
    retry silently never happens (issue #39 — zones never load, every
    tracked entity gets stuck reporting ``away``).
    """
    from homeassistant.core import is_callback

    src = _source()
    captured: list = []

    def fake_call_later(_hass, _delay, callback):
        captured.append(callback)
        return lambda: None

    with (
        patch(
            "custom_components.polygonal_zones.zone_source.load_zones",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "custom_components.polygonal_zones.zone_source.async_call_later",
            side_effect=fake_call_later,
        ),
    ):
        await src._async_initial_load(_hass(), attempt=1)

    assert len(captured) == 1
    assert is_callback(captured[0]) is True


async def test_initial_load_exhausted_raises_issue_and_notifies() -> None:
    src = _source()
    listener = MagicMock()
    src.add_listener(listener)
    call_later = MagicMock(return_value=lambda: None)
    with (
        patch(
            "custom_components.polygonal_zones.zone_source.load_zones",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("custom_components.polygonal_zones.zone_source.async_call_later", new=call_later),
        patch(
            "custom_components.polygonal_zones.zone_source.ir.async_create_issue"
        ) as create_issue,
    ):
        await src._async_initial_load(_hass(), attempt=5)

    call_later.assert_not_called()
    create_issue.assert_called_once()
    assert create_issue.call_args.args[2] == "zone_load_failed_entry-1"
    assert src.loaded_ok is False
    listener.assert_called_once()  # entities woken to reflect unavailable


async def test_async_reload_success_notifies_and_clears_issue() -> None:
    src = _source()
    listener = MagicMock()
    src.add_listener(listener)
    with (
        patch(
            "custom_components.polygonal_zones.zone_source.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=_ZONES)),
        ),
        patch("custom_components.polygonal_zones.zone_source.ir.async_delete_issue") as del_issue,
    ):
        await src.async_reload(_hass())

    assert src.zones == _ZONES
    listener.assert_called_once()
    del_issue.assert_called_once()


async def test_async_reload_failure_marks_failed_and_raises() -> None:
    src = _source()
    with (
        patch(
            "custom_components.polygonal_zones.zone_source.load_zones",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        pytest.raises(RuntimeError),
    ):
        await src.async_reload(_hass())
    assert src.last_load_result == "failed"


def test_add_listener_returns_working_unsub() -> None:
    src = _source()
    cb = MagicMock()
    remove = src.add_listener(cb)
    src._notify()
    cb.assert_called_once()
    remove()
    src._notify()
    cb.assert_called_once()  # not called again after removal


def test_schedule_initial_load_uses_async_at_started() -> None:
    src = _source()
    with patch(
        "custom_components.polygonal_zones.zone_source.async_at_started",
        return_value=lambda: None,
    ) as at_started:
        src.async_schedule_initial_load(_hass())
    at_started.assert_called_once()


def test_async_shutdown_cancels_pending_callbacks() -> None:
    src = _source()
    unsub_started = MagicMock()
    unsub_retry = MagicMock()
    src._unsub_at_started = unsub_started
    src._unsub_retry = unsub_retry
    src.async_shutdown()
    unsub_started.assert_called_once()
    unsub_retry.assert_called_once()
    assert src._unsub_at_started is None
    assert src._unsub_retry is None
