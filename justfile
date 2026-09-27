# polygonal-zones governance recipes (the cross-repo `just` convention).
#
# `just ci` mirrors the static gates in .github/workflows/validate.yml, including the same
# dependency install - mypy must run against the pinned homeassistant in requirements_test.txt
# or it reports false errors on HA's metaclass machinery.
# NOT covered locally, and remaining remote-only gates: Hassfest, HACS, Prettier and the
# Playwright config-flow test.

# Local CI gate - the same commands remote CI runs, for the checks it covers.
ci: lint test

venv:
    #!/usr/bin/env bash
    set -euo pipefail
    uv venv --python 3.14 --quiet --allow-existing .venv
    uv pip install --python .venv --quiet -r requirements_test.txt

lint: venv
    ruff check .
    ruff format --check .
    .venv/bin/mypy

test: venv
    .venv/bin/python -m pytest --cov=custom_components/polygonal_zones --cov-report=term --cov-fail-under=98

# Real-hass suite (tests_hass/) — its own venv, since pytest-homeassistant-custom-component
# hard-pins one exact homeassistant version and would fight requirements_test.txt's range
# in the shared .venv. Not part of `just ci`; not coverage-gated (see requirements_test_hass.txt).
venv-hass:
    #!/usr/bin/env bash
    set -euo pipefail
    uv venv --python 3.14 --quiet --allow-existing .venv-hass
    uv pip install --python .venv-hass --quiet -r requirements_test_hass.txt
    # shapely isn't in requirements_test_hass.txt to avoid duplicating its range
    # (requirements_test.txt is the single source of truth Renovate tracks).
    uv pip install --python .venv-hass --quiet "$(grep -E '^shapely' requirements_test.txt)"

test-hass: venv-hass
    .venv-hass/bin/pytest tests_hass -p homeassistant
