"""Shared size limits for zone collections.

Single source of truth for the caps enforced on BOTH the mutation-service
write path (``services/helpers.py``) and the URI/file read path
(``utils/zones.py``). Kept in ``utils`` so both layers can import it without a
``utils`` -> ``services`` dependency.
"""

from __future__ import annotations

MAX_FEATURES_PER_COLLECTION = 500
# Total vertex count across every ring of every polygon in the collection.
# Caps event-loop stall time inside shapely.buffer()/.intersects() on each
# state_changed — a 1 MiB JSON file can otherwise encode ~50k vertices.
MAX_TOTAL_VERTICES_PER_COLLECTION = 10_000

# The only geometry types this integration resolves. Enforced identically on the
# mutation-service write path (``services/helpers.py``) and the URI/file read
# path (``utils/zones.py``). Kept here (not in ``services``) so both layers share
# one source of truth without a ``utils`` -> ``services`` dependency. Crucially,
# ``count_geometry_vertices`` only counts Polygon/MultiPolygon rings, so a
# non-Polygon geometry (e.g. a huge ``LineString``) counts as 0 vertices and
# would slip past the vertex cap — rejecting the type closes that bypass.
SUPPORTED_GEOMETRY_TYPES = {"Polygon", "MultiPolygon"}


def count_geometry_vertices(geometry: dict) -> int:
    """Sum the vertex count across every ring of a Polygon / MultiPolygon.

    Walks the ``coordinates`` tree instead of calling into shapely so the cap
    can be enforced before geometry construction, which is the expensive step
    we are trying to keep off the event loop.
    """
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list):
        return 0

    polygons = [coordinates] if geometry.get("type") == "Polygon" else coordinates

    total = 0
    for polygon in polygons:
        if not isinstance(polygon, list):
            continue
        for ring in polygon:
            if isinstance(ring, list):
                total += len(ring)
    return total
