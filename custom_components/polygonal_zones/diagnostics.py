"""Diagnostics for the polygonal_zones integration (HA quality-scale: gold)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    from . import PolygonalZonesConfigEntry

# Keys whose values may carry user-meaningful identifiers; replace with placeholder.
# - ``entities`` / ``zone_urls`` live inside entry.data and carry URIs + entity_ids.
# - ``title`` is the config-entry title, which a user may have personalised
#   (e.g. "Alice's tracking") — redact before shipping diagnostics externally.
TO_REDACT_DATA = {"entities", "zone_urls"}
TO_REDACT_ENTRY_FIELDS = {"title"}


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
    entry_data = {k: (_redact(v) if k in TO_REDACT_DATA else v) for k, v in entry.data.items()}

    runtime = getattr(entry, "runtime_data", None)
    entities = runtime.entities if runtime is not None else []
    entities_state: list[dict[str, Any]] = [
        {
            "available": getattr(entity, "_attr_available", True),
            "editable_file": getattr(entity, "_editable_file", False),
            "zone_count": len(getattr(entity, "_zones", [])),
            "url_count": len(getattr(entity, "_zones_urls", []) or []),
            "prioritize_zone_files": bool(getattr(entity, "_prioritize_zone_files", False)),
            "expose_coordinates": bool(getattr(entity, "_expose_coordinates", True)),
            "allow_private_urls": bool(getattr(entity, "_allow_private_urls", False)),
            "last_load_result": getattr(entity, "_last_load_result", "never"),
            "last_zones_loaded_at": (
                ts.isoformat()
                if (ts := getattr(entity, "_last_zones_loaded_at", None)) is not None
                else None
            ),
            # Redact the URI to avoid leaking host names in the diagnostics dump;
            # surface the count + failure message so the user can see "which
            # source broke and why" without a fresh log scrape.
            "last_load_failures": [
                {"uri": f"<redacted-{i}>", "error": err}
                for i, (_uri, err) in enumerate(getattr(entity, "_last_load_failures", []))
            ],
        }
        for entity in entities
    ]

    return {
        "entry": {
            "title": "<redacted>" if "title" in TO_REDACT_ENTRY_FIELDS else entry.title,
            "version": entry.version,
            "data": entry_data,
        },
        "entities": entities_state,
    }
