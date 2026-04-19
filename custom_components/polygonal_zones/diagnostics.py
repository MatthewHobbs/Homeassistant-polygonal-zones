"""Diagnostics for the polygonal_zones integration (HA quality-scale: gold)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    from . import PolygonalZonesConfigEntry

# Keys whose values may carry user-meaningful identifiers; replace with placeholder.
TO_REDACT = {"entities", "zone_urls"}


def _redact(value: Any) -> Any:
    if isinstance(value, list):
        return [f"<redacted-{i}>" for i, _ in enumerate(value)]
    return "<redacted>"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PolygonalZonesConfigEntry
) -> dict[str, Any]:
    """Return sanitized diagnostics for a single config entry.

    Excludes lat/lon/accuracy and replaces identifying lists with placeholders so
    a user can paste this into a bug report without leaking household location
    or device names.
    """
    entry_data = {k: (_redact(v) if k in TO_REDACT else v) for k, v in entry.data.items()}

    entities_state: list[dict[str, Any]] = []
    runtime = getattr(entry, "runtime_data", None)
    entities = runtime.entities if runtime is not None else []
    for entity in entities:
        entities_state.append(
            {
                "available": getattr(entity, "_attr_available", True),
                "editable_file": getattr(entity, "_editable_file", False),
                "zone_count": len(getattr(entity, "_zones", [])),
                "url_count": len(getattr(entity, "_zones_urls", []) or []),
                "prioritize_zone_files": bool(getattr(entity, "_prioritize_zone_files", False)),
            }
        )

    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "data": entry_data,
        },
        "entities": entities_state,
    }
