"""Real-hass checks that the four zone-editing services accept their documented fields.

`async_register_admin_service` falls back to a schema that refuses every key, so a
service registered without one rejects its own fields before the handler runs. A
stubbed hass never sees that: it only exists when Home Assistant validates the call.
"""

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest

from custom_components.polygonal_zones.const import DOMAIN
from custom_components.polygonal_zones.services.errors import InvalidZoneData


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir: str) -> str:
    """Write the test zone files under tmp_path, not the plugin's shared directory."""
    return hass_tmp_config_dir


_FEATURE = (
    '{"type":"Feature","properties":{"name":"A"},'
    '"geometry":{"type":"Polygon","coordinates":[[[0,0],[0,1],[1,1],[1,0],[0,0]]]}}'
)
_COLLECTION = '{"type":"FeatureCollection","features":[' + _FEATURE + "]}"


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("add_new_zone", {"device_id": "no-such-device", "zone": _FEATURE}),
        ("edit_zone", {"device_id": "no-such-device", "zone_name": "A", "zone": _FEATURE}),
        ("delete_zone", {"device_id": "no-such-device", "zone_name": "A"}),
        ("replace_all_zones", {"device_id": "no-such-device", "zone": _COLLECTION}),
    ],
)
async def test_service_accepts_its_documented_fields(
    hass: HomeAssistant, service: str, data: dict
) -> None:
    """The call must get past schema validation and reach the handler, which then
    refuses the unknown device. A schema error means the service cannot be used."""
    assert await async_setup_component(hass, DOMAIN, {})

    with pytest.raises(InvalidZoneData, match="Unknown device_id"):
        await hass.services.async_call(DOMAIN, service, data, blocking=True)


async def test_replace_all_zones_writes_the_file_and_updates_the_entity(
    hass: HomeAssistant,
) -> None:
    """A real call through Home Assistant edits the entry's file and re-resolves."""
    import json
    from pathlib import Path

    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    seed = hass.config.path("seed.geojson")
    empty = {"type": "FeatureCollection", "polygonal_zones": {"schema_version": 1}, "features": []}
    await hass.async_add_executor_job(Path(seed).write_text, json.dumps(empty), "utf-8")
    hass.states.async_set(
        "device_tracker.phone",
        "not_home",
        {"latitude": 0.5, "longitude": 0.5, "gps_accuracy": 5},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "zone_urls": ["seed.geojson"],
            "entities": ["device_tracker.phone"],
            "download_zones": True,
            "expose_coordinates": True,
            "consent_confirmed_at": "2026-09-27T00:00:00+00:00",
        },
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert hass.states.get("sensor.polygonal_zones_phone").state == "away"

    await hass.services.async_call(
        DOMAIN,
        "replace_all_zones",
        {"device_id": device.id, "zone": _COLLECTION.replace('"A"', '"Home"')},
        blocking=True,
    )
    await hass.async_block_till_done()

    snapshot = Path(hass.config.path(f"polygonal_zones/{entry.entry_id}.json"))
    saved = json.loads(await hass.async_add_executor_job(snapshot.read_text))
    assert saved["features"][0]["properties"]["name"] == "Home"
    assert hass.states.get("sensor.polygonal_zones_phone").state == "Home"
