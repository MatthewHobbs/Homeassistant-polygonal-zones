# ADR 0003: A last-reported sensor for silent trackers (Option B)

- Status: Accepted
- Date: 2026-10-20
- RFC: [RFC 0001 — Detecting and refreshing stale trackers](https://claude.ai/code/artifact/945903cd-0c3a-47ca-b594-fe8c78855664) (`docs/rfc/README.md`)

## Context

Issue [#110](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues/110)
asks for the integration to request a location update from a tracker that has
been silent for N seconds. A stationary phone reports rarely (iOS especially,
where significant-change updates can be hours apart), so a silent tracker looks
the same as a healthy one. The reporter runs an automation that calls the
Companion app's `request_location_update` command.

The Home Assistant Companion docs call that command "hit or miss" on iOS, say it
only works while the app is running, and advise against calling it on a
schedule for battery reasons. It works only for Companion-app trackers, while
this integration mirrors any `device_tracker`.

## Decision

Option B: expose staleness, do not build the ping.

Each tracked entity gets a `sensor.polygonal_zones_<name>_last_reported`
diagnostic sensor, **disabled by default**, and the README documents a template
trigger that turns it into a staleness automation, including the
`request_location_update` call for users who want it.

Owner's decision, verbatim: "B and it should be disabled by default".

Refined from the RFC while implementing: the sensor is a **timestamp** (the
source's `last_reported`), not a ticking "seconds since" duration. A duration
needs a once-a-minute write per device for no information the timestamp lacks;
the timestamp writes only when the tracker reports, and `now() - states(...)`
gives the duration where it is wanted.

## Alternatives

From RFC 0001:

| Option                                | What changes                                            | Why not                                                                                                                                                        |
| ------------------------------------- | ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A. Document only                      | A recipe, no entity                                     | Nothing in the integration says a tracker is stale; the reporter keeps maintaining the helper state                                                            |
| **B. Sensor + recipe (chosen)**       | Per-device diagnostic timestamp sensor, disabled        | n/a                                                                                                                                                            |
| C. Built-in active ping               | Config option; the integration calls the notify service | Battery drain the Companion docs discourage; hit or miss on iOS; Companion-app sources only; needs a device-to-notify-service mapping; privacy page to revisit |
| D. A `request_location_update` action | The integration resolves a mirror to its notify service | Carries C's mapping cost for a small gain over the user's existing `notify` call; revisit if users ask for it after B ships                                    |

## Consequences

- The sensor follows both `state_changed` and `state_reported`. A phone that
  re-reports an unchanged position fires only `state_reported`, and listening to
  `state_changed` alone would call it stale. A real-hass test covers it, and
  fails if the `state_reported` listener is removed.
- The sensor ignores `unavailable` and `unknown` source states, which Home
  Assistant stamps with a fresh `last_reported`; those are the silence the
  sensor exists to expose. If the source entity is gone it keeps the last value.
- After a Home Assistant restart the value is the source state's restored
  `last_reported`, not the tracker's true last report. A tracker that was already
  silent looks freshly reported until it next reports or the window passes.
- Resolution is one second: Home Assistant renders timestamp states without
  microseconds.
- One more entity per tracked device, off unless the user enables it.
- Revisit option D only on demand after this ships.
