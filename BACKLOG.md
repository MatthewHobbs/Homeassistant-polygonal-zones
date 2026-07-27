# Backlog

## CI cost / GitHub Actions minutes (2026-07-27) — OPEN

From an account-wide GitHub Actions cost review. **This repo is the personal account's #1 Actions
cost driver** — the only repo with a net charge in 2026: **July = $36.59 net** ($70.01 gross,
**11,668 `Actions Linux` minutes**), and climbing hard — **1,061 → 4,071 → 11,668** minutes over
May → Jun → Jul. All jobs run on standard `ubuntu-latest`.

> **Confirm visibility FIRST — this may already be solved.** Standard runners are **free on public
> repos**. This repo currently reads `public`; a public repo billing standard minutes almost
> certainly means it was **private during the billed months and has since been made public**, in
> which case the bill self-corrects to ~$0 in August. Verify whether it was private in July before
> investing effort. The items below are worth doing for **wall-clock speed regardless**, and are
> the whole bill if it stays/returns private. Severities assume "still billed"; as pure hygiene → P2.

- **P1 — redundant `push` + `pull_request` double-runs.** `multi-arch.yml` and `validate.yml`
  trigger on **both** `push` and `pull_request`, so every PR commit runs the whole suite **twice**
  for the same SHA. Fix: drop `push:`, or scope it to `branches: [main]`. Halves the runs on the two
  heaviest workflows (Validate = 8 jobs × 26 runs/30d; Multi-arch = matrix × 26 runs/30d).
- **P1 — three daily `schedule` crons.** `multi-arch.yml` (`0 0 * * *`), `validate.yml`
  (`0 0 * * *`), `playwright.yml` (`30 3 * * *`) each fire a full run every day → ~90 scheduled
  runs/month of pure upstream-drift checking. Fix: weekly (`0 0 * * 1`) or `workflow_dispatch`-only.
  Removes the recurring floor.
- **P1 — no `concurrency: cancel-in-progress`.** Superseded pushes run to completion instead of
  cancelling. Fix: add a `concurrency` group keyed on `github.ref` with `cancel-in-progress: true`.
- **P2 — multi-arch (QEMU) on every PR/push.** Emulated multi-arch is 5–10× slower than native.
  Fix: single native arch on PR, multi-arch only on release/tag; add buildx layer cache
  (`cache-from/to: type=gha`). Biggest per-run time cut.
- **Rejected alternative (record):** a self-hosted runner on `nuc-02` to dodge the bill was
  considered and **rejected** — this is a **public** repo, and a self-hosted runner on a public repo
  = fork-PR RCE from any contributor. Keep CI on GitHub-hosted; the levers above dominate on cost.

Owner: matt. Raised by: account cost review (measure-first). Est: ~60–80% fewer billed minutes if
still private; otherwise pure speed/hygiene. **Do the visibility check before implementing.**

---

_Everything below is the resolved **2026-07-09 end-of-day panel review** (kept for record)._

Findings from the **end-of-day panel review of 2026-07-09** (read-only audit; nothing
was changed in source). Panel: security-reviewer, dpo, sre-reliability, chief-architect,
qa-lead, technical-writer, product-manager. Coverage measured at **99%** (271 tests, gate ≥98%).

Promote items to GitHub issues as you pick them up. Severity: P0 = fix before next release /
compliance gap, P1 = this sprint, P2 = backlog.

> **Update 2026-07-09 — ALL P0s and P1s are now fixed and merged.** Four PRs, each squash +
> signed, CI green, dual-reviewed (Claude + codex):
>
> - **[PR #40](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/pull/40)** — P0s: consent scope-creep, retry-stampede jitter, download-mode setup fragility.
> - **[PR #41](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/pull/41)** — remaining P0 (LAN/SSRF onboarding) + bounded P1s: vertex-cap bypass, URI leak, `matched_zones`/`zone_uris` gating, `async_reload_zones` raise, dead `async_update_config` removed, lock-identity race, stale `reload_zones` doc, config-flow inline hint, qa P0 escalation-branch tests + malformed-feature tests.
> - **[PR #42](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/pull/42)** — `state_changed` → `async_track_state_change_event`.
> - **[PR #43](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/pull/43)** — entry-scoped `ZoneSource` (single fetch/parse/load-lifecycle; dissolves the per-entity fan-out).
>
> **Update 2 — P2s + Dependabot now resolved too (PRs #44, #45).**
>
> - **[PR #44](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/pull/44)** — all 6 Dependabot bumps (#33–#38, now closed) + shapely manifest floor →2.1.2.
> - **[PR #45](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/pull/45)** — actionable P2 cleanups: reload_zones rate-limit, restore-attr coord filter, `entry.options` split-brain, download-path helper, `RecursionError` parity, dead strings, strict-typing, README caps + ELI5 glosses.
> - A handful of P2s were consciously **not** done (admin-gating reload, shared HTTP session, test-file renames, an obsolete privacy note) — rationale in each item / PR #45.

---

## Verdict: RESOLVED — all P0s, P1s, actionable P2s, and Dependabot merged to `main`

Every P0- and P1-severity finding is fixed (PRs #40–#43); the actionable P2s and all six
Dependabot PRs are resolved (PRs #44–#45). What remains below is a short list of
deliberately-declined P2s (each annotated) — no open action.

> **Update 3 (2026-07-09, backlog review pass)** — re-verified against `origin/main` @ `b4cffa8`
> (11 commits ahead of this doc's last edit; PRs #46–#50 landed since, all CI/config-only, zero
> `custom_components/` diff — confirmed via `git diff`). Two items this doc still listed as open
> were actually already resolved as side effects of PR #43/#45 and just never got their checkmark:
>
> - qa-lead P0 (untested `ZoneFileCorrupt` escalation) — PR #43's `ZoneSource` refactor collapsed
>   the 3 original call sites into 1 (`zone_source.py:141-150`), now covered by
>   `tests/test_zone_source.py:44-54` and `tests/test_device_tracker_added.py:74-88`.
> - technical-writer's dead-strings flag (`no_entities`, `download_or_no_zones`) — PR #45 deleted
>   both keys outright (commit `b1b0397`); nothing left to decide.
>
> One residual, sub-P0 gap found during re-verification: no test explicitly asserts
> previous-zones-are-retained-on-load-failure (the "retain previous zones" half of the original
> qa-lead ask) — implicit in the code (`self.zones` only mutates on success) but not asserted.
> Not worth a P-severity item on its own; note it if `zone_source.py` gets touched again.

---

## Consensus items (raised independently by ≥2 specialists — highest signal)

### ✅ P0 (DONE — PR #40) — Consent gate is bypassed when adding trackers via Reconfigure

**Fixed 2026-07-09:** reconfigure now re-applies the consent gate when the submitted entity
set grows vs. the stored entry, and persists a `consent_confirmed_at` timestamp on both initial
setup and reconfigure. Tests added for consent-on-add, no-consent-on-URL-edit, and timestamp
carry-forward.

<details><summary>Original finding</summary>

`config_flow.py:170-186` (`async_step_reconfigure`) reuses `build_create_flow` — which
includes the `CONF_ENTITIES` selector — but never adds the consent checkbox and never
re-notifies. An operator can add a _new person's_ `device_tracker` to an existing entry with
zero re-attestation. The lawful-basis floor enforced at first setup silently doesn't apply to
scope expansion. Also: `config_flow.py:150` discards the consent tick immediately
(`user_input.pop("consent", None)`) — no persisted evidence of _when / for which entities_
consent was confirmed (GDPR Art. 7(1) accountability).

- Fix: extend the reconfigure schema with the consent checkbox whenever submitted
  `CONF_ENTITIES` grows vs. the stored entry; persist a `consent_confirmed_at` timestamp.
- Raised by: dpo (P0). Related: security-reviewer noted `reload_zones` is un-gated.

</details>

### ✅ P0+P1 (DONE — PR #40 jitter, PR #43 refactor) — Per-entity zone ownership causes a startup retry stampede + redundant work

**Fixed 2026-07-09:** PR #40 added equal jitter to the retry backoff; PR #43 completed the
deeper fix — a single entry-scoped `ZoneSource` on `entry.runtime_data` that all mirrors read
from, eliminating the redundant per-entity fetch/parse and dissolving the
`sync_entities_after_write` fan-out.

<details><summary>Original finding</summary>

Every `PolygonalZoneEntity` under one entry independently fetches/parses the _same_ zone
source and runs the _same_ backoff schedule with **no jitter**
(`device_tracker.py:196-234`, `:220`). With N devices on one URL, a flaky host gets N
synchronised GETs at t=0, 30s, 90s, 210s, 450s — a self-inflicted stampede against your own
dependency, and N identical executor parses of byte-identical input. The idiomatic fix is a
single entry-scoped zone holder (on `entry.runtime_data`, already a dataclass) that all mirror
entities read from — which also deletes the `sync_entities_after_write` fan-out and the
"keep them all in sync" complexity.

- Raised by: sre-reliability (P0, stampede) + chief-architect (P1, state should be entry-scoped).
- Add jitter to backoff as an immediate mitigation even before the larger refactor.

</details>

### ✅ P1 (done) — Vertex/complexity cap bypassed by non-Polygon geometry on the READ path

`count_geometry_vertices` (`utils/limits.py:29-38`) only walks Polygon/MultiPolygon; a
`LineString`/`GeometryCollection` returns **0**, so a ~5 MiB single-feature LineString sails
past `MAX_TOTAL_VERTICES_PER_COLLECTION`. The load path's `_parse_feature`
(`utils/zones.py:117,172-180`) calls `shape()` on _any_ geometry type — unlike the admin
service validator (`services/helpers.py:102-107`) which restricts to `SUPPORTED_GEOMETRY_TYPES`.
`buffer.intersects()` then runs over it on _every_ `state_changed`, draining HA's shared
executor. Secondary: a Point/LineString reaching the tie-break hits `geometry.exterior`
(`utils/geometry.py:34`) → `AttributeError` per GPS update.

- Fix: restrict `_parse_feature` to Polygon/MultiPolygon (reuse `SUPPORTED_GEOMETRY_TYPES`)
  and/or count unknown geometries conservatively. Closes the cap bypass and the crash together.
- Raised by: security-reviewer (P1) + qa-lead (line 178 vertex cap untested on read path).

### ✅ P1 (done) — Stale doc: "call reload_zones after a mutating action"

`README.md:143-145` tells users to call `reload_zones` after mutations, but all four services
call `sync_entities_after_write` (`services/*.py`, `services/helpers.py:212-223`) which already
refreshes every entity before the call returns. The manual step is a no-op.

- Fix (writer supplied replacement text): say mutations auto-refresh; use `reload_zones` only
  to re-fetch _source_ files/URLs (e.g. after editing zones.json out-of-band or host recovery).
- Raised by: technical-writer (P1) + chief-architect (cross-cutting note).

### ✅ P0/UX (DONE — PR #41) — LAN + SSRF-default is the primary persona's first-run failure

**Fixed 2026-07-09:** `validate_zone_urls` now returns a specific `private_url_blocked` error
naming the "Allow private-network URLs (LAN)" toggle when a literal private/loopback IP is
pasted — so the user fixes it at the form instead of the entry silently failing at startup.

<details><summary>Original finding</summary>

The Quick Start recommends installing the companion add-on first; it serves a **LAN URL**; the
integration **blocks LAN by default** (SSRF). So the default paired-product path hits
"Refusing to connect to non-public address" before the first zone loads.

- Fix (no security change — sequencing/copy only): Quick Start step 4 should say "if you
  followed step 1, enable **Allow private-network URLs (LAN)** now," _before_ the error.
  Consider a config-flow inline hint when a private-range host is pasted with the toggle off.
- Raised by: product-manager (P0) + technical-writer (P2, SSRF/RFC-1918 unglossed in docs).

</details>

---

## Security (security-reviewer)

- **✅ P1 (done) — URI leak via error strings into diagnostics/logs.** Diagnostics redact the `uri`
  field, but `err` strings embed the full URI verbatim (`utils/general.py:96,110,113,121`,
  `utils/zones.py:257-259`) and flow into `diagnostics.py:57-60` and WARNING logs
  (`device_tracker.py:221-227`). A URL with userinfo creds or a query token leaks into a
  public bug report. Fix: store host-only/index in failure records; strip userinfo before
  logging. (dpo separately confirmed coordinate redaction itself is correct — this is a
  _second_ channel dpo's field-level check didn't cover.)
- **✅ P2 (rate-limit done, PR #45; admin-gating declined) — `reload_zones` is not admin-gated or rate-limited** (`device_tracker.py:124-129`);
  any authenticated non-admin can spam outbound fetches. Small blast radius (target is
  admin-fixed + SSRF-protected). Reuse `enforce_mutation_rate_limit`.
- **✅ P2 (done, PR #44) — supply chain:** manifest floor `shapely>=2.0` is looser than the tested `>=2.1.2`;
  raise the manifest floor to match what CI actually exercises. GH Actions are **all
  SHA-pinned** (verified) — posture sound; the 5 Dependabot Action PRs are SHA→SHA, safe
  after changelog review.
- **✅ P2 (done, PR #45) —** catch `RecursionError` in `_parse_zone_document` (`utils/zones.py:139`) for parity
  with the service parsers.
- Confirmed solid (no action): SSRF resolver filters inside `resolve()` (closes DNS-rebinding
  TOCTOU), `trust_env=False`, `allow_redirects=False`, streaming 5 MiB cap, `safe_config_path`
  symlink resolution, `save_zones` O_NOFOLLOW + atomic replace, admin-only mutations.

## Privacy (dpo)

- **✅ P1 (done) — `matched_zones` and `zone_uris` attributes bypass `expose_coordinates`**
  (`device_tracker.py:341-353`) — published unconditionally even when coordinates are off.
  `matched_zones` reveals overlapping semantic location; `zone_uris` can leak LAN
  hostnames/paths on a shared dashboard. Gate behind `expose_coordinates` or document.
- **✅ P2 (done, PR #45) — restored attributes may re-expose coordinates after opt-out.** `async_added_to_hass`
  restores `last_state.attributes` wholesale (`device_tracker.py:194`); if a user turned
  coordinates off, previously-recorded lat/lon can persist until the next live update. (Also
  flagged by chief-architect as a cross-cutting note.)
- **⏭️ P2 (obsolete — PR #41 made reconfigure re-attest) —** document in `docs/privacy.md` that Reconfigure currently permits adding trackers
  without re-attesting, until the P0 fix lands.
- Confirmed good: diagnostics excludes lat/lon/gps_accuracy + redacts entities/urls/title;
  no `_LOGGER` call logs raw coordinates; legacy `expose_coordinates=on` migration is
  non-silent (repair issue, clears on opt-out) — defensible. Erasure runbook in privacy.md is
  genuinely usable.

## Reliability (sre-reliability)

- **✅ P0 (DONE — PR #40) — download_zones initial fetch has none of the per-entity resilience.**
  The initial `download_zones` materialisation in the device-tracker `async_setup_entry` used
  to propagate any failure and hard-fail the _entire_ entry (no entities, no retry). **Fixed
  2026-07-09:** transient failures now raise `ConfigEntryNotReady` (HA retries with backoff);
  the one unambiguously-permanent case, `UnsupportedSchemaVersion`, raises `ConfigEntryError`
  (HA stops retrying, shows an actionable error) rather than spinning forever. Tests added for
  both paths. _(Deeper transient-vs-permanent typing for the ambiguous `ZoneFileCorrupt` bucket
  needs the loader refactor — folded into the entry-scoped-state P1.)_
- **✅ P1 (done) — `async_reload_zones` silently swallows failures even with `return_response`.**
  `device_tracker.py:426-433` logs WARNING and returns `None` before building the response —
  a `return_response: true` caller sees a "successful" call with no zones and no error. Raise
  `HomeAssistantError` like the mutation services. (qa-lead: this branch is also untested.)
- **✅ P1 (done) — dead/misleading `async_update_config`.** `device_tracker.py:266-298` is never invoked
  (`__init__.py:56` wires `async_reload_entry` → full `async_reload`). It reads like a graceful
  in-place update path that doesn't exist; any options change flickers all entities unavailable.
  Delete it or wire it. **See conflict below.**
- **✅ P1 (done) — lock-identity race across entry reload.** `release_file_lock`
  (`utils/local_zones.py:44-50`) drops the cached `asyncio.Lock` without waiting for an
  in-flight holder; a mutation mid-write during a reload can get a _new_ Lock for the same
  path → two concurrent writers. Join/refuse-while-locked before dropping.
- **⏭️ P2 (moot/declined — refactor collapsed N fetches→1 per entry) —** no connection reuse (new `TCPConnector`/`ClientSession` per fetch per entity per
  URI); collapse duplicate per-entity failure tracebacks (`utils/zones.py:234`,
  `exc_info=True`) to one log line at entry granularity.

## Architecture (chief-architect)

- **✅ P1 (done) — zone state is per-entity but logically entry-scoped** (same root as the sre P0 above).
  Move the loaded `list[Zone]` + `last_load_*` onto `entry.runtime_data`
  (`__init__.py:28-35`); dissolves `sync_entities_after_write` and the service/diagnostics
  private-attribute reach-ins.
- **✅ P1 (done) — global `state_changed` bus listener per entity** (`device_tracker.py:262-264`) filters
  by entity_id in Python; with M mirrors every unrelated state change wakes M coroutines. Use
  `async_track_state_change_event(hass, [entity_id], cb)` — the primitive the
  `entity-event-setup` gold rule already points to. Collapses the manual `_unsub` bookkeeping.
- **✅ P2 (done, PR #45) — `entry.options` is written but never read** (`config_flow.py:201-215`) — split-brain;
  everything reads `entry.data`. Drop the options write or commit to the options model.
- **✅ P2 (done, PR #45) — download path built three different ways** (`device_tracker.py:95` raw f-string vs.
  `__init__.py:66-74` `safe_config_path` vs. services); one bypasses the guard. Extract a
  single `download_path_for(config_dir, entry_id)` helper.
- **✅ P2 (done, PR #45) — `strict-typing: done` mildly overclaimed** (`quality_scale.yaml:101`): `update_location`
  and `async_reload_zones` params unannotated (`device_tracker.py:328,402`).
- Confirmed good: `runtime_data` + typed config-entry alias, `async_migrate_entry` stub,
  atomic `save_zones`, `ZoneLoadResult` partial-success model, executor offload.

## Test coverage (qa-lead) — 99%, gate ≥98%; the NUMBER is fine, these are quality gaps

- **✅ P0 (done, incidentally via PR #43/#45) — the "all URIs failed → `ZoneFileCorrupt`" escalation
  is untested at all three device_tracker call sites** (original finding: lines 210-211, 280-281,
  420-421). The PR #43 `ZoneSource` refactor collapsed the 3 call sites into 1
  (`zone_source.py:141-150`), which now raises `ZoneFileCorrupt` on `ZoneLoadResult(zones=[],
failures=[...])` and is covered by `tests/test_zone_source.py:44-54` and
  `tests/test_device_tracker_added.py:74-88`. Residual: no test explicitly asserts
  previous-zones-retention on failure — noted above, not P0-worthy on its own.
- **✅ P1 (done) — read-path vertex cap (`utils/zones.py:178`) untested** (write path is well tested).
  Add malformed-feature cases: not-an-object, properties-not-a-dict, non-int/str priority type,
  geometry that raises from `shape()` (`utils/zones.py:90,93,104,118-119`).
- **✅ P1 (done) — consent gate has no blocking UI test.** Playwright spec only checks discoverability
  and is `continue-on-error: true` on PRs (`.github/workflows/playwright.yml:32`); it never
  fills the form or ticks consent. Drive the form (or a real-`hass` config-flow test).
- **⏭️ P2 (declined — churn, low value) —** `test_final_coverage.py`/`test_full_coverage.py` are organised by "push coverage over
  N%" not by behaviour — rename to behaviour-named files. `test_cross_repo_conformance.py` is a
  manually-synced snapshot of the add-on output, not a live contract — will drift silently.

## Docs (technical-writer) — full punch-list, ready-to-apply wording captured

- **✅ P1 (done) —** stale `reload_zones` instruction (`README.md:143-145`) — see consensus above.
- **✅ P2 (done, PR #45) —** README "Known limitations" (`README.md:234-244`) omits the 500-feature and
  10,000-vertex caps that `utils/limits.py:11-15` enforces and `docs/ZONES_FORMAT.md:77-89`
  already documents. Add two bullets.
- **✅ P2 (done, PR #45) — ELI5 glosses missing on direct-landing pages:** SSRF unglossed in
  `docs/troubleshooting.md:38` and `docs/install.md:98`; "RFC-1918" unglossed in
  `docs/troubleshooting.md:42`; "event loop / sync compute library" jargon-dumped in
  `README.md:244`; GDPR Art. 46 unglossed in `docs/privacy.md:86`.
- **⏭️ P2 (declined — "≥98%" is an accurate floor claim) —** coverage badge says "≥98%" (`README.md:5`); actual 99% — floor claim is _not wrong_,
  optional to sharpen.
- **✅ Flag (resolved, PR #45)** — `strings.json` error keys `no_entities` and
  `download_or_no_zones` were dead; PR #45 (commit `b1b0397`) deleted both outright. No decision
  remains.

## Product (product-manager)

- **✅ P0 (DONE — PR #41)** — onboarding LAN/SSRF sequencing (see consensus above).
- **✅ P1 (done) —** config-flow inline hint when a private-range host is pasted with `allow_private_urls`
  off — name the specific toggle in the banner rather than a generic `invalid_url`.
- **ℹ️ P2 (release-notes guidance, not a repo change) —** next release notes: call out that mutation services need `download_zones` enabled
  first (off-by-default for reconfigured legacy entries → one-time `ZoneFileNotEditable`).
- Confirmed well-served: privacy-admin persona (hard consent gate, coords-off default,
  recorder-exclusion docs) and contributor persona (strong CONTRIBUTING.md, honest EN-only i18n).

---

## Conflicts surfaced (decide, don't average)

1. **Test vs. delete `async_update_config` (lines 280-281).** qa-lead wants the escalation
   branch there tested; sre-reliability + chief-architect say the method is **dead code** (never
   wired — options change triggers a full `async_reload`). → Resolve the dead-code question
   first: if deleting, don't add a test for it; the uncovered lines vanish with the method.
2. **Diagnostics redaction: "correct" vs. "leaks URI."** dpo verified coordinate + `uri`-field
   redaction is complete; security-reviewer found the `err` _string_ carries the URI as a second
   channel. Not contradictory — both are right about different fields. Fix the err-string channel.

## Not reviewed / out of scope tonight

- No live Docker/container boot performed (read-only audit; per your container-verify rule, do
  that before merging any fix PR that touches runtime code).
- Dual codex reconciliation not run — the tree is clean with no diff; reconcile against codex on
  each fix PR's diff per the standing dual-review rule.
- lead-frontend / product-designer (no UI surface beyond the config flow), data-engineer,
  cto/head-of-dev (no delivery/commercial question this cycle) — not engaged.

## Dependency housekeeping (separate from the panel) — ✅ RESOLVED, PR #44

The 6 Dependabot PRs open since 2026-07-04 (#38 HA test-floor bump `>=2026.7.1,<2027` + #33-37,
5 GitHub Actions SHA bumps: setup-node, upload-artifact, hassfest, attest-build-provenance,
ruff-action) were consolidated into PR #44, which also raised the `manifest.json` shapely floor
to match. Zero Dependabot PRs open as of this writing (re-verified via `gh pr list`).
