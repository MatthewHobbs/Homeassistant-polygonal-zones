"""Real-hass baseline for the location_name migration (Release A, PR A1).

Boots a real Home Assistant instance, loads polygonal_zones via an actual
config entry (exercising the real async_forward_entry_setups path the pure
pytest-stub suite in tests/ can't reach), and asserts on real entity state.
This is the harness Release A's later PRs build on: PR A2 fixes a real
platform-forwarding race that only shows up when a second platform is
forwarded, and PR A4 needs to assert on real in_zones/state derivation, both
of which need genuine HA state-machine behaviour, not a stub.

This test itself documents TODAY's baseline (state == the matched zone's
name via location_name) before anything in the migration changes it.
"""

import json
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.polygonal_zones.const import DOMAIN

_ZONE_GEOJSON = {
    "type": "FeatureCollection",
    "polygonal_zones": {"schema_version": 1},
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "Home", "priority": 0},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-0.135, 51.51],
                        [-0.125, 51.51],
                        [-0.125, 51.515],
                        [-0.135, 51.515],
                        [-0.135, 51.51],
                    ]
                ],
            },
        }
    ],
}


async def test_mirror_reflects_matched_zone_name_via_real_hass(hass: HomeAssistant) -> None:
    """Baseline: today, a source tracker inside the polygon shows the zone's name
    as its mirror's state — the exact behaviour Release A must not break while it's
    additive, and Release B will deliberately change."""
    zones_path = hass.config.path("polygonal_zones_test.geojson")
    await hass.async_add_executor_job(
        Path(zones_path).write_text, json.dumps(_ZONE_GEOJSON), "utf-8"
    )

    hass.states.async_set(
        "device_tracker.test_phone",
        "not_home",
        {"latitude": 51.5125, "longitude": -0.13, "gps_accuracy": 5},
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "zone_urls": ["polygonal_zones_test.geojson"],
            "entities": ["device_tracker.test_phone"],
            "download_zones": False,
            "expose_coordinates": True,
            "consent_confirmed_at": "2026-09-27T00:00:00+00:00",
        },
    )
    entry.add_to_hass(hass)

    # async_setup_component sets up any already-added config entries for this
    # domain as part of its own bootstrap — an explicit
    # hass.config_entries.async_setup(entry.entry_id) afterward double-sets up
    # the same entry and raises OperationNotAllowed.
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done(wait_background_tasks=True)

    mirror = hass.states.get("device_tracker.polygonal_zones_test_phone")
    assert mirror is not None
    assert mirror.state == "Home"
