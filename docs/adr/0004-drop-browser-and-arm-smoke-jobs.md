# ADR 0004: Drop the browser config-flow and ARM import smoke jobs

- **Repo:** Homeassistant-polygonal-zones
- **Status:** Accepted (2026-10-20)
- **Context:** An audit of the repository found about 690 lines of CI and a Node toolchain whose gates either checked little or did not match production. Neither job is a required check.
- **North star:** Every CI job that remains can fail for a reason that matters to a user of the integration.

## Decision

I am removing the Playwright config-flow smoke (`playwright.yml`, `_playwright-config-flow.yml`, `tests/e2e/`) and the multi-arch import smoke (`multi-arch.yml`, `tests/smoke/`). The nightly beta job keeps its pytest suite and loses its Playwright leg, which supersedes that part of ADR 0002.

| #   | Step                                                                                           | Owner | Status | Evidence |
| --- | ---------------------------------------------------------------------------------------------- | ----- | ------ | -------- |
| 1   | Delete both smoke jobs and their files; update `nightly-beta`                                  | matt  | Done   | #124     |
| 2   | Reinstate an ARM check against HA's own wheel index, only if users report ARM install failures | matt  | Open   |          |

Status is one of **Open**, **Done**, **Blocked**, **Dropped**.

## Context

The browser test only checked that "Polygonal Zones" appears in the Add Integration search of a real Home Assistant. It never opened the flow, so it never exercised `strings.json`, the translations or the consent gate. The one failure it ever recorded was a broken test selector, not a product fault. The real-Home-Assistant suite in `tests_hass/` and the config-flow unit tests cover the behaviour.

The ARM smoke imported shapely inside Debian `python:3.14-slim` against PyPI, while Home Assistant installs from its own wheel index, so neither a pass nor a failure said whether a user could install. It also ran `tonistiigi/binfmt` privileged with unpinned images that Renovate does not track.

## Consequences

**Accepted**

- A Home Assistant frontend change that stops a config-flow integration being listed in the brand search would no longer be caught here. That would be Home Assistant's fault and users would report it quickly.
- A shapely release inside the supported range with no aarch64 wheel would no longer be caught by CI. The nightly pytest run still exercises shapely on amd64.

**Watch**

- If users report an install failure on ARM hardware, step 2 applies.

## Verification (2026-10-20)

- Nothing references a removed workflow, job or script: a case-insensitive grep of the branch for the removed names finds only this ADR and ADR 0002, and `actionlint` passes.
- No removed job is a required check on `main` (required: Pytest, Pytest (HA floor), Hassfest, HACS, Ruff, Prettier, Mypy), so no pull request waits for a check that never runs.
- Not checked: whether Home Assistant OS on aarch64 gets shapely from its musllinux wheel index, which I took from the removed workflow's own comment.

## References

- [ADR 0002](0002-nightly-ha-beta-testing.md)
