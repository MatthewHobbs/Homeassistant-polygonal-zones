"""Test configuration for polygonal_zones.

Pure-pytest tests only at the moment — the ``hass`` fixture from
``pytest-homeassistant-custom-component`` is not used yet, so its plugin is
disabled via ``-p no:homeassistant`` in ``pyproject.toml``.
"""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _stub_state_change_tracker():
    """Stub ``async_track_state_change_event`` for the pure-pytest tests.

    The helper does real Home Assistant wiring (``hass.data``, bus filters); the
    unit tests build ``SimpleNamespace`` hass stubs and never deliver real
    events (they invoke the entity's ``_update_state`` / captured callbacks
    directly), so a no-op unsub keeps ``async_added_to_hass`` working without a
    full hass. Real event routing is covered by the Playwright/e2e smoke.
    """
    with patch(
        "custom_components.polygonal_zones.device_tracker.async_track_state_change_event",
        return_value=lambda: None,
    ):
        yield


@pytest.fixture(autouse=True)
def _reset_mutation_rate_limit():
    """Clear the module-level mutation rate-limit map between every test.

    Without this, tests that hit the same ``entry_id`` within 2s of one another
    would fail the rate-limit gate introduced for mutation services. The gate
    is a real runtime defence; in tests we want every case to start fresh.
    """
    from custom_components.polygonal_zones.device_tracker import _reset_reload_rate_limit
    from custom_components.polygonal_zones.services.helpers import (
        reset_mutation_rate_limit,
    )

    reset_mutation_rate_limit()
    _reset_reload_rate_limit()
    yield
    reset_mutation_rate_limit()
    _reset_reload_rate_limit()
