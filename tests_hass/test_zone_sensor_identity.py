"""Real-hass checks that the zone sensor's identity survives reloads (issue #131).

1.15.0/1.15.1 derived its unique_id from ``generate_entity_id``, which suffixes
``_2`` when the id is taken, so every reload registered another sensor. Needs the
real registry and state machine; a stubbed hass cannot reproduce it.
"""

import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.polygonal_zones.const import DOMAIN

_SRC = "device_tracker.phone"
_ZONES = {"type": "FeatureCollection", "polygonal_zones": {"schema_version": 1}, "features": []}


async def _entry(hass: HomeAssistant) -> MockConfigEntry:
    path = hass.config.path("identity.geojson")
    await hass.async_add_executor_job(Path(path).write_text, json.dumps(_ZONES), "utf-8")
    hass.states.async_set(_SRC, "not_home", {"latitude": 51.5, "longitude": -0.1})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "zone_urls": ["identity.geojson"],
            "entities": [_SRC],
            "download_zones": False,
            "expose_coordinates": True,
            "consent_confirmed_at": "2026-09-27T00:00:00+00:00",
        },
    )
    entry.add_to_hass(hass)
    return entry


def _sensors(hass: HomeAssistant) -> list[tuple[str, str | None]]:
    reg = er.async_get(hass)
    return sorted((e.entity_id, e.unique_id) for e in reg.entities.values() if e.domain == "sensor")


async def test_reload_keeps_zone_sensor_identity(hass: HomeAssistant) -> None:
    entry = await _entry(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    first = _sensors(hass)
    assert (
        "sensor.polygonal_zones_phone",
        f"{entry.entry_id}_{_SRC}_zone",
    ) in first

    for _ in range(2):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    assert _sensors(hass) == first


async def test_entities_have_per_tracker_names(hass: HomeAssistant) -> None:
    await _entry(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    # HA prefixes the device name, so each friendly name still has to differ.
    assert hass.states.get("sensor.polygonal_zones_phone").name == "Polygonal Zones phone zone"
    assert hass.states.get("device_tracker.polygonal_zones_phone").name == "Polygonal Zones phone"


async def test_migration_survives_both_ids_registered(hass: HomeAssistant) -> None:
    """A downgrade to 1.15.x and back must not fail the entry's setup."""
    entry = await _entry(hass)
    reg = er.async_get(hass)
    new_uid = f"{entry.entry_id}_{_SRC}_zone"
    for uid in (new_uid, "sensor.polygonal_zones_phone_zone"):
        reg.async_get_or_create("sensor", DOMAIN, uid, config_entry=entry)

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert [s[1] for s in _sensors(hass) if s[1].endswith("_zone")] == [new_uid]


async def test_1_15_1_registry_is_migrated(hass: HomeAssistant) -> None:
    """The first legacy sensor keeps its entity_id; the `_N` duplicates go."""
    entry = await _entry(hass)
    reg = er.async_get(hass)
    original_ids = {}
    for suffix in ("", "_2", "_3"):
        created = reg.async_get_or_create(
            "sensor",
            DOMAIN,
            f"sensor.polygonal_zones_phone{suffix}_zone",
            suggested_object_id=f"polygonal_zones_phone{suffix}",
            config_entry=entry,
        )
        original_ids[suffix] = created.id
    reg.async_update_entity("sensor.polygonal_zones_phone", name="My zone")

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    zone_sensors = [s for s in _sensors(hass) if s[1].endswith("_zone")]
    assert zone_sensors == [("sensor.polygonal_zones_phone", f"{entry.entry_id}_{_SRC}_zone")]
    # Re-keyed, not deleted and recreated: same registry row, customisation kept.
    kept = reg.async_get("sensor.polygonal_zones_phone")
    assert kept.id == original_ids[""]
    assert kept.name == "My zone"
