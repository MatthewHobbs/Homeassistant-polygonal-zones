"""Tests for the integration's package-level lifecycle hooks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
import pytest

from custom_components.polygonal_zones import (
    PolygonalZonesData,
    async_migrate_entry,
    async_reload_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.polygonal_zones.utils.zones import UnsupportedSchemaVersion


async def test_async_setup_registers_services() -> None:
    """async_setup registers all four services. No per-domain dict any more."""
    hass = SimpleNamespace()
    register_mock = AsyncMock()

    from custom_components import polygonal_zones as pkg

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
        data={},
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


def _download_entry(**data_overrides):
    data = {
        "zone_urls": ["https://example.com/zones.json"],
        "download_zones": True,
    }
    data.update(data_overrides)
    return SimpleNamespace(
        entry_id="entry-1",
        data=data,
        async_on_unload=MagicMock(),
        add_update_listener=MagicMock(),
    )


async def test_async_setup_entry_download_failure_raises_before_forward(tmp_path) -> None:
    """A failed initial snapshot download raises ConfigEntryNotReady from __init__,
    before the platform is forwarded — HA retries setup with backoff (#84). Raised
    from the forwarded platform instead, entity_platform swallows it: no retry."""
    forward_mock = AsyncMock()
    entry = _download_entry()
    hass = SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        config_entries=SimpleNamespace(async_forward_entry_setups=forward_mock),
        async_add_executor_job=AsyncMock(return_value=False),  # snapshot missing
    )

    with (
        patch(
            "custom_components.polygonal_zones.download_zones",
            new=AsyncMock(side_effect=OSError("host unreachable")),
        ),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)

    forward_mock.assert_not_awaited()


async def test_async_setup_entry_download_unsupported_schema_raises_before_forward(
    tmp_path,
) -> None:
    """An unsupported schema version is permanent: ConfigEntryError, not NotReady
    (retrying with NotReady would spin forever), and still before the forward."""
    forward_mock = AsyncMock()
    entry = _download_entry()
    hass = SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        config_entries=SimpleNamespace(async_forward_entry_setups=forward_mock),
        async_add_executor_job=AsyncMock(return_value=False),  # snapshot missing
    )

    with (
        patch(
            "custom_components.polygonal_zones.download_zones",
            new=AsyncMock(side_effect=UnsupportedSchemaVersion("schema 2 > max 1")),
        ),
        pytest.raises(ConfigEntryError),
    ):
        await async_setup_entry(hass, entry)

    forward_mock.assert_not_awaited()


async def test_async_setup_entry_download_skipped_when_snapshot_exists(tmp_path) -> None:
    """An existing snapshot short-circuits the bootstrap; forward proceeds normally."""
    forward_mock = AsyncMock()
    entry = _download_entry()
    hass = SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        config_entries=SimpleNamespace(async_forward_entry_setups=forward_mock),
        async_add_executor_job=AsyncMock(return_value=True),  # snapshot already present
    )

    with patch(
        "custom_components.polygonal_zones.download_zones", new=AsyncMock()
    ) as download_mock:
        result = await async_setup_entry(hass, entry)

    assert result is True
    download_mock.assert_not_awaited()
    forward_mock.assert_awaited_once()


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


async def test_async_unload_entry_shuts_down_source(tmp_path) -> None:
    """Unload cancels the shared source's pending start/retry callbacks."""
    from unittest.mock import MagicMock

    from custom_components.polygonal_zones import PolygonalZonesData

    source = SimpleNamespace(async_shutdown=MagicMock())
    unload_mock = AsyncMock(return_value=True)
    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=PolygonalZonesData(source=source),
    )
    hass = SimpleNamespace(
        config=SimpleNamespace(config_dir=str(tmp_path)),
        config_entries=SimpleNamespace(async_unload_platforms=unload_mock),
    )

    result = await async_unload_entry(hass, entry)

    assert result is True
    source.async_shutdown.assert_called_once()


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


async def test_async_migrate_entry_accepts_current_version() -> None:
    """VERSION=1 entries need no migration — stub returns True."""
    entry = SimpleNamespace(entry_id="entry-1", version=1)
    assert await async_migrate_entry(SimpleNamespace(), entry) is True


async def test_async_migrate_entry_rejects_future_version() -> None:
    """A future schema version the stub doesn't know how to downgrade returns False."""
    entry = SimpleNamespace(entry_id="entry-1", version=99)
    assert await async_migrate_entry(SimpleNamespace(), entry) is False
