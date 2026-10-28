"""The polygonal_zones integration."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITIES, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ADDON_URL,
    CONF_ALLOW_PRIVATE_URLS,
    CONF_DISCOVERED_BY_ADDON,
    CONF_DOWNLOAD_ZONES,
    CONF_HOME_ZONE_ID,
    CONF_PRIORITIZE_ZONE_FILES,
    CONF_ZONE_SOURCE_TOKEN,
    CONF_ZONES_URL,
    DOMAIN,
)
from .services import register_services
from .services.reload_all_zones import action_builder as reload_all_zones
from .utils.general import download_zone_relative_path, is_local_add_on_host, safe_config_path
from .utils.local_zones import download_zones
from .utils.zones import UnsupportedSchemaVersion
from .zone_source import ZoneSource, async_check_duplicate_source

if TYPE_CHECKING:
    from .device_tracker import PolygonalZoneEntity

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS: list[Platform] = [Platform.DEVICE_TRACKER, Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


@dataclass
class PolygonalZonesData:
    """Runtime data for a polygonal_zones config entry.

    ``source`` is the single entry-scoped :class:`ZoneSource` that owns the
    loaded zones + load lifecycle; every mirror entity reads from it. Built by
    ``async_setup_entry`` (see ``_build_zone_source``) before any platform is
    forwarded.
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
    # Not admin and no target: it only reloads what is already configured, and
    # the companion add-on has no entity ids to target after it saves its file.
    hass.services.async_register(DOMAIN, "reload_all_zones", reload_all_zones(hass))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PolygonalZonesConfigEntry) -> bool:
    """Set up polygonal_zones from a config entry.

    Builds the shared :class:`ZoneSource` here — before any platform is
    forwarded — so every forwarded platform can read
    ``entry.runtime_data.source`` from the moment its own ``async_setup_entry``
    starts. ``async_forward_entry_setups`` starts every platform concurrently;
    building the source inside one platform's own setup (as device_tracker
    used to) would race a second platform that needs it too.
    """
    entry.runtime_data = PolygonalZonesData()
    _migrate_zone_sensor_unique_ids(hass, entry)
    if entry.data.get(CONF_DOWNLOAD_ZONES):
        await _async_bootstrap_zone_snapshot(hass, entry)
    entry.runtime_data.source = _build_zone_source(entry)
    async_check_duplicate_source(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


# 1.15.0/1.15.1 built the zone sensor's unique_id from its entity_id.
_LEGACY_ZONE_SENSOR_UID = re.compile(r"^sensor\.polygonal_zones_.+_zone$")


def _legacy_sensor_for(
    entries: list[er.RegistryEntry], slug: str, *, taken: set[str]
) -> er.RegistryEntry | None:
    """The oldest unclaimed legacy zone-sensor row for one tracked entity.

    ``generate_entity_id`` suffixed the entity_id, so the original is ``…_zone``
    or, when that entity_id was already taken, ``…_2_zone``. Picking the lowest
    suffix keeps the row the user has been customising instead of deleting it.
    ``taken`` keeps one row from being re-keyed for two tracked entities.
    """
    pattern = re.compile(rf"^sensor\.polygonal_zones_{re.escape(slug)}(?:_(\d+))?_zone$")
    candidates = [
        (int(match.group(1) or 1), row)
        for row in entries
        if row.entity_id not in taken and (match := pattern.match(row.unique_id or ""))
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate[0])[1]


def _migrate_zone_sensor_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Move 1.15.0/1.15.1 zone sensors onto stable ids and drop their duplicates.

    Those versions derived the unique_id from ``generate_entity_id``, which adds
    ``_2``, ``_3`` … whenever the id is already taken, so each reload registered
    another sensor. The first one registered (``…_<slug>_zone``) keeps its
    entity_id and history under the new id; every other legacy-format entry of
    this entry is a duplicate or an orphan and is removed. Idempotent.
    """
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor" and e.unique_id and _LEGACY_ZONE_SENSOR_UID.match(e.unique_id)
    ]
    if not entries:
        return
    tracked_entities = list(entry.data.get(CONF_ENTITIES, []))
    assigned: dict[str, er.RegistryEntry] = {}
    taken: set[str] = set()
    # Exact ids first: a suffixed row is another tracker's original whenever a
    # tracked entity's own slug ends in that suffix (e.g. phone vs phone_2).
    by_uid = {row.unique_id: row for row in entries}
    for tracked in tracked_entities:
        exact = by_uid.get(f"sensor.polygonal_zones_{tracked.split('.')[-1]}_zone")
        if exact is not None:
            assigned[tracked] = exact
            taken.add(exact.entity_id)
    for tracked in tracked_entities:
        if tracked in assigned:
            continue
        if (row := _legacy_sensor_for(entries, tracked.split(".")[-1], taken=taken)) is not None:
            assigned[tracked] = row
            taken.add(row.entity_id)

    kept: set[str] = set()
    for tracked in tracked_entities:
        legacy = assigned.get(tracked)
        new_uid = f"{entry.entry_id}_{tracked}_zone"
        # A downgrade to 1.15.x and back leaves both ids registered; re-keying onto
        # an id already in use raises and would fail the whole entry's setup.
        if legacy is not None and registry.async_get_entity_id("sensor", DOMAIN, new_uid) is None:
            registry.async_update_entity(legacy.entity_id, new_unique_id=new_uid)
            kept.add(legacy.entity_id)
    for legacy in entries:
        if legacy.entity_id not in kept:
            registry.async_remove(legacy.entity_id)
    _LOGGER.info(
        "Migrated %d zone sensor(s), removed %d duplicate(s)", len(kept), len(entries) - len(kept)
    )


def _is_announced_addon_url(uri: str) -> bool:
    """Whether ``uri`` has the shape of an add-on URL announced by Supervisor."""
    parsed = urlparse(uri)
    if parsed.scheme != "http" or not parsed.hostname:
        return False
    return is_local_add_on_host(uri) or "." not in parsed.hostname


def _trusted_addon_url(entry: PolygonalZonesConfigEntry, zone_uris: list[str]) -> str | None:
    """The announced add-on URL for this entry, or None when hand-configured."""
    if addon_url := entry.data.get(CONF_ADDON_URL):
        return str(addon_url)
    # 1.16.0/1.16.1 stored only the boolean flag; single-URL entries keep working
    # before the add-on's next start writes CONF_ADDON_URL.
    if (
        entry.data.get(CONF_DISCOVERED_BY_ADDON)
        and len(zone_uris) == 1
        and _is_announced_addon_url(zone_uris[0])
    ):
        return zone_uris[0]
    return None


def _fetch_settings(entry: PolygonalZonesConfigEntry) -> tuple[list[str], dict[str, Any]]:
    """The configured zone URIs and how to fetch them, as stored on the entry."""
    zone_uris = [uri for uri in entry.data.get(CONF_ZONES_URL) or [] if uri]
    return zone_uris, {
        "prioritize": bool(entry.data.get(CONF_PRIORITIZE_ZONE_FILES)),
        "allow_private_urls": bool(entry.data.get(CONF_ALLOW_PRIVATE_URLS, False)),
        "token": entry.data.get(CONF_ZONE_SOURCE_TOKEN) or None,
        "addon_url": _trusted_addon_url(entry, zone_uris),
    }


def _build_zone_source(entry: PolygonalZonesConfigEntry) -> ZoneSource:
    """Build the entry-scoped ``ZoneSource`` shared by every platform's entities.

    When ``download_zones`` is enabled, the configured URLs are a one-time seed
    for ``_async_bootstrap_zone_snapshot`` (already run by the time this is
    called); the source itself reads only the managed local snapshot file.
    """
    zone_uris, fetch = _fetch_settings(entry)
    home_zone_id: str | None = entry.data.get(CONF_HOME_ZONE_ID) or None

    editable_file = False
    if entry.data.get(CONF_DOWNLOAD_ZONES):
        relative = download_zone_relative_path(entry.entry_id)
        zone_uris = [f"/{relative}"]
        editable_file = True

    return ZoneSource(
        entry.entry_id,
        zone_uris,
        fetch["prioritize"],
        editable_file,
        allow_private_urls=fetch["allow_private_urls"],
        token=fetch["token"],
        home_zone_id=home_zone_id,
        addon_url=fetch["addon_url"],
    )


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
    zone_uris, fetch = _fetch_settings(entry)

    relative = download_zone_relative_path(entry.entry_id)
    download_path = safe_config_path(hass.config.config_dir, relative)

    exists = await hass.async_add_executor_job(download_path.exists)
    if exists:
        return

    try:
        await download_zones(
            zone_uris,
            download_path,
            fetch["prioritize"],
            hass,
            allow_private_urls=fetch["allow_private_urls"],
            token=fetch["token"],
            addon_url=fetch["addon_url"],
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
        # Any other failure may be transient, and an all-URIs-down outage is
        # indistinguishable from a corrupt file here (both raise ZoneFileCorrupt).
        # Retry with HA's backoff instead of hard-failing into no entities.
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
        # The removed entry was the duplicate, so the survivor's warning is now
        # wrong; the other entries are not reloaded, so clear it here.
        for other in hass.config_entries.async_entries(DOMAIN):
            if other.entry_id != entry.entry_id:
                async_check_duplicate_source(hass, other)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: PolygonalZonesConfigEntry) -> None:
    """Reload polygonal_zones config entry — full unload/setup cycle.

    Triggered by the options flow via ``add_update_listener`` so the tracked-entity
    list is rebuilt and add/remove in options flow takes effect without HA restart.
    """
    await hass.config_entries.async_reload(entry.entry_id)
