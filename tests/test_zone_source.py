"""Tests for the entry-scoped ZoneSource — load lifecycle, retry, listeners."""

import asyncio
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
    # Both the load-failure issue and the (unset, so always-clear) home-zone
    # issue are cleared on a successful load.
    cleared = {call.args[2] for call in del_issue.call_args_list}
    assert cleared == {src.issue_id, src.home_zone_missing_issue_id}


async def test_load_success_matching_home_zone_clears_issue() -> None:
    """A configured home_zone_id that matches a loaded zone clears the repair issue."""
    src = ZoneSource("entry-1", ["http://x"], False, False, home_zone_id="Home")
    with (
        patch(
            "custom_components.polygonal_zones.zone_source.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=_ZONES)),
        ),
        patch("custom_components.polygonal_zones.zone_source.ir.async_delete_issue") as del_issue,
        patch(
            "custom_components.polygonal_zones.zone_source.ir.async_create_issue"
        ) as create_issue,
    ):
        await src._async_initial_load(_hass())

    create_issue.assert_not_called()
    cleared = {call.args[2] for call in del_issue.call_args_list}
    assert src.home_zone_missing_issue_id in cleared


async def test_load_success_missing_home_zone_raises_issue() -> None:
    """A configured home_zone_id that matches nothing raises the repair issue —
    checked on every (re)load, since a rename/deletion can invalidate it later."""
    src = ZoneSource("entry-1", ["http://x"], False, False, home_zone_id="Not A Real Zone")
    with (
        patch(
            "custom_components.polygonal_zones.zone_source.load_zones",
            new=AsyncMock(return_value=ZoneLoadResult(zones=_ZONES)),
        ),
        patch("custom_components.polygonal_zones.zone_source.ir.async_delete_issue"),
        patch(
            "custom_components.polygonal_zones.zone_source.ir.async_create_issue"
        ) as create_issue,
    ):
        await src._async_initial_load(_hass())

    create_issue.assert_called_once()
    _hass_arg, domain, issue_id = create_issue.call_args.args
    assert domain == "polygonal_zones"
    assert issue_id == src.home_zone_missing_issue_id
    placeholders = create_issue.call_args.kwargs["translation_placeholders"]
    assert placeholders == {"entry_id": "entry-1", "home_zone_id": "Not A Real Zone"}


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
    """The retry closure must be a HA ``@callback`` so it runs on the event loop (#39)."""
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
    cleared = {call.args[2] for call in del_issue.call_args_list}
    assert cleared == {src.issue_id, src.home_zone_missing_issue_id}


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


def _executor_hass() -> SimpleNamespace:
    """A hass whose executor hands back a real Future, as Home Assistant's does."""

    def run(func, *args):
        return asyncio.get_running_loop().run_in_executor(None, func, *args)

    return SimpleNamespace(async_add_executor_job=run)


_GET = "custom_components.polygonal_zones.zone_source.get_locations_zone"


async def test_resolve_runs_the_geometry_once_for_concurrent_callers() -> None:
    """The mirror and the zone sensor ask the same question for one position."""
    src = _source()
    src.zones = _ZONES
    calls = []

    def fake(lat, lon, acc, zones):
        calls.append((lat, lon, acc))
        return {"name": "Home", "zone_key": "Home", "matched_zones": ["Home"]}

    with patch(_GET, side_effect=fake):
        a, b = await asyncio.gather(
            src.async_resolve(_executor_hass(), 0.5, 0.5, 10),
            src.async_resolve(_executor_hass(), 0.5, 0.5, 10),
        )
        again = await src.async_resolve(_executor_hass(), 0.5, 0.5, 10)

    assert len(calls) == 1
    assert a == b == again
    assert a["name"] == "Home"


async def test_resolve_hands_each_caller_its_own_copy() -> None:
    src = _source()
    src.zones = _ZONES

    with patch(_GET, return_value={"name": "Home", "zone_key": "Home", "matched_zones": ["Home"]}):
        first = await src.async_resolve(_executor_hass(), 0.5, 0.5, 10)
        first["matched_zones"].append("changed")
        second = await src.async_resolve(_executor_hass(), 0.5, 0.5, 10)

    assert second["matched_zones"] == ["Home"]


async def test_resolve_recomputes_after_the_zones_change() -> None:
    """A cached answer for the old zones must never be served for the new ones."""
    src = _source()
    src.zones = _ZONES
    results = iter([{"name": "Old", "zone_key": "Old", "matched_zones": []}, None])

    with patch(_GET, side_effect=lambda *_a: next(results)):
        assert (await src.async_resolve(_executor_hass(), 0.5, 0.5, 10))["name"] == "Old"
        src.zones = []  # e.g. a reload that dropped the zone
        assert await src.async_resolve(_executor_hass(), 0.5, 0.5, 10) is None


async def test_resolve_does_not_cache_a_failure() -> None:
    src = _source()
    src.zones = _ZONES
    outcomes = iter(
        [RuntimeError("boom"), {"name": "Home", "zone_key": "Home", "matched_zones": []}]
    )

    def fake(*_a):
        out = next(outcomes)
        if isinstance(out, Exception):
            raise out
        return out

    with patch(_GET, side_effect=fake):
        with pytest.raises(RuntimeError):
            await src.async_resolve(_executor_hass(), 0.5, 0.5, 10)
        assert (await src.async_resolve(_executor_hass(), 0.5, 0.5, 10))["name"] == "Home"


async def test_resolve_cache_is_bounded() -> None:
    from custom_components.polygonal_zones import zone_source as zs

    src = _source()
    src.zones = _ZONES

    with patch(_GET, return_value=None):
        for i in range(zs._RESOLVE_CACHE_MAX + 5):
            await src.async_resolve(_executor_hass(), float(i), 0.0, 1)

    assert len(src._resolved) <= zs._RESOLVE_CACHE_MAX


async def test_cancelling_one_caller_does_not_cancel_the_run_another_waits_on() -> None:
    """A platform-add timeout or an unload cancels one entity's update; the sibling
    entity asking for the same position must still get its answer, and later calls
    must not be poisoned by the cancellation."""
    import threading

    src = _source()
    src.zones = _ZONES
    release = threading.Event()
    calls = []

    def slow(lat, lon, acc, zones):
        calls.append(1)
        release.wait(5)
        return {"name": "Home", "zone_key": "Home", "matched_zones": ["Home"]}

    with patch(_GET, side_effect=slow):
        first = asyncio.ensure_future(src.async_resolve(_executor_hass(), 0.5, 0.5, 10))
        second = asyncio.ensure_future(src.async_resolve(_executor_hass(), 0.5, 0.5, 10))
        await asyncio.sleep(0.05)  # both are now waiting on the one run
        first.cancel()
        await asyncio.sleep(0)
        release.set()

        assert (await second)["name"] == "Home"
        assert first.cancelled()
        again = await src.async_resolve(_executor_hass(), 0.5, 0.5, 10)

    assert again["name"] == "Home"
    assert len(calls) == 1  # the run was shared, not restarted


async def test_a_run_nobody_awaits_any_more_is_still_evicted_when_it_fails() -> None:
    """Only the done-callback can do this: the one caller was cancelled while the run
    was still going, so no await is left on the failure path to evict it."""
    import contextlib
    import threading

    src = _source()
    src.zones = _ZONES
    release = threading.Event()

    def boom(*_a):
        release.wait(5)
        raise RuntimeError("boom")

    with patch(_GET, side_effect=boom):
        caller = asyncio.ensure_future(src.async_resolve(_executor_hass(), 0.5, 0.5, 10))
        await asyncio.sleep(0.05)  # the run is in flight, blocked in the executor
        (run,) = src._resolved.values()
        caller.cancel()
        await asyncio.sleep(0)
        assert len(src._resolved) == 1  # still shared: only the caller was cancelled
        release.set()
        # Wait for the run itself, not a fixed delay, so a slow runner cannot flake.
        with contextlib.suppress(RuntimeError):
            await run
        await asyncio.sleep(0)  # let its done-callbacks run

    assert src._resolved == {}
