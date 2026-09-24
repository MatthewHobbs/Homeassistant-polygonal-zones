# ADR 0001: Bootstrap the zone snapshot in `__init__`, before the forward

- Status: Accepted
- Date: 2026-09-24
- RFC: [polygonal-zones integration setup retry (#84)](https://claude.ai/code/artifact/0857e19c-9710-4c8d-aecd-b9b5929d8012) (draft, unnumbered/unindexed — see Data class below)

## Context

`device_tracker.async_setup_entry` (a platform forwarded from
`__init__.async_setup_entry`) downloaded the first zone snapshot itself, and
raised `ConfigEntryNotReady` or `ConfigEntryError` on failure. Home
Assistant's `entity_platform.async_setup_platform` catches both from a
_forwarded_ platform, logs "raises exception ConfigEntryNotReady in forwarded
platform ..." (without the underlying error text) and returns `False`.
`config_entries.async_setup` does not store that per-platform result, so
`__init__.async_setup_entry` still returned `True`: the config entry showed
`LOADED` with no entities, no retry, and no error banner (issue #84).

HA only retries with backoff (5s doubling to 600s, state `SETUP_RETRY` with
the message) when the integration's own `async_setup_entry` raises — not a
forwarded platform's.

## Decision

Move the first-snapshot bootstrap (the `download_zones` check-and-download
block, previously `device_tracker.py:100-135`) into
`__init__.async_setup_entry`, before `async_forward_entry_setups`, as a new
`_async_bootstrap_zone_snapshot` helper. It raises `ConfigEntryNotReady` for
a transient failure (unreachable source, SSRF block, corrupt payload) or
`ConfigEntryError` for a permanent one (`UnsupportedSchemaVersion`) — both now
from the integration's own `async_setup_entry`, so HA's own retry/backoff and
error banner apply. `device_tracker.async_setup_entry` no longer downloads
anything; when `download_zones` is set it just points `zone_uris` at the
already-bootstrapped local snapshot path.

This corresponds to Option A in the RFC.

## Alternatives

From the RFC:

| Option                                  | What changes                                                                                                                                                   | What the user sees                                                                                                                                | Cost                                                | Risk                                                                                      |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **A. Bootstrap in `__init__` (chosen)** | Move the first snapshot download (`device_tracker.py:100-135`) into `__init__.async_setup_entry`, before the forward; raise NotReady or ConfigEntryError there | Entry shows "Retrying setup" with the real error, and HA retries with backoff. A permanent error shows as failed                                  | About 35 lines move, plus the tests that cover them | Low. It is HA's documented pattern                                                        |
| B. Degrade inside the platform          | Platform never raises. Entities come up unavailable, with a repair issue                                                                                       | Entities exist but are unavailable. HA does not retry, so `ZoneSource` must learn to retry the first download itself                              | Highest: new retry logic and a repair flow          | Medium. Adds a second retry mechanism next to HA's                                        |
| C. `PlatformNotReady`                   | One line: raise `PlatformNotReady` instead                                                                                                                     | Platform retries every 30 to 180s and logs the message. The entry still reads LOADED with no entities. No equivalent exists for a permanent error | Smallest                                            | Medium. It hides failures behind a LOADED entry, and a corrupt local file retries forever |

Option A was chosen because it is the only one that gets both HA's retry and
the real error in front of the user, and it fixes the lost-error problem
(entity_platform never logs `str(exc)`) because the entry's own retry state
carries the message.

## Consequences

- A local-file parse failure (`UnsupportedSchemaVersion`) is permanent and
  raises `ConfigEntryError`, not `ConfigEntryNotReady` — retrying it with
  NotReady would spin every 10 minutes indefinitely.
- The regression test (`tests/test_init.py`) runs with `-p no:homeassistant`
  and an `AsyncMock` forward. It proves call order (the download is attempted
  and the forward is never awaited on failure), not that HA actually shows
  `SETUP_RETRY` — that needs `pytest-homeassistant-custom-component`'s `hass`
  fixture and `MockConfigEntry`, which this repo does not install. Adding
  that harness is a separate, larger change and is not part of this ADR.
- Not established by this change: why the original reporter's download
  failed. That remains open on #84 pending their debug log.

## Data class

This repo had no data class recorded yet at RFC draft time (ADR 0003 row 17
in `claude-config`), so the RFC was drafted unnumbered and unindexed,
treated as Restricted by default. It is a public GitHub repo with no
non-public personal data, so it classifies as **Public** ("content already
public") under the global data-class policy — recorded here as the
decision for this repo; the corresponding `claude-config` ADR 0003 row is a
separate, cross-repo edit and is not made from this session.
