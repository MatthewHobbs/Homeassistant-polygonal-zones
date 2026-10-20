# ADR 0003: A last-reported sensor for silent trackers

- **Repo:** Homeassistant-polygonal-zones
- **Status:** Accepted (2026-10-20)
- **Context:** [#110](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues/110) asks for a location update to be requested from a tracker that has gone quiet; RFC 0001 weighed four ways to answer it.
- **North star:** A user can see from Home Assistant when a tracker has gone silent, and the integration never decides what to do about it.

## Decision

I am exposing staleness and not building the ping. Each tracked entity gets a `sensor.polygonal_zones_<name>_last_reported` diagnostic sensor, disabled by default, holding the time the source tracker last reported. The README shows a template trigger that turns it into a staleness automation, including the Companion `request_location_update` call for anyone who wants it. It is a timestamp and not a ticking "seconds since" value: that would need a write per device every minute, and `now() - states(...)` gives the duration where it is wanted.

| #   | Step                                                                          | Owner | Status | Evidence |
| --- | ----------------------------------------------------------------------------- | ----- | ------ | -------- |
| 1   | The sensor: timestamp, diagnostic, disabled by default, restored              | matt  | Done   | #118     |
| 2   | README recipe and enable steps; `privacy.md` covers the per-report history    | matt  | Done   | #118     |
| 3   | A `request_location_update` action, only if users ask for it after this ships | matt  | Open   |          |

Status is one of **Open**, **Done**, **Blocked**, **Dropped**.

## Context

A stationary phone reports rarely, iOS especially, so a silent tracker looks like a healthy one. The Companion docs call `request_location_update` "hit or miss" on iOS, say it only works while the app is running, and advise against a schedule because of battery use. It works only for Companion-app trackers, and this integration mirrors any `device_tracker`. I chose the sensor-plus-recipe option, disabled by default. The other options are in the RFC.

## Consequences

**Accepted**

- The sensor follows both `state_changed` and `state_reported`: a phone re-reporting an unchanged position fires only the latter. `unavailable` and `unknown` source states are ignored.
- The unique id comes from the config entry and tracked entity, not the generated entity id, so a setup retry cannot re-key it and drop the user's opt-in.
- While enabled, the recorder stores a row per report: an activity log per person. `docs/privacy.md` says so and shows how to exclude it.

**Watch**

- After a restart the sensor prefers its restored value, and a source's first write after a start or reload is not counted as a report. For any source that does not restore its state, and for a brand-new tracker, that first genuine report is ignored and the next one corrects it, which can raise one avoidable stale alert.
- Removing and re-adding a tracker, or disabling and re-enabling the sensor, within 7 days restores an old timestamp until the tracker next reports.

## Verification (2026-10-20)

- Removing the `state_reported` listener fails `test_unchanged_re_report_advances_the_timestamp`; advancing on `unavailable` fails `test_source_going_unavailable_keeps_the_last_timestamp`; deriving the unique id from the entity id or skipping restore fails their tests; counting a source's first post-restart write fails `test_sources_first_write_after_restart_does_not_overwrite_the_restore`.
- The README template is rendered against the real sensor in `test_readme_template_flips_after_ten_minutes_of_silence`.
- Not checked: behaviour on a real Companion-app device, or the real bootstrap order of a source integration against this one.

## References

- RFC 0001, `docs/rfc/README.md`
- [Companion notification commands](https://companion.home-assistant.io/docs/notifications/notification-commands/)
