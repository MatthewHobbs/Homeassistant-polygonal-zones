# Changelog

## 1.16.0 — 2026-10-24

Automatic setup with the editor app, and a set of fixes found by testing.

- **Setting up is one confirmation.** With the editor app 0.7.0 or later installed,
  Home Assistant offers this integration as a discovered entry. Confirm it, then use
  the entry's **⋮ → Reconfigure** menu to choose your devices. There is no URL to
  type, no port to open and no token to copy.
- **Unavailable is now visible.** When a tracker stops reporting, or stops existing,
  the mirror entity reports `unavailable` instead of keeping its last zone name.
  Automations that treated that stale name as "still home" will see the change.
- **Edits are checked before they are written.** The zone actions now refuse a file
  Home Assistant cannot read: broken shapes, a `priority` that is not a whole number,
  more than 500 zones or more than 10,000 points in total. Zone names and ids must
  be unique.
- **A home zone can be given by name.** `home_zone_id` matches a zone's id first,
  then its exact name, as the documentation always said.
- **New action** `polygonal_zones.reload_all_zones`, for a producer that has no
  entity ids to target. The editor app calls it after each save.
- **Restored values follow the same rules as live ones.** Attributes rebuilt after
  a restart are redacted exactly as they are when first published.
- Positions update in the order they were received, and a null accuracy figure no
  longer stops a valid position from resolving.

**Notes for anyone automating this:** the mirror's `state` is still the zone name,
and the `location_name` property Home Assistant reads it from is removed in 2027.7.
Read the zone name from `sensor.polygonal_zones_*` instead; that sensor already
exists and reports the same value.
