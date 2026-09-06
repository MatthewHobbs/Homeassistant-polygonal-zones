# CLAUDE.md — Homeassistant-polygonal-zones

**Tier 0** — HACS custom integration; users install it into their HA. Global rules (`~/.claude/CLAUDE.md`) apply; this file is repo-specifics only.

## What it is

HA integration that resolves any `device_tracker` into the polygonal zone it currently sits in, from a GeoJSON file. Companion to the **Homeassistant-polygonal-zones-addon** (the editor that serves `zones.json`). Community continuation of `MichelGerding/Homeassistant-polygonal-zones`. Code under `custom_components/polygonal_zones/`.

## Gates

- **Validate is the required check** (`.github/workflows/validate.yml`); coverage floor **≥98%**.
- No container boot — this is an integration, not an add-on, so the global container-verify rule does not apply here. HACS/hassfest validation must stay green.

## HA cadence (source of truth = the HA blogs, not memory)

Floor: **HA 2026.7.1 / Python 3.14**. Track breaking changes via the developer blog (https://developers.home-assistant.io/blog/) and release notes (https://www.home-assistant.io/blog/); surface when the floor or a deprecated API lags. `quality_scale: bronze` is declared; Silver/Gold/Platinum rules are implemented and tracked in `custom_components/polygonal_zones/quality_scale.yaml`, claimable only via an HA core-team review.

## Gotchas

- **SSRF protection:** private/LAN zone URLs are blocked by default; the "Allow private-network URLs (LAN)" advanced option opts in. Don't weaken this silently.
- The config flow won't continue without the location-tracking consent tick — keep that gate.
