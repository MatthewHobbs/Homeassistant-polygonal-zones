# Backlog

## `claude-review` fails on every Dependabot PR (2026-09-05) — RESOLVED 2026-09-05

Surfaced while draining a nine-PR Dependabot queue: `claude-review` failed on all six integration
PRs. Not a required check (`Pytest`, `Pytest (HA floor)`, `Hassfest`, `HACS`, `Ruff`, `Prettier`,
`Mypy` are), so nothing was ever blocked — which is precisely why it went unnoticed.

Cause, from the run log:

```
##[group]GITHUB_TOKEN Permissions
Secret source: Dependabot
...
  "claude_code_oauth_token": "",
  ANTHROPIC_API_KEY:
```

Dependabot PRs execute against Dependabot's **own** secret store, not the repository's Actions
secrets, so `secrets.CLAUDE_CODE_OAUTH_TOKEN` resolves to an empty string and the action cannot
authenticate. GitHub behaviour, not a defect in the workflow — and unfixable by granting
permissions, since the secret genuinely is not present in that context.

**Why it was worth fixing anyway:** a check that is red on every dependency PR forever is worse
than no check. It trains you to skim past red, which is exactly the habit that lets a real failure
through.

**Fixed:** `if: github.actor != 'dependabot[bot]'` on the job, so it skips rather than fails.
Reviewing a dependency bump was never what this workflow was for.

---

## Release-only action bumps are unverified by any PR check (2026-09-05) — OPEN, P2

`actions/attest-build-provenance` was bumped 4.1.1 → 4.2.2 (#67) and `softprops/action-gh-release`
3.0.2 → 3.0.3 (#71). Both are used **only** in `release.yml`, which triggers on `v*` tags. No pull
request check exercises either one, so those PRs going green said nothing whatsoever about whether
the release path still works.

The same pattern is worse in the companion add-on repo, where the equivalent bump was **v3 → v4.2.2
— a major** — on the action that produces the Sigstore provenance that `config.yaml` documents as
the image-integrity mechanism (`gh attestation verify`).

**Nothing is known to be broken.** This is a visibility gap, not a defect: the first execution of
this code path will be a real release, where a failure is most expensive and least convenient.

**Mitigation available now:** `release.yml` accepts `workflow_dispatch`, so the path can be
exercised deliberately before the next real tag rather than discovered during one.

**Worth considering longer-term:** a scheduled or manual smoke job that runs the release workflow's
attestation step against a throwaway artifact, so provenance tooling is covered by something other
than production releases.

---

## `gps_accuracy: 0` can never match any zone (2026-09-05) — OPEN, P0

`utils/zones.py:301` inflates the fix by the accuracy radius before testing containment:

```python
gps_point = Point(lon, lat)
buffer = gps_point.buffer(acc / 111320)
possible = [z for z in zones if buffer.intersects(z.geometry)]
```

Shapely returns an **empty polygon** for `Point.buffer(0)`, and an empty geometry intersects
nothing. So a tracker reporting `gps_accuracy: 0` falls out at `if not possible: return None`
and reads `away` regardless of where it actually is.

**Reproduced against live data** (shapely 2.1.2, the real `The Poplars` polygon, the real fix):

```
polygon contains the A290 point : True
  acc=0   buffer.is_empty=True   intersects(zone)=False
  acc=1   buffer.is_empty=False  intersects(zone)=True
  acc=5   buffer.is_empty=False  intersects(zone)=True
```

`contains()` says the point is inside; the buffered intersect says it is not. The point sits
**7.3 m inside** the boundary, so this is not a near-edge tolerance question — no distance would
help. Reported accuracy of `0` is common: the Renault/Kamereon feed behind
`device_tracker.mm75dxb_location` publishes exactly that, and it is the natural encoding for
"source does not report an accuracy figure". The failure is silent — `last_load_result` stays
`ok`, the debug line just reads `new zone: None`.

**Fix:** use the bare point when there is nothing to inflate by —
`buffer = gps_point.buffer(acc / 111320) if acc > 0 else gps_point`. Guard `acc < 0` the same way.

**Also worth deciding, separately:** `acc = 0` and `acc = None`/absent are currently
indistinguishable, but they mean different things — "perfectly accurate" versus "unknown". Treating
unknown as zero-inflation is defensible; treating it as _fail-closed_ (today's accidental behaviour)
is not. Whichever is chosen should be explicit and tested.

Owner: matt. Tests: a case per accuracy value `{0, None, negative, positive}`, asserting a point
known to be inside resolves to its zone in every case.

---

## `download_zones` defaults to true, silently freezing add-on-authored zones (2026-09-05) — OPEN, P1

`config_flow.py:49` documents the default as `True` for new installs ("CRUD works out of the box").
`device_tracker.py:105` then does:

```python
exists = await hass.async_add_executor_job(download_path.exists)
if not exists:
    await download_zones(...)
zone_uris = [f"/{relative}"]  # entities now read ONLY the local snapshot
```

The configured URL is therefore a **one-time seed**. It is re-fetched only if the snapshot file is
missing — never on reload, never on a config-entry reload, never on restart.

That is documented behaviour (`strings.json`: _"The entities will only use this single file to
retrieve the zones from"_), and it is the right model when the integration owns the data and edits
flow through `replace_all_zones`. It is the **wrong default when the source URL is the companion
add-on**, which is the pairing this project exists to support: the user draws a zone, saves it,
reloads, and nothing changes.

**Observed:** with 13 zones snapshotted, the source file was edited down to 4 (`Garage`/`Workshop`
merged to `Annex`, 8 indoor rooms deleted, boundary regrown 1,649 → 1,954 m²). After a config-entry
reload the debug line still read
`matched_zones: ['The Poplars', 'Home', 'Kitchen']` — two of those zones no longer existed — with a
`distance_to_centroid` byte-identical to the previous run. Setting `download_zones: false` fixed it
immediately: the same tracker went from `Home` (a deleted zone) to `The Poplars`.

**The real defect is that staleness is invisible.** `last_load_result` reads `ok`, because loading
the snapshot genuinely succeeded. Nothing anywhere says "this is a snapshot taken at _T_, not
tracking source".

**Fix, in preference order:** (1) default `download_zones` to `false` when a configured URI is a
local add-on host; (2) expose `zones_source: snapshot|live` and `snapshot_taken_at` as entity
attributes so the freeze is legible; (3) re-download on config-entry reload when the source is
reachable, treating the snapshot as a cache rather than a fork.

---

## Config flow cannot authenticate to a token-protected companion add-on (2026-09-05) — OPEN, P1

The add-on's `save_token` option gates **every** non-ingress request, `GET /zones.json` included
(see the add-on repo's backlog — its description claims `POST /save_zones` only). The integration's
config flow accepts `zone_urls` as bare URLs with no header field, and the add-on accepts the token
**only** as the `X-Save-Token` header.

Verified by hand against the running add-on:

```
header X-Save-Token:  200 (3805 bytes)
?token=…              401
?save_token=…         401
?X-Save-Token=…       401
?x_save_token=…       401
```

So the documented pairing is unreachable whenever the add-on is configured as its own docs
recommend ("pair with save_token whenever the port is exposed"). The only working combinations today
are _no token at all_, or _ingress-only_ — which the integration cannot use, since it runs in a
different container.

The user-visible symptom is a generic `ConfigEntryNotReady` with a 401, giving no hint that the
config flow structurally cannot supply the credential.

**Fix:** either an optional per-URL header/token field in the config and options flows, or — better,
since it removes the secret from HA's config entirely — have the add-on scope `save_token` to
mutating methods only, so reads work unauthenticated on an already IP-restricted port. These are
alternatives, not both; the second is cheaper and is the add-on's stated intent.

---

## `location_name` override is deprecated — hard removal in HA 2027.7 (2026-09-05) — OPEN, P2

Logged on every setup by HA itself:

```
WARNING [homeassistant.components.device_tracker.entity]
custom_components.polygonal_zones.device_tracker::PolygonalZoneEntity is overriding the
deprecated location_name property on an instance of TrackerEntity, this will be unsupported
from Home Assistant 2027.7, please report it to the custom integration author
```

A dated, hard breakage with ~10 months of runway, and HA is asking the author to act. Worth taking
while the surrounding code is being touched for the P0 above rather than as a separate scramble
nearer the deadline.

Owner: matt. Next step: confirm the supported replacement for a zone-name-bearing tracker on
2026.9+ before changing anything — the migration path matters more than the warning.

---

## Playwright config-flow smoke fails on HA 2026.7.4 (2026-07-27) — OPEN, P1

Surfaced merging Dependabot PR #60 (`homeassistant` floor `>=2026.7.1` → `>=2026.7.4`, now merged).
`Config flow (Playwright)` failed twice (initial + 1 retry): `Polygonal Zones` never became visible
in the Add Integration dialog within 30s. Not a required check — did not block the merge — but it's
a new, reproducible failure specific to this HA bump: the same check passed cleanly on the 5 other
PRs merged in this session (#54, #55, #56, #58, #59), all against HA 2026.7.1.

**What I found, and why I didn't guess a fix:** `ha.log` shows `homeassistant.setup` errors —
`Setup failed for 'radio_frequency': No module named 'rf_protocols'` and same for `'infrared'` /
`infrared_protocols` — two integrations new to HA core since 2026.7.1 (confirmed via
`home-assistant/core` manifests: `rf-protocols==4.3.0`, `infrared-protocols==8.2.0`). This matches
the _class_ of problem `playwright.yml`'s own comments document for `hassio`/`aiohasupervisor` (a
transitive dependency missing from the harness's pre-install allowlist) — but neither
`radio_frequency` nor `infrared` has a `services.yaml`, so they aren't part of the `get_services`
import sweep that comment describes, meaning that's not confirmed as the actual mechanism connecting
these setup errors to the dialog timeout. The `[setup] boot HA, onboard, and persist auth` sub-test
passed in 364ms on the same instance, so HA's frontend/auth are functioning — the failure is
specific to the integration-search step. Root cause is plausible but not confirmed; guessing a fix
(e.g. adding `radio_frequency`/`infrared` to the pre-install `comps` list) risks masking a real
config-flow regression instead of fixing it.

Owner: matt. Next step: re-run `Config flow (Playwright)` against current `main` (now on HA
2026.7.4) via `workflow_dispatch` and inspect the Playwright trace/screenshot artifact (uploaded on
every run, 7-day retention) to see what the Add Integration dialog actually rendered — that will
disambiguate "new components pollute discovery" from "unrelated regression" before touching the
harness or the integration code.

---

## CI cost / GitHub Actions minutes (2026-07-27) — RESOLVED 2026-07-27

From an account-wide GitHub Actions cost review. Original claim: this repo is the personal
account's #1 Actions cost driver — July = $36.59 net ($70.01 gross, ~11.7k `Actions Linux`
minutes), climbing May→Jun→Jul.

**Visibility check — done, via real billing data, not a guess.** Pulled
`gh api /users/.../settings/billing/usage`: May ($6.37 gross) and June ($24.43 gross) for this repo
were **100% discounted** (net $0) — consistent with the repo being public those months. July was
only **~48% discounted** ($33.52 of $70.31), netting **$36.79 charged**. The repo reads `public` now
(confirmed via `gh repo view`). Best-evidence read: the repo was private for part of July and has
since flipped public — real money was spent, this wasn't a false alarm, and going forward it should
self-correct. Exact flip timestamp isn't recoverable (no audit-log API access for a personal
account) — if a similar charge reappears next billing cycle, check visibility again before assuming
the CI fixes below are insufficient.

**Panel review (sre-reliability, security-reviewer, test-lead) before implementing** — two of the
four original items didn't survive scrutiny, one item's exact mechanism was corrected before
shipping:

- **CORRECTED, not implemented — "redundant push + pull_request double-runs."** The premise was
  stale: `validate.yml`/`multi-arch.yml` were **already** `push: branches: [main]`, not unscoped —
  the "scope it" fix was already satisfied. The other suggested fix ("drop `push:`") would have been
  **actively dangerous**: `release.yml` gates every release on a successful `validate.yml` run
  against the exact post-squash-merge SHA on `main`; dropping `push:` would leave that SHA with zero
  Validate runs and hard-fail every future release. `push` (main-only) and `pull_request` fire on
  _different_ SHAs (PR head vs. squash commit) — not a same-SHA double-run, by design. No code
  change; do not revisit without re-checking the release-gate dependency.
- **DOWNGRADED to informational, not implemented — "three daily schedule crons."** All three crons
  call the shared `_upstream-gate.yml`, which is one cheap PyPI-version-check job; the heavy jobs
  only run if upstream actually moved (cache-gated). Real daily cost is ~3 lightweight jobs, not 3
  full suites — this wasn't a meaningful driver of the July bill. Kept daily: detection-latency for
  upstream HA/shapely breaks matters more than the near-zero savings from going weekly.
- **IMPLEMENTED — `concurrency: cancel-in-progress`.** Added to `validate.yml`, `multi-arch.yml`,
  `playwright.yml`: `group: ${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}`,
  `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`. Group key includes the workflow
  name (concurrency groups are repo-global, not workflow-scoped — a bare `ref` key would collide
  across these three workflows) and cancellation is scoped to PR events only, so it can never cancel
  the `push`-to-`main` run `release.yml` depends on, or a nightly cron run.
- **PARTIALLY IMPLEMENTED — multi-arch QEMU on every PR/push.** Dropped the "buildx layer cache"
  suggestion — `multi-arch.yml` has no `docker build`/buildx step to cache (confirmed: it's
  `docker run --platform=X python:3.14-slim pip install shapely`, per the file's own header
  comment). Implemented a narrower fix than "arch on PR, multi-arch only on release/tag": amd64
  (native, cheap) still runs on every PR/push; the QEMU-emulated arm64 leg is skipped on PR/push
  _unless_ the diff touches `manifest.json`, `requirements_test.txt`, or the workflow file itself —
  full matrix always runs on `schedule`/`workflow_dispatch`. Chosen over a blanket skip because HA's
  install base skews Raspberry Pi/ARM; a shapely-bump PR still gets pre-merge arm64 coverage.
- **Rejected alternative (record, unchanged):** a self-hosted runner on `nuc-02` to dodge the bill
  was considered and rejected — public repo + self-hosted runner = fork-PR RCE from any contributor.

Owner: matt. Verified: `actionlint` + `prettier@3` clean on all touched workflow files.

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
