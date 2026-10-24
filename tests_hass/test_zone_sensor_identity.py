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


async def _entry(hass: HomeAssistant, entities: list[str] | None = None) -> MockConfigEntry:
    path = hass.config.path("identity.geojson")
    await hass.async_add_executor_job(Path(path).write_text, json.dumps(_ZONES), "utf-8")
    entities = entities or [_SRC]
    for entity in entities:
        hass.states.async_set(entity, "not_home", {"latitude": 51.5, "longitude": -0.1})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "zone_urls": ["identity.geojson"],
            "entities": entities,
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


async def test_a_lone_suffixed_original_is_kept(hass: HomeAssistant) -> None:
    """When the preferred entity_id was taken, 1.15.x registered the only sensor
    as ``…_2_zone``. It must be re-keyed, not deleted as a duplicate."""
    entry = await _entry(hass)
    reg = er.async_get(hass)
    created = reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "sensor.polygonal_zones_phone_2_zone",
        suggested_object_id="polygonal_zones_phone_2",
        config_entry=entry,
    )
    reg.async_update_entity(created.entity_id, name="My zone")
    row_id = created.id

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert [s for s in _sensors(hass) if s[1].endswith("_zone")] == [
        (created.entity_id, f"{entry.entry_id}_{_SRC}_zone")
    ]
    kept = reg.async_get(created.entity_id)
    assert kept.id == row_id
    assert kept.name == "My zone"


async def test_a_suffixed_row_stays_with_the_tracker_it_belongs_to(hass: HomeAssistant) -> None:
    """``…_phone_2_zone`` is tracker ``phone_2``'s original, not a duplicate of
    ``phone``'s sensor, so it must not be re-keyed onto the shorter slug."""
    second = "device_tracker.phone_2"
    entry = await _entry(hass, entities=[_SRC, second])
    reg = er.async_get(hass)
    created = reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "sensor.polygonal_zones_phone_2_zone",
        suggested_object_id="polygonal_zones_phone_2",
        config_entry=entry,
    )
    row_id = created.id

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    zone_sensors = {uid: entity_id for entity_id, uid in _sensors(hass) if uid.endswith("_zone")}
    # The suffixed row moves with phone_2, keeping its registry identity, and
    # phone gets a sensor of its own instead of hijacking it.
    assert zone_sensors[f"{entry.entry_id}_{second}_zone"] == created.entity_id
    assert f"{entry.entry_id}_{_SRC}_zone" in zone_sensors
    assert reg.async_get(created.entity_id).id == row_id
