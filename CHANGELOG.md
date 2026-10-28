# Changelog

## 1.16.2 — 2026-10-28

Automatic setup with the editor app stays correct when the app restarts or moves.

- **The app's password goes only to the app.** An entry set up by the app sends the
  password to the address the app announced, and to no other URL on that entry. A
  source you added yourself under **Reconfigure** never receives it.
- **A waiting discovery card is replaced, not left stale.** When the app starts
  again, any card still waiting is replaced by the new one, so confirming it uses the
  app's current address and password. A card you have open when this happens stops
  working: close it and open the new one.
- **Rediscovery changes only the app's address.** Extra URLs you added, your devices
  and your choices are kept. An entry made by 1.16.0 or 1.16.1 with a single URL keeps
  working until the app next starts.
- **One broken source no longer blocks the others.** `polygonal_zones.reload_all_zones`
  reloads every entry even when one fails. It reports an error only when the app's own
  entry could not be reloaded, so the editor's warning after a save is accurate. A
  failure in any other entry is written to the log.
- The app's address is hidden in diagnostics, like your other URLs.

## 1.16.1 — 2026-10-25

A documentation update, and the two corrections the writing of it turned up.

The install guide now leads with the automatic path: install the app, install this
integration, confirm the discovered entry, then pick your devices. The by-hand path
sits below it, under a heading that says it is only for what automatic setup cannot
cover. The guide also has a short section for using a zones file you already have,
and says plainly that the app needs a 64-bit installation.

Fixed:

- **Two entries reading the same editor are told apart.** New entries are titled
  after the editor they read, and an entry whose editor another entry also reads
  raises a repair issue naming that entry. Removing the duplicate clears the
  remaining entry's warning too.
- The documentation for a corrupt zones file now says what repairs it:
  `replace_all_zones`, which never reads the file it replaces.

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
