"""Tests for the domain-wide reload_all_zones action."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.polygonal_zones.const import CONF_DISCOVERED_BY_ADDON, DOMAIN
from custom_components.polygonal_zones.services import reload_all_zones


def _entry(entry_id: str, source=None, *, runtime_data=True, discovered=False):
    data = SimpleNamespace(source=source) if runtime_data else None
    entry_data = {CONF_DISCOVERED_BY_ADDON: True} if discovered else {}
    return SimpleNamespace(entry_id=entry_id, data=entry_data, runtime_data=data)


def _hass(*entries) -> SimpleNamespace:
    return SimpleNamespace(
        config_entries=SimpleNamespace(async_loaded_entries=MagicMock(return_value=list(entries)))
    )


def _fresh() -> None:
    reload_all_zones._last_reload.clear()


async def test_reloads_every_loaded_entry_once() -> None:
    _fresh()
    first, second = AsyncMock(), AsyncMock()
    hass = _hass(_entry("a", first), _entry("b", second))

    await reload_all_zones.action_builder(hass)(SimpleNamespace())

    first.async_reload.assert_awaited_once_with(hass)
    second.async_reload.assert_awaited_once_with(hass)
    hass.config_entries.async_loaded_entries.assert_called_once_with(DOMAIN)


async def test_skips_an_entry_without_a_source() -> None:
    _fresh()
    source = AsyncMock()
    hass = _hass(_entry("a", source), _entry("b", None, runtime_data=False))

    await reload_all_zones.action_builder(hass)(SimpleNamespace())

    source.async_reload.assert_awaited_once_with(hass)


async def test_a_second_call_waits_for_the_floor_and_still_reloads() -> None:
    """Two saves in quick succession must both be reloaded.

    The earlier version dropped the second one silently, so the editor
    reported success while Home Assistant kept the older zones.
    """
    _fresh()
    source = AsyncMock()
    hass = _hass(_entry("a", source))
    reload_all_zones._last_reload["a"] = time.monotonic()

    sleep = AsyncMock()
    with patch.object(reload_all_zones.asyncio, "sleep", sleep):
        await reload_all_zones.action_builder(hass)(SimpleNamespace())

    sleep.assert_awaited_once()
    (waited,) = sleep.await_args.args
    assert 0 < waited <= reload_all_zones.RELOAD_FLOOR_SECONDS
    source.async_reload.assert_awaited_once_with(hass)


async def test_outside_the_floor_it_does_not_wait() -> None:
    _fresh()
    source = AsyncMock()
    hass = _hass(_entry("a", source))
    reload_all_zones._last_reload["a"] = (
        time.monotonic() - reload_all_zones.RELOAD_FLOOR_SECONDS - 1
    )

    sleep = AsyncMock()
    with patch.object(reload_all_zones.asyncio, "sleep", sleep):
        await reload_all_zones.action_builder(hass)(SimpleNamespace())

    sleep.assert_not_awaited()
    source.async_reload.assert_awaited_once_with(hass)


async def test_a_failing_manual_entry_warns_without_raising_when_addon_entry_succeeds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A broken hand-configured entry must not make the add-on's save fail."""
    _fresh()
    broken = AsyncMock()
    broken.async_reload.side_effect = RuntimeError("dead host")
    healthy = AsyncMock()
    hass = _hass(
        _entry("manual", broken, discovered=False),
        _entry("addon", healthy, discovered=True),
    )

    await reload_all_zones.action_builder(hass)(SimpleNamespace())

    broken.async_reload.assert_awaited_once_with(hass)
    healthy.async_reload.assert_awaited_once_with(hass)
    assert "Could not reload zones for entry manual: dead host" in caplog.text


async def test_a_failing_addon_entry_raises_after_reloading_other_entries() -> None:
    """When the add-on-discovered entry fails to reload, the call raises so
    the add-on reports that Home Assistant could not re-read the zones."""
    _fresh()
    broken_addon = AsyncMock()
    broken_addon.async_reload.side_effect = RuntimeError("addon down")
    healthy_manual = AsyncMock()
    hass = _hass(
        _entry("addon", broken_addon, discovered=True),
        _entry("manual", healthy_manual, discovered=False),
    )

    with pytest.raises(HomeAssistantError, match=r"addon: addon down"):
        await reload_all_zones.action_builder(hass)(SimpleNamespace())

    broken_addon.async_reload.assert_awaited_once_with(hass)
    healthy_manual.async_reload.assert_awaited_once_with(hass)
