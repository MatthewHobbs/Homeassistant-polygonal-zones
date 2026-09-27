"""Tests for the companion zone-name sensor (Release A, PR A4)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_ENTITIES
from shapely.geometry import Polygon

from custom_components.polygonal_zones.sensor import async_setup_entry
from custom_components.polygonal_zones.utils.zones import Zone
from tests.helpers import make_sensor as _make_sensor
from tests.helpers import make_source

_HOME = Zone(name="Home", geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), priority=0)


def _make_hass() -> SimpleNamespace:
    async def aaej(func, *args):
        return func(*args)

    return SimpleNamespace(
        states=SimpleNamespace(get=MagicMock(return_value=None)),
        async_create_task=MagicMock(),
        async_add_executor_job=aaej,
    )


async def test_async_setup_entry_creates_one_sensor_per_entity() -> None:
    source = make_source()
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(source=source),
        data={CONF_ENTITIES: ["device_tracker.alice", "device_tracker.bob"]},
    )
    add_entities = MagicMock()

    with patch(
        "custom_components.polygonal_zones.sensor.generate_entity_id",
        side_effect=lambda fmt, name, hass=None: fmt.format(name),
    ):
        await async_setup_entry(_make_hass(), entry, add_entities)

    add_entities.assert_called_once()
    entities = add_entities.call_args.args[0]
    assert len(entities) == 2
    assert {e.entity_id for e in entities} == {
        "sensor.polygonal_zones_alice",
        "sensor.polygonal_zones_bob",
    }
    assert {e.unique_id for e in entities} == {
        "sensor.polygonal_zones_alice_zone",
        "sensor.polygonal_zones_bob_zone",
    }


async def test_update_location_sets_native_value() -> None:
    sensor = _make_sensor(zones=[_HOME])
    sensor.hass = _make_hass()

    await sensor.update_location(latitude=0.5, longitude=0.5, gps_accuracy=10)

    assert sensor.native_value == "Home"
    assert sensor.available is True
    assert sensor.extra_state_attributes["source_entity"] == "device_tracker.phone"
    assert sensor.extra_state_attributes["matched_zones"] == ["Home"]


async def test_update_location_outside_zones_marks_away() -> None:
    sensor = _make_sensor(zones=[_HOME])
    sensor.hass = _make_hass()

    await sensor.update_location(latitude=10, longitude=10, gps_accuracy=1)

    assert sensor.native_value == "away"


async def test_update_location_expose_coordinates_false_omits_matched_zones() -> None:
    sensor = _make_sensor(zones=[_HOME], expose_coordinates=False)
    sensor.hass = _make_hass()

    await sensor.update_location(latitude=0.5, longitude=0.5, gps_accuracy=10)

    assert "matched_zones" not in sensor.extra_state_attributes


async def test_update_state_marks_unavailable_when_not_loaded_ok() -> None:
    source = make_source(zones=[_HOME], loaded_ok=False)
    sensor = _make_sensor(source=source)
    sensor.hass = _make_hass()

    await sensor._update_state()

    assert sensor.available is False


async def test_update_state_marks_unavailable_when_source_tracker_unavailable() -> None:
    sensor = _make_sensor(zones=[_HOME])
    hass = _make_hass()
    hass.states.get = MagicMock(return_value=SimpleNamespace(state="unavailable", attributes={}))
    sensor.hass = hass

    await sensor._update_state()

    assert sensor.available is False


async def test_update_state_missing_gps_attrs_does_not_update() -> None:
    sensor = _make_sensor(zones=[_HOME])
    hass = _make_hass()
    hass.states.get = MagicMock(
        return_value=SimpleNamespace(state="not_home", attributes={"latitude": 0.5})
    )
    sensor.hass = hass

    await sensor._update_state()

    assert sensor.native_value is None


async def test_update_state_full_success_path_writes_state() -> None:
    """_update_state's success path: source state has all GPS attrs, resolves via
    update_location, marks available, and writes HA state."""
    sensor = _make_sensor(zones=[_HOME])
    hass = _make_hass()
    hass.states.get = MagicMock(
        return_value=SimpleNamespace(
            state="not_home",
            attributes={"latitude": 0.5, "longitude": 0.5, "gps_accuracy": 10},
        )
    )
    sensor.hass = hass
    sensor.async_write_ha_state = MagicMock()

    await sensor._update_state()

    assert sensor.native_value == "Home"
    assert sensor.available is True
    sensor.async_write_ha_state.assert_called_once()


async def test_async_added_to_hass_restores_native_value_and_attributes() -> None:
    sensor = _make_sensor()
    sensor.hass = _make_hass()
    sensor.async_get_last_sensor_data = AsyncMock(return_value=SimpleNamespace(native_value="Home"))
    sensor.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(attributes={"source_entity": "device_tracker.phone"})
    )

    with patch("custom_components.polygonal_zones.sensor.async_track_state_change_event"):
        await sensor.async_added_to_hass()

    assert sensor.native_value == "Home"
    assert sensor.extra_state_attributes == {"source_entity": "device_tracker.phone"}


async def test_async_added_to_hass_no_prior_state() -> None:
    sensor = _make_sensor()
    sensor.hass = _make_hass()
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)
    sensor.async_get_last_state = AsyncMock(return_value=None)

    with patch("custom_components.polygonal_zones.sensor.async_track_state_change_event"):
        await sensor.async_added_to_hass()

    assert sensor.native_value is None


async def test_added_to_hass_tracks_only_its_source_entity() -> None:
    sensor = _make_sensor()
    sensor.hass = _make_hass()
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)
    sensor.async_get_last_state = AsyncMock(return_value=None)

    tracker = MagicMock(return_value=lambda: None)
    with patch(
        "custom_components.polygonal_zones.sensor.async_track_state_change_event",
        new=tracker,
    ):
        await sensor.async_added_to_hass()

    tracker.assert_called_once()
    assert tracker.call_args.args[1] == ["device_tracker.phone"]


async def test_added_to_hass_registers_source_listener() -> None:
    source = make_source()
    sensor = _make_sensor(source=source)
    sensor.hass = _make_hass()
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)
    sensor.async_get_last_state = AsyncMock(return_value=None)

    with patch("custom_components.polygonal_zones.sensor.async_track_state_change_event"):
        await sensor.async_added_to_hass()

    assert len(source._listeners) == 1


async def test_will_remove_releases_unsubs() -> None:
    sensor = _make_sensor()
    sensor._unsub = MagicMock()
    sensor._unsub_source = MagicMock()

    await sensor.async_will_remove_from_hass()

    assert sensor._unsub is None
    assert sensor._unsub_source is None


async def test_will_remove_no_unsubs_is_a_noop() -> None:
    sensor = _make_sensor()
    await sensor.async_will_remove_from_hass()
    assert sensor._unsub is None
    assert sensor._unsub_source is None


async def test_handle_source_reloaded_schedules_update() -> None:
    sensor = _make_sensor()
    hass = _make_hass()
    created = []
    hass.async_create_task = created.append
    sensor.hass = hass

    sensor._handle_source_reloaded()

    assert len(created) == 1
    created[0].close()  # close the scheduled coroutine (never awaited in the test)


async def test_handle_state_change_builder_invokes_update_on_match() -> None:
    sensor = _make_sensor()
    update_mock = AsyncMock()
    sensor._update_state = update_mock

    func = sensor._handle_state_change_builder()

    old = SimpleNamespace(attributes={"latitude": 1, "longitude": 2, "gps_accuracy": 5})
    new = SimpleNamespace(
        attributes={"latitude": 99, "longitude": 2, "gps_accuracy": 5}, state="not_home"
    )
    event = SimpleNamespace(
        data={"entity_id": "device_tracker.phone", "old_state": old, "new_state": new}
    )
    await func(event)
    update_mock.assert_awaited_once()


async def test_handle_state_change_builder_ignores_other_entities() -> None:
    sensor = _make_sensor()
    update_mock = AsyncMock()
    sensor._update_state = update_mock

    func = sensor._handle_state_change_builder()
    event = SimpleNamespace(
        data={"entity_id": "device_tracker.someone_else", "old_state": None, "new_state": None}
    )
    await func(event)
    update_mock.assert_not_called()


def test_device_info_matches_device_tracker_mirror() -> None:
    sensor = _make_sensor(source=make_source(entry_id="entry-9"))
    info = sensor.device_info
    assert info["identifiers"] == {("polygonal_zones", "entry-9")}
    assert info["name"] == "Polygonal Zones"


def test_should_not_poll() -> None:
    assert _make_sensor().should_poll is False
