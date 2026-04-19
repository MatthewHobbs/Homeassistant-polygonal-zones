# Home Assistant core submission package

This directory contains the integration code reshaped for inclusion in [`home-assistant/core`](https://github.com/home-assistant/core).
The HACS-distributed version on `main` (in `custom_components/polygonal_zones/`) stays as the source of truth for HACS users; this `core-port/` tree is what you copy into a fork of `home-assistant/core` when you're ready to open the PR for issue [#8](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues/8).

## What's here

```
core-port/
├── homeassistant/components/polygonal_zones/   # Integration code (no HACS-isms)
│   ├── __init__.py                             # Same as HACS but in core's tree
│   ├── config_flow.py
│   ├── const.py
│   ├── device_tracker.py
│   ├── diagnostics.py
│   ├── icons.json
│   ├── manifest.json                           # No 'version', no 'issue_tracker'
│   ├── quality_scale.yaml
│   ├── services.yaml
│   ├── services/
│   ├── strings.json                            # Translations come from Lokalise in core
│   └── utils/
└── tests/components/polygonal_zones/           # Test suite, imports rewritten
    ├── test_*.py                               # `custom_components.*` → `homeassistant.components.*`
    └── services/
```

## Differences vs the HACS version

| Field / file | HACS (main) | Core port |
|---|---|---|
| `manifest.json` `version` | present (e.g. `"1.8.0"`) | **removed** (core auto-versions) |
| `manifest.json` `issue_tracker` | present | **removed** (core uses home-assistant/core for issues) |
| `manifest.json` `documentation` | repo URL | `https://www.home-assistant.io/integrations/polygonal_zones` |
| `manifest.json` `dependencies` | `[]` | omitted when empty |
| `hacs.json` | present at repo root | **not included** (not used in core) |
| `info.md` | present at repo root | **not included** (not used in core) |
| `translations/` | `en.json` + `de`/`es`/`fr`/`it`/`nl` | **not included** — core uses Lokalise; only `strings.json` is authored |
| `brand/` | shipped per-integration in HACS | **separate** — submit to [`home-assistant/brands`](https://github.com/home-assistant/brands) post-merge |
| Test imports | `custom_components.polygonal_zones.*` | `homeassistant.components.polygonal_zones.*` |
| Test framework | pure pytest + `unittest.mock` | same; works in core's test runner without changes |

## Step-by-step: how to submit

### 1. Prerequisites

- A GitHub account with a fork of `home-assistant/core`.
- A local clone of your fork:
  ```
  gh repo clone YOUR-USERNAME/core ha-core
  cd ha-core
  git remote add upstream https://github.com/home-assistant/core.git
  git fetch upstream
  ```
- The HA dev environment set up: <https://developers.home-assistant.io/docs/development_environment/>

### 2. Branch from `dev`

```
git checkout -b polygonal_zones-add upstream/dev
```

### 3. Copy the integration tree

From this repo's root:

```
cp -r core-port/homeassistant/components/polygonal_zones \
      /path/to/ha-core/homeassistant/components/polygonal_zones
cp -r core-port/tests/components/polygonal_zones \
      /path/to/ha-core/tests/components/polygonal_zones
```

### 4. Add codeowner entry

Edit `CODEOWNERS` in the core repo and add a line under the alphabetical section:

```
homeassistant/components/polygonal_zones/* @MatthewHobbs
tests/components/polygonal_zones/* @MatthewHobbs
```

### 5. Add to requirements

Edit `requirements_all.txt` (alphabetical) and add:

```
shapely==2.0.6
pandas==2.2.3
```

(If `pandas` is already there for another integration, leave that line alone; just add `shapely`. Run `python -m script.gen_requirements_all` if available to regenerate cleanly.)

### 6. Run the local checks

From the `ha-core` root:

```
# Format + lint
ruff format homeassistant/components/polygonal_zones tests/components/polygonal_zones
ruff check homeassistant/components/polygonal_zones tests/components/polygonal_zones

# Manifest + i18n + quality-scale validation
python -m script.hassfest --integration-path homeassistant/components/polygonal_zones

# Tests (use core's pytest config; coverage gate is set per-integration)
pytest tests/components/polygonal_zones/ -v --cov=homeassistant.components.polygonal_zones
```

Address any failures before pushing. Common things hassfest catches that don't appear in our HACS CI: requirements being out of sync with `requirements_all.txt`, manifest key ordering, missing translation keys.

### 7. Commit and push

```
git add homeassistant/components/polygonal_zones tests/components/polygonal_zones \
        CODEOWNERS requirements_all.txt
git commit -m "Add polygonal_zones integration"
git push -u origin polygonal_zones-add
```

### 8. Open the PR

Go to <https://github.com/home-assistant/core/compare> and create a PR from `YOUR-USERNAME:polygonal_zones-add` against `home-assistant:dev`.

**Title**: `Add polygonal_zones integration`

**Description** (template):

```markdown
## Proposed change
Adds a new `polygonal_zones` integration that resolves any HA `device_tracker`
entity to the named polygonal zone it currently sits inside, defined via GeoJSON.
Useful when HA's built-in circular zones aren't expressive enough — irregular
property boundaries, school catchments, town centres, etc.

## Type of change
- [x] New integration (thank you!)

## Additional information
- HACS-distributed precursor with full implementation history:
  https://github.com/MatthewHobbs/Homeassistant-polygonal-zones
- Latest HACS release: v1.8.0
- 100% line coverage in the source repo's test suite
- All Bronze quality-scale rules implemented; quality_scale.yaml records
  status of every Bronze/Silver/Gold/Platinum rule for review

## Quality-scale rules implementation status
See `homeassistant/components/polygonal_zones/quality_scale.yaml`. Every Bronze
rule is `done` or `exempt` with documented reasoning. Higher-tier rules are
also implemented; happy to discuss tier assignment with the architecture team.
```

### 9. Brand assets — separate PR

The icon/logo files in this repo's `custom_components/polygonal_zones/brand/`
are NOT submitted to home-assistant/core. They're served by HA's Brands Proxy
API, which auto-fetches from the integration's own repo path post-merge —
see the [Brands Proxy API announcement](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api).

If the proxy doesn't auto-pick them up, the fallback is a separate PR to
[`home-assistant/brands`](https://github.com/home-assistant/brands) — though
that repo no longer accepts custom-integration brands as of HA 2026.3.0
(an earlier PR there was auto-closed for exactly this reason).

### 10. Wait for review

No SLA. Typical wait: weeks to months for a new integration. Architecture team
will likely request changes; address them, push more commits to the branch,
mark "ready for review" again.

Common things they may push back on:

- **`runtime_data` migration** — already done. ✓
- **`pytest-homeassistant-custom-component` references** — none in the ported tests; we use pure pytest with mocks, which works in core. ✓
- **`hass.async_add_executor_job` for shapely calls** — already done in `device_tracker.update_location`. ✓
- **Single `services.py` vs `services/` sub-package** — we use a sub-package; core convention is increasingly a single file. May be asked to consolidate.
- **Snapshot tests** — core encourages syrupy snapshots for large outputs (e.g. config-flow renders, diagnostics dumps). Optional but nice.
- **`inject-websession`** — we use a per-call session with a custom DNS resolver for SSRF protection. Be ready to defend this; it's documented as exempt in `quality_scale.yaml`.

### 11. After merge

- Update this repo's README to point users at the core integration (HACS becomes legacy).
- Decide whether to keep this HACS repo in maintenance-only mode or archive it.
- Open a docs PR against `home-assistant.io` so `https://www.home-assistant.io/integrations/polygonal_zones` actually exists.

## Keeping this port in sync

If you modify the HACS version on `main` after this branch was prepared,
re-run the port. There's no automated sync — the simplest path is to delete
this `core-port/` directory and rebuild from current `main` using the same
`cp` + `sed` steps that originally produced it.
