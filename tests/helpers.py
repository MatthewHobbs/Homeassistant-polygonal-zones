"""Shared builders for the pure-pytest unit tests.

The entry-scoped refactor made ``PolygonalZoneEntity`` read its zones from a
shared ``ZoneSource`` rather than owning them, so tests build a source and hand
it to the entity. These helpers keep that construction in one place.
"""

from __future__ import annotations

from custom_components.polygonal_zones.device_tracker import PolygonalZoneEntity
from custom_components.polygonal_zones.utils.zones import Zone
from custom_components.polygonal_zones.zone_source import ZoneSource


def make_source(
    *,
    entry_id: str = "entry-id",
    zone_urls: list[str] | None = None,
    prioritize: bool = False,
    editable_file: bool = False,
    allow_private_urls: bool = False,
    zones: list[Zone] | None = None,
    loaded_ok: bool = True,
) -> ZoneSource:
    """Build a ``ZoneSource`` (defaults to a loaded, healthy source)."""
    src = ZoneSource(
        entry_id,
        ["https://example.com/zones.json"] if zone_urls is None else zone_urls,
        prioritize,
        editable_file,
        allow_private_urls=allow_private_urls,
    )
    if zones is not None:
        src.zones = zones
    src.loaded_ok = loaded_ok
    return src


def make_entity(
    *,
    source: ZoneSource | None = None,
    tracked_entity_id: str = "device_tracker.phone",
    own_id: str = "device_tracker.polygonal_zones_phone",
    expose_coordinates: bool = True,
    **source_kwargs,
) -> PolygonalZoneEntity:
    """Build a ``PolygonalZoneEntity`` backed by a shared ``ZoneSource``."""
    if source is None:
        source = make_source(**source_kwargs)
    return PolygonalZoneEntity(source, tracked_entity_id, own_id, expose_coordinates)
