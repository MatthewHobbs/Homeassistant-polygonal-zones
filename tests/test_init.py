"""Tests for the integration's package-level lifecycle hooks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.polygonal_zones import (
    async_reload_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.polygonal_zones.const import DOMAIN


async def test_async_setup_registers_services_and_seeds_data() -> None:
    """async_setup creates the per-domain dict and registers all four services."""
    hass = SimpleNamespace(data={})
    register_mock = AsyncMock()

    from custom_components import polygonal_zones as pkg

    original = pkg.register_services
    pkg.register_services = register_mock
    try:
        result = await async_setup(hass, {})
    finally:
        pkg.register_services = original

    assert result is True
    assert DOMAIN in hass.data
    register_mock.assert_awaited_once()
    args = register_mock.await_args[0]
    assert sorted(args[1]) == [
        "add_new_zone",
        "delete_zone",
        "edit_zone",
        "replace_all_zones",
    ]


async def test_async_setup_entry_forwards_and_registers_listener() -> None:
    """async_setup_entry calls async_forward_entry_setups + add_update_listener."""
    forward_mock = AsyncMock()
    listener_unsub = MagicMock()

    entry = SimpleNamespace(
        entry_id="entry-1",
        async_on_unload=MagicMock(),
        add_update_listener=MagicMock(return_value=listener_unsub),
    )
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_forward_entry_setups=forward_mock))

    result = await async_setup_entry(hass, entry)

    assert result is True
    forward_mock.assert_awaited_once()
    entry.async_on_unload.assert_called_once_with(listener_unsub)


async def test_async_unload_entry_pops_data_and_releases_lock(tmp_path) -> None:
    """Successful unload removes the per-entry data and releases its file lock."""
    unload_mock = AsyncMock(return_value=True)
    entry = SimpleNamespace(entry_id="entry-1")
    hass = SimpleNamespace(
        data={DOMAIN: {"entry-1": ["entity"]}},
        config=SimpleNamespace(config_dir=str(tmp_path)),
        config_entries=SimpleNamespace(async_unload_platforms=unload_mock),
    )

    result = await async_unload_entry(hass, entry)

    assert result is True
    assert "entry-1" not in hass.data[DOMAIN]


async def test_async_unload_entry_partial_failure_keeps_data(tmp_path) -> None:
    """If platform unload fails the per-entry data is left in place."""
    unload_mock = AsyncMock(return_value=False)
    entry = SimpleNamespace(entry_id="entry-1")
    hass = SimpleNamespace(
        data={DOMAIN: {"entry-1": ["entity"]}},
        config=SimpleNamespace(config_dir=str(tmp_path)),
        config_entries=SimpleNamespace(async_unload_platforms=unload_mock),
    )

    result = await async_unload_entry(hass, entry)

    assert result is False
    assert "entry-1" in hass.data[DOMAIN]


async def test_async_reload_entry_delegates_to_async_reload() -> None:
    reload_mock = AsyncMock()
    entry = SimpleNamespace(entry_id="entry-1")
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_reload=reload_mock),
    )

    await async_reload_entry(hass, entry)

    reload_mock.assert_awaited_once_with("entry-1")
