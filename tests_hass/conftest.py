"""Test configuration for the real-hass suite (see requirements_test_hass.txt).

Separate from tests/conftest.py deliberately: the main suite disables the
``pytest-homeassistant-custom-component`` plugin (``-p no:homeassistant`` in
pyproject.toml) because it hard-pins one exact HA version, which would fight
this repo's floor/latest dual-testing installs. This directory re-enables it
(the CI job passes ``-p homeassistant`` on the command line) and is never
collected by the main ``pytest``/``pytest --cov`` invocation.
"""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/ discoverable — the standard HA test fixture for this."""
    yield
