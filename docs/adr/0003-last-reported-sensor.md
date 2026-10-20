# ADR 0003: A last-reported sensor for silent trackers

- **Repo:** Homeassistant-polygonal-zones
- **Status:** Accepted (2026-10-20)
- **Context:** [#110](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues/110) asks the integration to request a location update from a tracker that has gone quiet; [RFC 0001](https://claude.ai/code/artifact/945903cd-0c3a-47ca-b594-fe8c78855664) weighed four ways to answer it.
- **North star:** A user can see from Home Assistant when a tracker has gone silent, and the integration never decides what to do about it.

## Decision

I am exposing staleness and not building the ping. Each tracked entity gets a
`sensor.polygonal_zones_<name>_last_reported` diagnostic sensor, disabled by
default, holding the time the source tracker last reported. The README shows a
template trigger that turns it into a staleness automation, including the
Companion `request_location_update` call for anyone who wants it.

It is a timestamp and not a ticking "seconds since" value. A duration needs a
write per device every minute for nothing the timestamp lacks; the timestamp
writes only when the tracker reports, and `now() - states(...)` gives the
duration where it is wanted.

| #   | Step                                                                                        | Owner | Status | Evidence |
| --- | ------------------------------------------------------------------------------------------- | ----- | ------ | -------- |
| 1   | The sensor: timestamp, diagnostic, disabled by default, restored, follows both report kinds | matt  | Done   | #118     |
| 2   | README recipe and enable steps; `privacy.md` covers the per-report history                  | matt  | Done   | #118     |
| 3   | A `request_location_update` action, only if users ask for it after this ships               | matt  | Open   |          |

Status is one of **Open**, **Done**, **Blocked**, **Dropped**.

## Context

A stationary phone reports rarely, iOS especially, where significant-change
updates can be hours apart, so a silent tracker looks the same as a healthy
one. The reporter runs an automation that calls the Companion app's
`request_location_update` command.

That command is documented as "hit or miss" on iOS, works only while the app is
running, and is advised against on a schedule because of battery use. It works
only for Companion-app trackers, and this integration mirrors any
`device_tracker`. So the sensor works for every source, and the request stays
the user's choice. I chose B and that it be disabled by default. The options I
did not choose are in the RFC.

## Consequences

**Accepted**

- One more entity per tracked device, off unless the user enables it.
- The sensor follows both `state_changed` and `state_reported`. A phone that
  re-reports an unchanged position fires only `state_reported`, and listening to
  `state_changed` alone would call it stale.
- `unavailable` and `unknown` source states are ignored. Home Assistant stamps
  them with a fresh `last_reported`, but the tracker has not spoken.
- The unique id is built from the config entry and the tracked entity, not from
  the generated entity id. `generate_entity_id` can return a `_2` suffix on a
  setup retry, which would have created a new disabled entry and dropped the
  user's opt-in.
- Resolution is one second: Home Assistant renders timestamp states without
  microseconds.
- While enabled, the recorder stores a row per report, an activity log per
  person. `docs/privacy.md` says so and shows how to exclude it.

**Watch**

- After a restart the source's own `last_reported` is the restart time, so the
  sensor deliberately prefers its restored value, which is older and truer. A
  report made between start and the sensor being added is missed until the next
  one, which can raise one avoidable stale alert.

## Verification (2026-10-20)

- Removing the `state_reported` listener fails
  `test_unchanged_re_report_advances_the_timestamp`; a stubbed-hass test could
  not tell the two events apart, so this runs the real state machine.
- Advancing on `unavailable` fails
  `test_source_going_unavailable_keeps_the_last_timestamp`.
- Deriving the unique id from the entity id fails
  `test_unique_id_survives_a_taken_entity_id`; skipping restore fails
  `test_value_is_restored_when_the_source_is_unavailable`.
- The README template is rendered against the real sensor in
  `test_readme_template_flips_after_ten_minutes_of_silence`.
- Not checked: behaviour on a real Companion-app device, and the
  `Pytest (HA floor)` job's result is the evidence for the HA 2026.7.1 floor.

## References

- [RFC 0001](https://claude.ai/code/artifact/945903cd-0c3a-47ca-b594-fe8c78855664), `docs/rfc/README.md`
- [Companion notification commands](https://companion.home-assistant.io/docs/notifications/notification-commands/)
- [Companion location docs](https://companion.home-assistant.io/docs/core/location/)
