# End-to-end config-flow smoke (Playwright)

This harness boots a **real Home Assistant** instance, installs the
`polygonal_zones` integration into its `custom_components/`, and drives the
**Settings → Devices & Services → Add Integration → Polygonal Zones** flow in a
real browser.

## Why this exists

The pytest suite uses Home Assistant's Python test harness — it never renders
the actual frontend. This smoke test catches breakage that only shows up in the
UI: a `config_flow.py` schema the frontend can't render, missing `strings.json`
/ translation keys, or a `manifest.json` that stops the integration loading.

It is **not** a required status check and is **not** wired into branch
protection, so it can never block a merge. CI runs it nightly and on demand
(`workflow_dispatch`) via `.github/workflows/playwright.yml`.

## Status: scaffold

This is a **starting skeleton**. The Home Assistant onboarding REST payloads
(`/api/onboarding/users`, `/auth/token`, `/api/onboarding/*`) and the frontend
selectors in `tests/config-flow.spec.ts` can shift between HA releases. Expect
to do one local iteration pass to get the first green run, then pin the
selectors. Search for `TODO` in `tests/global.setup.ts`.

## Run locally

```bash
# From the repo root, in one terminal — start HA with the integration staged:
HA_CONFIG="$(mktemp -d)"
mkdir -p "$HA_CONFIG/custom_components"
cp -r custom_components/polygonal_zones "$HA_CONFIG/custom_components/"
printf 'default_config:\n' > "$HA_CONFIG/configuration.yaml"
pip install "homeassistant>=2026.1,<2027" "shapely>=2.0,<3"
hass --config "$HA_CONFIG"

# In a second terminal:
cd tests/e2e
npm install
npx playwright install --with-deps chromium
npx playwright test          # or: npx playwright test --ui
```

Override the target instance with `HA_URL` (defaults to
`http://127.0.0.1:8123`).
