# ADR 0001: Bootstrap the zone snapshot in `__init__`, before the forward

- **Repo:** Homeassistant-polygonal-zones
- **Status:** Accepted (2026-09-24)
- **Context:** Issue #84: a failed first zone download left the config entry `LOADED` with no entities, no retry and no error.
- **North star:** A zone source that cannot be fetched at setup shows its real error, and Home Assistant retries it.

## Decision

I am moving the first-snapshot download out of `device_tracker.async_setup_entry` and into `__init__.async_setup_entry`, before `async_forward_entry_setups`, as `_async_bootstrap_zone_snapshot`. It raises `ConfigEntryNotReady` for a transient failure (unreachable source, SSRF block, corrupt payload) and `ConfigEntryError` for a permanent one (`UnsupportedSchemaVersion`). `device_tracker` no longer downloads anything; with `download_zones` set it only points `zone_uris` at the bootstrapped local snapshot.

| #   | Step                                                          | Owner | Status | Evidence |
| --- | ------------------------------------------------------------- | ----- | ------ | -------- |
| 1   | Move the bootstrap into `__init__`, ahead of the forward      | matt  | Done   | v1.14.2  |
| 2   | A real-Home-Assistant test that the entry shows `SETUP_RETRY` | matt  | Open   |          |

Status is one of **Open**, **Done**, **Blocked**, **Dropped**.

## Context

Home Assistant catches `ConfigEntryNotReady` and `ConfigEntryError` raised from a _forwarded_ platform, logs "raises exception ... in forwarded platform" without the error text, and returns `False`. `config_entries.async_setup` does not store that result, so `__init__.async_setup_entry` still returned `True`. Home Assistant only retries with backoff (5 s doubling to 600 s, state `SETUP_RETRY`, with the message) when the integration's own `async_setup_entry` raises. The options not chosen are in the RFC.

## Consequences

**Accepted**

- A permanent failure (`UnsupportedSchemaVersion`) raises `ConfigEntryError`, not `ConfigEntryNotReady`: retrying it would spin every ten minutes for ever.
- About 35 lines move, with the tests that cover them.

**Watch**

- Why the original reporter's download failed is still unknown; it stays open on #84 pending their debug log.

## Verification (2026-09-24)

- `tests/test_init.py` runs with an `AsyncMock` forward and proves the call order: the download is attempted and the forward is never awaited on failure. It could have failed had the forward run first.
- Not checked: that Home Assistant actually shows `SETUP_RETRY`. That needs the real-hass harness, which now exists in `tests_hass/`, so it is step 2.

## References

- Issue #84
