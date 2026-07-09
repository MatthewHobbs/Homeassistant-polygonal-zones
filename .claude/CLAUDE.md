# Homeassistant-polygonal-zones — project notes for Claude

Project-local overrides/narrowings of the global `~/.claude/CLAUDE.md`. This file records
**only** where the global rules are wrong, incomplete, or need a project-specific fact — every
other global rule (git branch naming, dual review, Dependabot pre-check, branch-protection
baseline, open-questions system, HA release-cadence tracking) is inherited unchanged and is not
restated here.

## Project type — NOT a container (scopes out the global Docker-verify rule)

This ships as a **HACS custom integration**: the source under `custom_components/polygonal_zones/`
is copied into a user's Home Assistant config. There is **no Dockerfile, no registry image, no
`/data` mount, no `image:`/`version:` tag pull**. The global "local Docker build + boot before
recommending merge" rule **does not apply here** — do not attempt a docker build/boot; there is
nothing to boot. (The paired editor add-on is a _separate_ repo; that one is a container.)

## What "verify before merge" means here

- **Local:** `.venv/bin/pytest` (with `--cov`, coverage gate **≥98%**), `.venv/bin/ruff check` +
  `ruff format`, `.venv/bin/mypy custom_components/polygonal_zones`, and `npx prettier@3` for
  JSON/Markdown/YAML.
- **CI is the merge gate.** The **required** status check on `main` is **`Pytest`** (branch
  protection). Full CI set: Hassfest, HACS, Ruff, Prettier, Mypy, Pytest, Pytest (HA floor), plus
  **non-required** Playwright and multi-arch smoke.
- This is a **public** repo → GitHub Actions minutes are free; optimise CI for latency/clarity,
  not minutes.

## Home Assistant compatibility floor

Home Assistant **2026.7.1+**, Python **3.14**. Before claiming the project is "up to date", check
the HA developer blog / release notes for breaking changes (the global HA-cadence rule applies).

## Dependencies

Single runtime dependency: **`shapely>=2.1.2,<3`** (the manifest floor matches the tested floor).
`manifest.json` declares `dependencies: []`.

## Review roster for this repo

Backend-only integration — no custom frontend (the config flow is HA-rendered from
`strings.json`/`translations`), no data pipeline, no server deploy surface. For a code review the
lenses that actually fire here are: **staff-engineer** / **principal-engineer** (Python
correctness), **security-reviewer** (untrusted GeoJSON + URL/SSRF input), **qa-lead** (the
coverage gate), **technical-writer** (README/docs), and **chief-architect** for zone/entity-model
changes. `lead-frontend`, `product-designer`, and `data-engineer` effectively never apply.
Run the full `/orchestrate` panel only for a release cut or an explicit multi-axis request — not
for routine changes.

## Precedence

This file narrows/overrides the global `~/.claude/CLAUDE.md` for this repo; it does not restate
rules it doesn't change. On conflict, **this file wins for this repo**.
