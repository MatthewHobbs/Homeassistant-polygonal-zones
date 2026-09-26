# ADR 0002: Nightly HA beta testing (Option A)

- Status: Accepted
- Date: 2026-09-26
- RFC: [RFC 0006 — Homeassistant-polygonal-zones: nightly HA beta testing](https://claude.ai/artifact/P53H7DpiqckHyk4L2YpnyU) (`claude-config` `docs/rfc/README.md`)

## Context

`_upstream-gate.yml`'s `latest()` explicitly skips prereleases
(`if parsed.is_prerelease: continue`), so the nightly gate and the
Playwright/multi-arch smokes only ever test stable HA releases. HA typically
ships a beta about a week before the matching final release. A breaking API
change lands in that beta, but nothing in this repo's CI would catch it until
the final release ships — at which point users already have it.

Issue #84 showed this repo's users notice and report quickly, and turnaround
has been same-day (v1.14.1, v1.14.2). A week of advance notice from testing
betas would let a fix land before the breaking release reaches users, instead
of after.

## Decision

Option A: a separate, non-required nightly job that resolves the latest HA
_prerelease_ (dropping the `is_prerelease` filter for this one query) and
runs the existing pytest/Playwright suite against it. `continue-on-error:
true`, and its own cache-fingerprint namespace so it never interacts with the
stable gate.

- **Cadence: nightly** — matches the existing gate's schedule; the
  fingerprint cache already skips re-running when nothing changed, so nightly
  costs little more than weekly would.
- **Failure handling: start simple** — red in Actions only, no auto-opened
  issue. This repo has no existing issue-automation infra; revisit if
  red-in-Actions proves too easy to miss.

Owner's decision, verbatim: "rfc006 answer option A, nightly cadence, start
simple."

## Alternatives

From RFC 0006:

| Option                                 | What changes                                                                                                                                                                                                                                                                                                             | Cost                                                                         | Risk                                                                                                                                                                                                                                                                                                                    |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A. Separate nightly job (chosen)**   | New job (or extend `_upstream-gate.yml`) that resolves the latest HA _prerelease_ (dropping the `is_prerelease` filter for this one query) and runs the existing pytest/Playwright suite against it. Non-required, `continue-on-error: true`, own cache-fingerprint namespace so it never interacts with the stable gate | About 40–60 lines, mirrors the existing gate+smoke shape already in the repo | Low — isolated blast radius, can never block a merge or release. Main risk is a noisy/expected-red run being misread as "our code is broken" rather than "HA's beta broke something" — needs a clear job name/description                                                                                               |
| B. Fold a beta leg into `validate.yml` | Add a `pytest-beta` job next to `pytest-floor`, gated the same way, installing the latest prerelease                                                                                                                                                                                                                     | Smaller diff (one job, no new workflow)                                      | Medium — couples an intentionally-flaky signal into the workflow that gates `release.yml`'s SHA-verification; needs the same `continue-on-error` discipline as Playwright to avoid ever blocking a release, and future readers may be confused why a job in the _required-check_ workflow is expected to sometimes fail |
| C. Don't do it                         | No change                                                                                                                                                                                                                                                                                                                | None                                                                         | No early warning; matches status quo — acceptable given fixes have shipped same-day so far, but means users are the first to hit a breaking beta-introduced change rather than CI                                                                                                                                       |

Option A was chosen because it gets the same early-warning value as B without
touching the workflow whose green gates releases — an experimental,
expected-to-sometimes-fail signal belongs in its own isolated job, not folded
into the one that decides whether a release can ship.

## Consequences

- Implementing the job (extending `_upstream-gate.yml` with an
  `include_prereleases` input, or a small parallel resolution step, plus the
  new nightly job itself) is a separate step from this ADR, tracked
  separately in this repo.
- A failing nightly beta run means "HA's beta broke something," not "our code
  is broken" — the job's name and description need to make that distinction
  clear so it isn't misread as a regression in this integration.
- No auto-opened issue on failure (start simple, per the decision above); if
  a failure goes unnoticed in practice, revisit failure handling rather than
  treating this as settled forever.
