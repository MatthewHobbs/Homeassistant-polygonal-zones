"""Test configuration for polygonal_zones.

Pure-pytest tests only at the moment — the ``hass`` fixture from
``pytest-homeassistant-custom-component`` is not used yet, so its plugin is
disabled via ``-p no:homeassistant`` in ``pyproject.toml``.
"""

import pytest


@pytest.fixture(autouse=True)
def _reset_mutation_rate_limit():
    """Clear the module-level mutation rate-limit map between every test.

    Without this, tests that hit the same ``entry_id`` within 2s of one another
    would fail the rate-limit gate introduced for mutation services. The gate
    is a real runtime defence; in tests we want every case to start fresh.
    """
    from custom_components.polygonal_zones.services.helpers import (
        reset_mutation_rate_limit,
    )

    reset_mutation_rate_limit()
    yield
    reset_mutation_rate_limit()
