"""Helper functions for the services for the polygonal zones integration."""

from collections.abc import Callable, Iterator
import contextlib
import json
import logging
from pathlib import Path
import time
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

from ..const import DOMAIN
from ..device_tracker import PolygonalZoneEntity
from ..utils.general import read_local_file, safe_config_path
from ..utils.limits import (
    MAX_FEATURES_PER_COLLECTION,
    MAX_TOTAL_VERTICES_PER_COLLECTION,
    SUPPORTED_GEOMETRY_TYPES,
)
from ..utils.limits import (
    count_geometry_vertices as _count_geometry_vertices,
)
from ..utils.local_zones import (
    LOCK_ACQUIRE_TIMEOUT,
    dump_feature_collection,
    file_lock,
    write_zones,
)
from ..utils.zones import UnsupportedSchemaVersion, ZoneFileCorrupt, validate_zone_document
from .errors import (
    InvalidZoneData,
    RateLimited,
    ZoneAlreadyExists,
    ZoneFileNotEditable,
)

_LOGGER = logging.getLogger(__name__)

MAX_ZONE_JSON_BYTES = 1_048_576
MAX_ZONE_NAME_LEN = 200
# Declared top-level feature keys; anything else is preserved but logged at
# WARNING so drift shows. Producer-specific fields belong under
# ``properties.polygonal_zones_ext``. ``id`` is known, not drift: the add-on
# stamps it on every file to bind automations across renames.
# See docs/ZONES_FORMAT.md.
KNOWN_FEATURE_PROPERTY_KEYS = frozenset({"name", "priority", "id", "polygonal_zones_ext"})

# Minimum seconds between mutation-service calls for a single config entry.
# A low-privilege authenticated user can't wedge the event loop by spamming
# service calls; 2s is generous for human + automation use and catches runaway
# loops immediately.
MUTATION_MIN_INTERVAL_S = 2.0
_LAST_MUTATION_TIMESTAMP: dict[str, float] = {}


def reset_mutation_rate_limit() -> None:
    """Clear the mutation rate-limit timestamps. Intended for tests."""
    _LAST_MUTATION_TIMESTAMP.clear()


def enforce_mutation_rate_limit(
    entry_id: str, min_interval: float = MUTATION_MIN_INTERVAL_S
) -> None:
    """Raise ``RateLimited`` if this entry mutated within ``min_interval`` seconds.

    Keyed by ``entry_id`` rather than ``device_id`` because every entity under
    one entry shares the same on-disk file — allowing two devices in the same
    entry to mutate simultaneously would bypass the point of the gate.
    """
    now = time.monotonic()
    last = _LAST_MUTATION_TIMESTAMP.get(entry_id, 0.0)
    elapsed = now - last
    if elapsed < min_interval:
        raise RateLimited(
            f"Rate limit exceeded: wait {min_interval - elapsed:.1f}s before the "
            "next polygonal_zones mutation on this entry."
        )
    _LAST_MUTATION_TIMESTAMP[entry_id] = now


def audit_mutation_call(call: ServiceCall, service_name: str, entry_id: str) -> None:
    """Log every mutation invocation at INFO with the calling user_id.

    ``ServiceCall.context.user_id`` is the HA user that invoked the service.
    Automation / script / system invocations carry a ``None`` user_id; we
    surface that as ``<automation/system>`` so the audit trail still shows
    the origin.
    """
    context = getattr(call, "context", None)
    user_id = getattr(context, "user_id", None) if context is not None else None
    _LOGGER.info(
        "polygonal_zones.%s invoked by user=%s on entry=%s",
        service_name,
        user_id or "<automation/system>",
        entry_id,
    )


def _validate_feature(feature: object) -> None:
    """Validate a single GeoJSON Feature has the fields this integration needs."""
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise InvalidZoneData("Zone must be a GeoJSON Feature")
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise InvalidZoneData("Feature must have a properties object")
    name = properties.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InvalidZoneData("Feature must have a non-empty 'name' property")
    if len(name) > MAX_ZONE_NAME_LEN:
        raise InvalidZoneData(f"Zone name exceeds {MAX_ZONE_NAME_LEN} characters")
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise InvalidZoneData("Feature must have a geometry object")
    geom_type = geometry.get("type")
    if geom_type not in SUPPORTED_GEOMETRY_TYPES:
        raise InvalidZoneData(
            f"Unsupported geometry type {geom_type!r}; "
            f"expected one of {sorted(SUPPORTED_GEOMETRY_TYPES)}"
        )
    vertex_count = _count_geometry_vertices(geometry)
    if vertex_count > MAX_TOTAL_VERTICES_PER_COLLECTION:
        raise InvalidZoneData(
            f"Feature has {vertex_count} vertices; single-feature limit is "
            f"{MAX_TOTAL_VERTICES_PER_COLLECTION}"
        )
    unknown_keys = set(properties) - KNOWN_FEATURE_PROPERTY_KEYS
    if unknown_keys:
        _LOGGER.warning(
            "Zone feature %r carries unknown property keys %s; "
            "preserved but producers should move new fields under "
            "properties.polygonal_zones_ext (see docs/ZONES_FORMAT.md)",
            name,
            sorted(unknown_keys),
        )


def parse_zone_feature(raw: str | None) -> dict:
    """Parse a JSON string into a validated GeoJSON Feature dict."""
    if not raw:
        raise InvalidZoneData("Missing zone payload")
    if len(raw) > MAX_ZONE_JSON_BYTES:
        raise InvalidZoneData(f"Zone payload exceeds {MAX_ZONE_JSON_BYTES} bytes")
    try:
        feature = json.loads(raw)
    except (ValueError, RecursionError) as err:
        raise InvalidZoneData(f"Zone payload is not valid JSON: {err}") from err
    _validate_feature(feature)
    return feature


def parse_zone_collection(raw: str | None) -> dict:
    """Parse a JSON string into a validated GeoJSON FeatureCollection dict."""
    if not raw:
        raise InvalidZoneData("Missing zone payload")
    if len(raw) > MAX_ZONE_JSON_BYTES:
        raise InvalidZoneData(f"Zone payload exceeds {MAX_ZONE_JSON_BYTES} bytes")
    try:
        collection = json.loads(raw)
    except (ValueError, RecursionError) as err:
        raise InvalidZoneData(f"Zone payload is not valid JSON: {err}") from err
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise InvalidZoneData("Payload must be a GeoJSON FeatureCollection")
    features = collection.get("features")
    if not isinstance(features, list):
        raise InvalidZoneData("FeatureCollection must have a 'features' array")
    if len(features) > MAX_FEATURES_PER_COLLECTION:
        raise InvalidZoneData(
            f"FeatureCollection has {len(features)} features; limit is "
            f"{MAX_FEATURES_PER_COLLECTION}"
        )
    total_vertices = 0
    for feature in features:
        _validate_feature(feature)
        total_vertices += _count_geometry_vertices(feature["geometry"])
    if total_vertices > MAX_TOTAL_VERTICES_PER_COLLECTION:
        raise InvalidZoneData(
            f"FeatureCollection has {total_vertices} total vertices; limit is "
            f"{MAX_TOTAL_VERTICES_PER_COLLECTION}"
        )
    return collection


def require_device_id(call_data: dict) -> str:
    """Extract a device_id from a service call, raising on missing/empty input."""
    device_id = call_data.get("device_id")
    if not device_id:
        raise InvalidZoneData("Service call is missing 'device_id'")
    if isinstance(device_id, list):
        return device_id[0]
    return device_id


def get_zone_idx(name: str, existing_zones: dict[str, Any]) -> int | None:
    """Get the index of the zone in the features list of a GeoJSON dict.

    Args:
        name: The name to get the index of
        existing_zones: A GeoJSON dict of the existing zones to search in.

    Returns:
         int | None: the index if the name is found. otherwise None

    """
    for idx, zone in enumerate(zone_features(existing_zones)):
        properties = zone.get("properties") if isinstance(zone, dict) else None
        if isinstance(properties, dict) and properties.get("name") == name:
            return idx
    return None


def zone_features(collection: Any) -> list[Any]:
    """The feature list of a zone document, or ``InvalidZoneData`` if it has none.

    Indexing it unguarded turned a readable but malformed file (``{}``, an array,
    a null ``properties``) into a raw ``KeyError``/``TypeError`` escaping the
    service call instead of a translated validation error.
    """
    features = collection.get("features") if isinstance(collection, dict) else None
    if not isinstance(features, list):
        raise InvalidZoneData("Zone file has no 'features' array")
    return features


def ensure_unique_zone(features: list[Any]) -> None:
    """Refuse a collection where two zones share a name, or two share an id.

    A name is how the add/edit/delete actions select a zone and an id is how
    automations bind to one, so neither may be ambiguous: with duplicates,
    ``get_zone_idx`` returns the first match and the wrong polygon is edited or
    deleted. The add-on enforces both on save; this is the integration's half of
    the same contract.
    """
    for key in ("name", "id"):
        seen: set[str] = set()
        for zone in features:
            properties = zone.get("properties") if isinstance(zone, dict) else None
            value = properties.get(key) if isinstance(properties, dict) else None
            if not isinstance(value, str) or not value:
                continue
            if value in seen:
                raise ZoneAlreadyExists(f'The zone {key} "{value}" is already used by another zone')
            seen.add(value)


def ensure_loadable(content: str) -> None:
    """Refuse to persist a document the loader would reject.

    The per-feature checks validate what a call hands in; this validates the
    whole document that would be written — cumulative caps included — with the
    parser the loader uses. Without it a mutation can report success, leave the
    in-memory zones untouched (the post-write reload is allowed to fail), and
    only fail on the next start, when every zone stops loading.

    Sync: it runs inside the mutation's executor job, where the polygon parsing
    belongs anyway.
    """
    try:
        validate_zone_document(content)
    except (ZoneFileCorrupt, UnsupportedSchemaVersion) as err:
        raise InvalidZoneData(str(err)) from err


@contextlib.contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold the file's write lock, or give up after ``LOCK_ACQUIRE_TIMEOUT``.

    Both mutation paths need this, and the timeout has to cover the lock wait
    only: the write that follows cannot be cancelled, so a caller that gave up
    during it would leave another mutation free to read the pre-write file.
    """
    lock = file_lock(path)
    if not lock.acquire(timeout=LOCK_ACQUIRE_TIMEOUT):
        raise TimeoutError("Timed out waiting for zone file lock")
    try:
        yield
    finally:
        lock.release()


async def sync_entities_after_write(entities: list[PolygonalZoneEntity]) -> None:
    """Refresh the shared zone source after a successful disk write.

    Every entity under a single config entry reads from one entry-scoped
    ``ZoneSource``, so a mutation service reloads it once — the source then
    notifies every mirror to re-resolve. A reload failure here is swallowed
    (logged): the write already committed, and the entities keep their previous
    zones rather than the mutation appearing to fail.
    """
    if not entities:
        return
    source = entities[0]._source
    try:
        await source.async_reload(entities[0].hass)
    except Exception:
        _LOGGER.warning(
            "Post-write zone reload failed for entry=%s; entities keep previous zones",
            source.entry_id,
            exc_info=True,
        )


def get_entities_from_device_id(device_id: str, hass: HomeAssistant) -> list[PolygonalZoneEntity]:
    """Get the entities from the provided device_id via the entry's runtime_data."""
    device_entry = dr.async_get(hass)
    device = device_entry.async_get(device_id)
    if device is None:
        raise InvalidZoneData(f"Unknown device_id: {device_id}")
    entry_id = device.primary_config_entry
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
        raise InvalidZoneData(f"Device '{device_id}' is not registered to polygonal_zones")
    return entry.runtime_data.entities


def resolve_mutation_target(
    hass: HomeAssistant, call: ServiceCall, service_name: str
) -> tuple[list[PolygonalZoneEntity], PolygonalZoneEntity]:
    """Run the checks every zone-file mutation shares, in their fixed order.

    Device lookup, audit log, rate limit, then "is the file editable". Returns the
    entry's entities and the first one, whose source holds the zone file path.
    """
    entities = get_entities_from_device_id(require_device_id(call.data), hass)
    entity = entities[0]
    audit_mutation_call(call, service_name, entity._config_entry_id)
    enforce_mutation_rate_limit(entity._config_entry_id)
    if not entity.editable_file:
        raise ZoneFileNotEditable("Zone files of entity are not editable")
    return entities, entity


@contextlib.contextmanager
def zone_file_errors(value_error: str = "Zone file content or path is invalid") -> Iterator[None]:
    """Turn the failures of reading or writing a zone file into ``InvalidZoneData``."""
    try:
        yield
    except TimeoutError as err:
        raise InvalidZoneData(
            "Timed out waiting for zone file lock; another operation may be in progress"
        ) from err
    except OSError as err:
        raise InvalidZoneData("Failed to access zone file") from err
    except ValueError as err:
        raise InvalidZoneData(value_error) from err


async def modify_zone_file(
    hass: HomeAssistant,
    entities: list[PolygonalZoneEntity],
    entity: PolygonalZoneEntity,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """Read the zone file under its lock, apply ``mutate`` in place, save, then reload.

    The whole read-modify-write is one executor job: a thread lock outlives a
    cancelled caller, so no later mutation can read the file mid-write.
    """
    filename = entity.zone_urls[0]
    config_dir = hass.config.config_dir

    def _apply() -> None:
        path = safe_config_path(config_dir, filename)
        with locked(path):
            existing_zones = json.loads(read_local_file(config_dir, filename))
            mutate(existing_zones)
            new_content = dump_feature_collection(
                zone_features(existing_zones), existing=existing_zones
            )
            ensure_loadable(new_content)
            write_zones(new_content, path)

    with zone_file_errors():
        await hass.async_add_executor_job(_apply)
    # Outside the lock: the reload may fetch remote URLs, and a slow fetch must
    # not hold the file or turn a mutation that already committed into an error.
    await sync_entities_after_write(entities)
