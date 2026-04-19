"""Tests for utils.general — path containment + state-change filter."""

from types import SimpleNamespace

import pytest

from custom_components.polygonal_zones.utils.general import (
    event_should_trigger,
    safe_config_path,
)


def test_safe_config_path_inside_config_dir(tmp_path) -> None:
    """A simple relative path resolves to the expected location inside config_dir."""
    target = tmp_path / "polygonal_zones" / "entry.json"
    target.parent.mkdir()
    target.write_text("{}")
    resolved = safe_config_path(str(tmp_path), "polygonal_zones/entry.json")
    assert resolved == target


def test_safe_config_path_traversal_blocked(tmp_path) -> None:
    """A ``..`` traversal that escapes config_dir must raise ValueError."""
    with pytest.raises(ValueError):
        safe_config_path(str(tmp_path), "../../../etc/passwd")


def test_safe_config_path_absolute_path_treated_as_relative(tmp_path) -> None:
    """Leading slashes are stripped so absolute-looking input stays inside config_dir."""
    target = tmp_path / "absolute" / "thing.json"
    target.parent.mkdir()
    target.write_text("{}")
    resolved = safe_config_path(str(tmp_path), "/absolute/thing.json")
    assert resolved == target


def test_safe_config_path_symlink_escape_blocked(tmp_path) -> None:
    """A symlink inside config_dir pointing outside must be rejected by resolve()."""
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret")
    link = tmp_path / "evil"
    link.symlink_to(outside)
    with pytest.raises(ValueError):
        safe_config_path(str(tmp_path), "evil")


# event_should_trigger uses event.data.get(...) and state.attributes only —
# SimpleNamespace is enough; no HA fixtures needed.

REQUIRED = {"latitude": 1.0, "longitude": 2.0, "gps_accuracy": 5}


def _state(attributes: dict) -> SimpleNamespace:
    return SimpleNamespace(attributes=attributes)


def _event(entity_id: str, old_attrs: dict | None, new_attrs: dict | None) -> SimpleNamespace:
    return SimpleNamespace(
        data={
            "entity_id": entity_id,
            "old_state": _state(old_attrs) if old_attrs is not None else None,
            "new_state": _state(new_attrs) if new_attrs is not None else None,
        }
    )


def test_event_for_other_entity_ignored() -> None:
    event = _event("device_tracker.someone_else", REQUIRED, REQUIRED)
    assert event_should_trigger(event, "device_tracker.me") is False


def test_missing_gps_accuracy_does_not_trigger() -> None:
    """A new state missing one of the required GPS attrs must not fire the listener."""
    new_attrs = {"latitude": 1.0, "longitude": 2.0}  # no gps_accuracy
    event = _event("device_tracker.me", REQUIRED, new_attrs)
    assert event_should_trigger(event, "device_tracker.me") is False


def test_first_update_with_old_state_missing_attrs_triggers() -> None:
    """When the previous state lacks GPS attrs (first real update), allow the trigger."""
    event = _event("device_tracker.me", {}, REQUIRED)
    assert event_should_trigger(event, "device_tracker.me") is True


def test_unchanged_location_does_not_trigger() -> None:
    event = _event("device_tracker.me", REQUIRED, REQUIRED)
    assert event_should_trigger(event, "device_tracker.me") is False


def test_changed_latitude_triggers() -> None:
    new_attrs = {**REQUIRED, "latitude": 1.5}
    event = _event("device_tracker.me", REQUIRED, new_attrs)
    assert event_should_trigger(event, "device_tracker.me") is True
