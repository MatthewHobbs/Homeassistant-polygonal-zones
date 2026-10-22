# Contributing

This is a community-maintained fork (see the README fork notice). Pull requests are welcome; replies come at a spare-time pace.

## Run the checks

`just ci` runs Ruff, Mypy and the tests with the 98% coverage floor, in a Python 3.14 `.venv` that it creates with `uv`. Without `just`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
pytest --cov=custom_components/polygonal_zones --cov-fail-under=98
ruff check .
ruff format --check .
mypy
```

Prettier, Hassfest and HACS run only in CI. Check JSON, Markdown and YAML locally with `npx prettier@3 --check "**/*.{json,yaml,yml,md}"` (`--write` fixes them).

`just test-hass` runs `tests_hass/` against a real Home Assistant in a separate `.venv-hass`. Keep it out of the main `.venv`: `pytest-homeassistant-custom-component` pins one exact Home Assistant version. This suite is not part of `just ci` and has no coverage gate.

## CI

`validate.yml` runs on every pull request. These jobs must pass to merge: `Pytest`, `Pytest (HA floor)`, `Hassfest`, `HACS`, `Ruff (lint + format)`, `Prettier` and `Mypy`. `Pytest (real hass)` and `HA floor within lag bound` also run but do not block.

`Pytest (HA floor)` installs the Home Assistant version in `hacs.json`, so do not use APIs newer than that floor.

## Tests

- Unit tests run without Home Assistant: `pyproject.toml` passes `-p no:homeassistant` and tests use `SimpleNamespace` and `MagicMock` stubs. `pytest-asyncio` is in auto mode, so write `async def test_*` without a decorator. Anything that needs a real Home Assistant goes in `tests_hass/`.
- Each test asserts an observable effect (state, exception, log line, written file, mock call) and would fail on a plausible regression. Do not add tests only to cover a line.
- `tests/conftest.py` has an autouse fixture that resets module-level state (the action and `reload_zones` rate limits). Extend it when you add module-level state.
- Fake entities in action tests need a `_config_entry_id` attribute; the actions read it for audit logging and rate limiting.

## Adding a config option

1. Add the key to `const.py` as `CONF_*`.
2. Add it to `config_flow.py`: `build_create_flow` (new installs and reconfigure) and `build_options_flow` (existing entries).
3. Add the strings to `strings.json` and `translations/en.json`, in both the `config` and `options` sections.
4. Read it with `entry.data.get(CONF_*, fallback)` where it is used: `__init__.py` (`_build_zone_source`) for source settings, the `device_tracker.py` and `sensor.py` setup for entity settings. Choose the fallback for existing entries that lack the key with care.
5. Show it in `diagnostics.py`.
6. Add config-flow tests and runtime-behaviour tests.

## Commits and pull requests

- One logical change per commit.
- Use Conventional Commits 1.0.0 (`fix: ...`, `feat: ...`), imperative mood, 72 characters at most on the subject line. Put the reason in the body; the diff shows the change.
- Pull requests are squash-merged, so the PR title becomes the commit subject and follows the same format. The description covers the problem, the fix, the test plan and anything to check by hand.

## Translations

Only English ships: `custom_components/polygonal_zones/strings.json` (the source) and `translations/en.json`. Home Assistant falls back to English for other languages. To add one, copy `translations/en.json` to `translations/<lang>.json`, translate the values, keep the JSON keys and any `{placeholders}`, and open a PR.
