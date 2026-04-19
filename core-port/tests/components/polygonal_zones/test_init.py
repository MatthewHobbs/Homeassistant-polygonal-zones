"""Tests for the integration's package-level lifecycle hooks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.polygonal_zones import (
    PolygonalZonesData,
    async_reload_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)


async def test_async_setup_registers_services() -> None:
    """async_setup registers all four services. No per-domain dict any more."""
    hass = SimpleNamespace()
    register_mock = AsyncMock()

    from homeassistant.components import polygonal_zones as pkg

    original = pkg.register_services
    pkg.register_services = register_mock
    try:
        result = await async_setup(hass, {})
    finally:
        pkg.register_services = original

    assert result is True
    register_mock.assert_awaited_once()
    args = register_mock.await_args[0]
    assert sorted(args[1]) == [
        "add_new_zone",
        "delete_zone",
        "edit_zone",
        "replace_all_zones",
    ]


async def test_async_setup_entry_initialises_runtime_data_and_forwards() -> None:
    """async_setup_entry populates entry.runtime_data and forwards to platforms."""
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
    assert isinstance(entry.runtime_data, PolygonalZonesData)
    assert entry.runtime_data.entities == []


async def test_async_unload_entry_releases_lock(tmp_path) -> None:
    """Successful unload releases the per-file lock; runtime_data is GC'd with the entry."""
    unload_mock = AsyncMock(return_value=True)
    entry = SimpleNamespace(entry_id="entry-1")
    hass = SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        config_entries=SimpleNamespace(async_unload_platforms=unload_mock),
    )

    result = await async_unload_entry(hass, entry)

    assert result is True


async def test_async_unload_entry_partial_failure_leaves_state(tmp_path) -> None:
    """If platform unload fails the runtime_data is left in place by HA."""
    unload_mock = AsyncMock(return_value=False)
    entry = SimpleNamespace(entry_id="entry-1")
    hass = SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        config_entries=SimpleNamespace(async_unload_platforms=unload_mock),
    )

    result = await async_unload_entry(hass, entry)

    assert result is False


async def test_async_reload_entry_delegates_to_async_reload() -> None:
    reload_mock = AsyncMock()
    entry = SimpleNamespace(entry_id="entry-1")
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_reload=reload_mock),
    )

    await async_reload_entry(hass, entry)

    reload_mock.assert_awaited_once_with("entry-1")
