---
layout: page
title: Privacy
nav_order: 4
permalink: /privacy/
---

# Privacy and data handling

This page covers what data the integration and add-on process, where it goes, and what you can do to limit retention. It is written for people running this at home, not as a legal compliance document.

---

## Integration: what it processes

The integration continuously monitors the GPS position of every `device_tracker` entity you select during setup. That includes real-time latitude, longitude, and GPS accuracy from each tracked device.

**Everything runs locally inside your Home Assistant instance.** The integration itself does not send any data to third parties, analytics services, or the project maintainers.

### What is stored and where

| Data                              | Where it goes                                                                                                              |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Resolved zone name                | Entity state (`device_tracker.polygonal_zones_<name>`)                                                                     |
| Latitude, longitude, GPS accuracy | Entity attributes — only if **Expose GPS coordinates** is enabled                                                          |
| Zone history                      | Home Assistant's recorder database (HA's `home-assistant_v2.db`)                                                           |
| Downloaded zone file              | `<config>/polygonal_zones/<entry_id>.json` (mode 0600, directory 0700) — only if **Download the GeoJSON files** is enabled |
| GPS coordinates in logs           | Only at `DEBUG` log level — never written at default (`INFO`) level                                                        |

### Expose GPS coordinates

This option controls whether latitude, longitude, and GPS accuracy are written to entity attributes on each update.

- **New installs** default this to **off** — only the zone name is published.
- **Existing installs** that were created before this option was added keep their old default of **on**, for backwards compatibility. If you upgraded from an earlier version, check your setting under **Settings → Devices & Services → Polygonal Zones → ⋮ → Reconfigure**.

When `Expose GPS coordinates` is **on**, Home Assistant's recorder accumulates a full location history for every tracked person in its SQLite database (including backups). To disable coordinate exposure, re-open the integration (⋮ → Reconfigure) and un-tick the option.

### Recorder history

Even with coordinates off, the recorder logs state-change timestamps (when a person enters or leaves a zone) unless you explicitly exclude the entities. To stop the recorder from accumulating any history for the mirror entities, add this to your `configuration.yaml`:

```yaml
recorder:
  exclude:
    entity_globs:
      - device_tracker.polygonal_zones_*
```

Restart Home Assistant after adding it.

### Tracking other people

Any person whose `device_tracker` entity you select will have their location continuously monitored. If that includes people other than yourself — household members, children — please make sure they are aware and have agreed to it before you add their device. The setup form makes this explicit: it requires you to tick a confirmation ("everyone whose device I'm adding has been told it will be location-tracked") before it will continue. Don't tick it until that's actually true.

### Outbound requests

When `zone_urls` points at an `http(s)://` URL, the integration fetches it from your HA instance. The server hosting the GeoJSON file will see your HA instance's outbound IP address. Private, loopback, and link-local addresses are blocked by default to prevent SSRF; enabling **Allow private-network URLs (LAN)** relaxes this only for RFC-1918 space.

### Logging

GPS coordinates and zone names are only logged at `DEBUG` level. At default log settings they are never written to the HA log. `WARNING`-level log lines (raised when a zone file can't be fetched) include the source `entity_id` (e.g. `device_tracker.alice_phone`) — if you forward HA logs to an external aggregator, consider redacting those lines.

---

## Add-on: map tiles and zone file

### Third-party map tiles

The add-on's map editor loads map tiles from third-party servers. Depending on which tile layer is active, that may include:

- **OpenStreetMap** (operated by the OpenStreetMap Foundation)
- **CARTO** (operated by Carto, Inc.)
- **Esri** (operated by Esri)

Each tile request reveals your approximate map viewport (lat/lon bounding box) and your IP address to the tile provider. No zone geometry is sent — only the map viewport you're looking at. If you're zoomed in on a precise home address while drawing zones, the tile provider can infer that area of interest from the viewport.

This is the same data exposure as any web map (Google Maps, Apple Maps, etc.). The tile providers operate under their own privacy policies.

### zones.json is location PII

Your `zones.json` file contains the precise polygon coordinates of every place you've drawn — your home boundary, workplace, school run, and so on. Treat it accordingly:

- **HA backups and snapshots include it.** The zones file lives in `/data` inside the add-on container, which is captured in every HA backup. Deleting a zone from the editor does not remove it from snapshots taken before the deletion. If you need to fully remove a zone for privacy reasons, also delete the old backups that contain it (**Settings → System → Backups → ⋮ → Remove**).
- **Do not host zones.json on a public URL.** See the [DOCS.md](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/blob/main/polygonal_zones_editor/DOCS.md) section "Last resort — public-CDN mirror" for the full explanation of why this is a privacy risk.
- **Cloud backups.** If you use Nabu Casa cloud backup and the recorder database is included (the default), the location history of every tracked person is transferred to Nabu Casa's US-hosted infrastructure. Under GDPR Art. 46 (the rules for sending personal data outside the UK/EU), this is a cross-border transfer of personal data. Either apply the `recorder` exclude block above before enabling cloud backup, or review Nabu Casa's data-processing terms.

---

## Responding to a deletion request

If a tracked person asks for their location data to be removed:

1. **Remove the entity from the integration.** Settings → Devices & Services → Polygonal Zones → ⋮ → Reconfigure → untick their entity → Save. The mirror entity is deleted automatically.
2. **Purge recorder history.** Developer Tools → Actions → `recorder.purge_entities`:
   ```yaml
   entity_id:
     - device_tracker.polygonal_zones_<original>
     - device_tracker.<original>
   ```
   With `keep_days: 0` (the default), this removes all past state rows immediately.
3. **Delete any downloaded zone file.** If **Download the GeoJSON files** was enabled for this entry, remove `<config>/polygonal_zones/<entry_id>.json`.
4. **Rotate backups.** Any HA backup taken before these steps still contains the history. Delete old backups if full erasure is required, or rely on the backup's own retention expiry.
