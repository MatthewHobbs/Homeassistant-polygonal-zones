# ADR 0002: Nightly HA beta testing

- **Repo:** Homeassistant-polygonal-zones
- **Status:** Accepted (2026-09-26); the Playwright leg was superseded by [ADR 0004](0004-drop-browser-and-arm-smoke-jobs.md)
- **Context:** CI only tested stable Home Assistant releases, so a breaking change in a beta reached users with the final release.
- **North star:** A Home Assistant beta that breaks this integration turns a CI run red before the final release ships.

## Decision

I chose a separate, non-required nightly job that resolves the latest Home Assistant _prerelease_ in `requirements_test.txt`'s range and runs the pytest suite against it, in its own cache-fingerprint namespace so it never interacts with the stable gate. It runs on `schedule` and `workflow_dispatch` only, nightly, and a failure just shows red in Actions: no auto-opened issue, and no `continue-on-error`.

| #   | Step                                                                | Owner | Status | Evidence |
| --- | ------------------------------------------------------------------- | ----- | ------ | -------- |
| 1   | `include_prereleases` input on `_upstream-gate.yml`                 | matt  | Done   | #93      |
| 2   | The nightly beta job (`nightly-beta.yml`)                           | matt  | Done   | #93      |
| 3   | Open an issue automatically on failure, if a red run goes unnoticed | matt  | Open   |          |

Status is one of **Open**, **Done**, **Blocked**, **Dropped**.

## Context

`_upstream-gate.yml` skipped prereleases, and Home Assistant ships a beta about a week before the matching final release. Reports on #84 were fixed the same day (v1.14.1, v1.14.2), so a week's notice would let a fix land before the breaking release instead of after. The options not chosen are in the design note.

## Consequences

**Accepted**

- A red nightly run means "Home Assistant's beta broke something", not "our code is broken". The job's name says so.
- No automatic issue on failure; step 3 covers it if a red run goes unnoticed.

**Watch**

- Nothing tells me when a beta needs a newer Python than the one pinned in the workflow.

## Verification (2026-09-26)

- The design note said `continue-on-error: true`. Checked against the repo's own precedent: it makes GitHub report the run as a success even when the job fails, which would defeat "red in Actions only". The job only needs `schedule` and `workflow_dispatch`, so `continue-on-error` is dropped.
- Dropping the `is_prerelease` pre-filter is enough on its own: `packaging`'s per-candidate `SpecifierSet.contains()` matches prereleases when no `prereleases=` argument is given. Checked in the installed `packaging` 26.1 docstring and with a real beta version string.

## References

- [ADR 0004](0004-drop-browser-and-arm-smoke-jobs.md)
