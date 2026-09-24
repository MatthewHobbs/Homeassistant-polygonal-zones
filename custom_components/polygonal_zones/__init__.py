"""The polygonal_zones integration."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ALLOW_PRIVATE_URLS,
    CONF_DOWNLOAD_ZONES,
    CONF_PRIORITIZE_ZONE_FILES,
    CONF_ZONES_URL,
    DOMAIN,
)
from .services import register_services
from .utils.general import download_zone_relative_path, safe_config_path
from .utils.local_zones import download_zones, release_file_lock
from .utils.zones import UnsupportedSchemaVersion

if TYPE_CHECKING:
    from .device_tracker import PolygonalZoneEntity
    from .zone_source import ZoneSource

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS: list[Platform] = [Platform.DEVICE_TRACKER]
_LOGGER = logging.getLogger(__name__)


@dataclass
class PolygonalZonesData:
    """Runtime data for a polygonal_zones config entry.

    ``source`` is the single entry-scoped :class:`ZoneSource` that owns the
    loaded zones + load lifecycle; every mirror entity reads from it. It is
    populated by the device_tracker platform's ``async_setup_entry``.
    """

    entities: list[PolygonalZoneEntity] = field(default_factory=list)
    source: ZoneSource | None = None


type PolygonalZonesConfigEntry = ConfigEntry[PolygonalZonesData]


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Set up the polygonal_zones component (registers global services)."""
    await register_services(
        hass,
        ["add_new_zone", "delete_zone", "edit_zone", "replace_all_zones"],
        admin=True,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PolygonalZonesConfigEntry) -> bool:
    """Set up polygonal_zones from a config entry.

    The platform's ``async_setup_entry`` populates ``entry.runtime_data.entities``;
    we just initialise the container, bootstrap the zone snapshot (if enabled)
    and forward.
    """
    entry.runtime_data = PolygonalZonesData()
    if entry.data.get(CONF_DOWNLOAD_ZONES):
        await _async_bootstrap_zone_snapshot(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def _async_bootstrap_zone_snapshot(
    hass: HomeAssistant, entry: PolygonalZonesConfigEntry
) -> None:
    """Download the initial zone snapshot for a ``download_zones`` entry, if missing.

    Runs before the platform is forwarded so a failure raises here, where HA's
    own config-entry retry/backoff and error banner apply. Raised from a
    forwarded platform instead, entity_platform swallows it: it logs a message
    but never retries and never surfaces the real error (#84). Once this
    succeeds (or the snapshot already exists), the device_tracker platform's
    own ``exists`` check finds the file in place and does no further work.
    """
    zone_uris: list[str] = entry.data.get(CONF_ZONES_URL) or []
    zone_uris = [zone_uri for zone_uri in zone_uris if zone_uri]
    prioritize = bool(entry.data.get(CONF_PRIORITIZE_ZONE_FILES))
    allow_private_urls = bool(entry.data.get(CONF_ALLOW_PRIVATE_URLS, False))

    relative = download_zone_relative_path(entry.entry_id)
    download_path = safe_config_path(hass.config.config_dir, relative)

    exists = await hass.async_add_executor_job(download_path.exists)
    if exists:
        return

    try:
        await download_zones(
            zone_uris,
            download_path,
            prioritize,
            hass,
            allow_private_urls=allow_private_urls,
        )
    except UnsupportedSchemaVersion as err:
        # The source file's format is newer than this integration understands.
        # Retrying can't fix that — the user must upgrade the integration or
        # downgrade the file. Surface it as a permanent setup error (HA stops
        # retrying and shows it) rather than spinning forever.
        raise ConfigEntryError(
            f"Zone file for entry {entry.entry_id} uses an unsupported schema version: {err}"
        ) from err
    except Exception as err:
        # Any other failure (unreachable source, SSRF block, corrupt payload,
        # disk error) may be transient — and crucially, an all-URIs-down
        # outage is indistinguishable from a corrupt file at this boundary
        # (get_zones raises ZoneFileCorrupt for both). Don't hard-fail the
        # entry — that would leave no entities and no retry. Signal HA to
        # retry setup with its own backoff.
        raise ConfigEntryNotReady(
            f"Could not download zone files for entry {entry.entry_id}: {err}"
        ) from err


async def async_unload_entry(hass: HomeAssistant, entry: PolygonalZonesConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Cancel any pending start/retry callbacks on the shared zone source.
        data = getattr(entry, "runtime_data", None)
        if data is not None and data.source is not None:
            data.source.async_shutdown()
        # Drop the per-file lock so it doesn't accumulate across reloads.
        # If download_zones was never enabled, this is a harmless no-op.
        relative = download_zone_relative_path(entry.entry_id)
        try:
            download_path = safe_config_path(hass.config.config_dir, relative)
        except ValueError:
            download_path = Path(hass.config.config_dir) / relative
        release_file_lock(download_path)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: PolygonalZonesConfigEntry) -> None:
    """Reload polygonal_zones config entry — full unload/setup cycle.

    Triggered by the options flow via ``add_update_listener`` so the tracked-entity
    list is rebuilt and add/remove in options flow takes effect without HA restart.
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an older config entry to the current ``VERSION``.

    The config flow's ``VERSION = 1`` is the only schema we've ever shipped, so
    this function is a no-op stub today. It exists to document the contract and
    keep the migration path obvious when the first real schema change lands
    (e.g. splitting ``entry.data`` user-mutable fields into ``entry.options``,
    or dropping a removed key).

    Return True for versions we know how to handle (which is just ``1``); False
    for future versions we can't downgrade.
    """
    if entry.version == 1:
        return True
    _LOGGER.error(
        "Cannot migrate polygonal_zones entry=%s from schema version %d; "
        "this integration supports up to version 1",
        entry.entry_id,
        entry.version,
    )
    return False
