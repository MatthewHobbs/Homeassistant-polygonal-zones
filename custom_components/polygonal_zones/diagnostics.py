"""Diagnostics for the polygonal_zones integration (HA quality-scale: gold)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from .utils.general import redact_uri

if TYPE_CHECKING:
    from . import PolygonalZonesConfigEntry

# Redacted from a dump a user may paste publicly: entity ids and URIs
# (`entities`, `zone_urls`), the add-on token (`zone_source_token`, a real
# secret), the home zone (`home_zone_id`, usually a place name) and the
# personalised entry `title`.
TO_REDACT_DATA = {"entities", "zone_urls", "zone_source_token", "home_zone_id"}
TO_REDACT_ENTRY_FIELDS = {"title"}


def _redact(value: Any) -> Any:
    if isinstance(value, list):
        return [f"<redacted-{i}>" for i, _ in enumerate(value)]
    return "<redacted>"


def _scrub_uri_from_error(error: str, uri: str, placeholder: str) -> str:
    """Remove a failing zone URI from its error message.

    The ``uri`` field of each failure record is already redacted, but load-error
    strings embed the URI verbatim (``Refusing redirect from '<uri>'`` etc.), so
    the host — and any credentials/tokens in it — would leak through the ``error``
    field into a shared diagnostics dump. Replace both the raw URI and its
    credential-stripped form with the same placeholder used for the ``uri`` field.
    """
    cleaned = error.replace(uri, placeholder)
    redacted = redact_uri(uri)
    if redacted != uri:
        cleaned = cleaned.replace(redacted, placeholder)
    return cleaned


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
                {
                    "uri": f"<redacted-{i}>",
                    "error": _scrub_uri_from_error(err, uri, f"<redacted-{i}>"),
                }
                for i, (uri, err) in enumerate(getattr(entity, "_last_load_failures", []))
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
