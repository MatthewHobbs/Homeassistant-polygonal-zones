"""Real-hass checks for the per-tracker "last reported" diagnostic sensor (RFC 0001).

The case that matters is a phone re-reporting an unchanged position: HA fires
``state_reported`` for it, not ``state_changed``. A unit test with a stubbed hass
cannot tell the two apart, so this runs the real state machine.
"""

from datetime import timedelta
import json
from pathlib import Path

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.polygonal_zones.const import DOMAIN

_SOURCE = "device_tracker.silent_phone"
_SENSOR = "sensor.polygonal_zones_silent_phone_last_reported"
_ATTRS = {"latitude": 51.5125, "longitude": -0.13, "gps_accuracy": 5}
_ZONES = {
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


def _iso(state) -> str:
    # HA renders a timestamp sensor's state without microseconds.
    return state.last_reported.replace(microsecond=0).isoformat()


async def _setup(hass: HomeAssistant, *, enable_sensor: bool) -> MockConfigEntry:
    path = hass.config.path("polygonal_zones_last_reported.geojson")
    await hass.async_add_executor_job(Path(path).write_text, json.dumps(_ZONES), "utf-8")
    hass.states.async_set(_SOURCE, "not_home", _ATTRS)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "zone_urls": ["polygonal_zones_last_reported.geojson"],
            "entities": [_SOURCE],
            "download_zones": False,
            "expose_coordinates": True,
            "consent_confirmed_at": "2026-09-27T00:00:00+00:00",
        },
    )
    entry.add_to_hass(hass)
    if enable_sensor:
        # Registry entries are created disabled; pre-create it enabled, as a user
        # would have after switching the entity on.
        er.async_get(hass).async_get_or_create(
            "sensor",
            DOMAIN,
            _SENSOR,
            config_entry=entry,
            suggested_object_id="polygonal_zones_silent_phone_last_reported",
            disabled_by=None,
        )
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


async def test_sensor_is_disabled_diagnostic_by_default(hass: HomeAssistant) -> None:
    await _setup(hass, enable_sensor=False)

    registry_entry = er.async_get(hass).async_get(_SENSOR)
    assert registry_entry is not None
    assert registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert registry_entry.entity_category is EntityCategory.DIAGNOSTIC
    assert hass.states.get(_SENSOR) is None


async def test_unchanged_re_report_advances_the_timestamp(hass: HomeAssistant, freezer) -> None:
    """A tracker re-reporting identical state must not look stale."""
    await _setup(hass, enable_sensor=True)

    first = hass.states.get(_SENSOR)
    assert first is not None
    assert first.state == _iso(hass.states.get(_SOURCE))

    freezer.tick(timedelta(minutes=5))
    hass.states.async_set(_SOURCE, "not_home", _ATTRS)  # identical: state_reported only
    await hass.async_block_till_done()

    assert hass.states.get(_SOURCE).last_changed < hass.states.get(_SOURCE).last_reported
    second = hass.states.get(_SENSOR)
    assert second.state == _iso(hass.states.get(_SOURCE))
    assert second.state != first.state


async def test_changed_report_advances_the_timestamp(hass: HomeAssistant, freezer) -> None:
    await _setup(hass, enable_sensor=True)
    first = hass.states.get(_SENSOR).state

    freezer.tick(timedelta(minutes=5))
    hass.states.async_set(_SOURCE, "not_home", {**_ATTRS, "latitude": 51.5126})
    await hass.async_block_till_done()

    assert hass.states.get(_SENSOR).state != first


async def test_source_going_unavailable_keeps_the_last_timestamp(
    hass: HomeAssistant, freezer
) -> None:
    await _setup(hass, enable_sensor=True)
    before = hass.states.get(_SENSOR).state

    freezer.tick(timedelta(minutes=5))
    hass.states.async_set(_SOURCE, "unavailable")
    await hass.async_block_till_done()

    # HA stamped "unavailable" five minutes later; the sensor must not follow it.
    assert hass.states.get(_SENSOR).state == before


_README_TEMPLATE = (
    "{% set s = 'sensor.polygonal_zones_silent_phone_last_reported' %}"
    "{{ has_value(s) and now() - states(s) | as_datetime > timedelta(minutes=10) }}"
)


async def test_readme_template_flips_after_ten_minutes_of_silence(
    hass: HomeAssistant, freezer
) -> None:
    """The README's template trigger, rendered for real, against the real sensor."""
    from homeassistant.helpers.template import Template

    await _setup(hass, enable_sensor=True)

    def render() -> str:
        return Template(_README_TEMPLATE, hass).async_render()

    freezer.tick(timedelta(minutes=9))
    assert render() is False
    freezer.tick(timedelta(minutes=2))
    assert render() is True

    hass.states.async_set(_SOURCE, "not_home", _ATTRS)  # tracker speaks again
    await hass.async_block_till_done()
    assert render() is False
