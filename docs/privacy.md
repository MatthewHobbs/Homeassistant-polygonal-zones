---
layout: page
title: Privacy
nav_order: 4
permalink: /privacy/
---

# Privacy and data handling

What the integration and add-on process, where it goes, and how to limit retention. It is written for people running this at home, not as a compliance document.

---

## Integration: what it processes

The integration reads the latitude, longitude and GPS accuracy of every `device_tracker` entity you select, each time it reports.

Zone resolution runs inside Home Assistant. The integration's only network requests fetch your zone URLs; see [Outbound requests](#outbound-requests).

### What is stored and where

| Data                              | Where it goes                                                                                                                                                     |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Resolved zone name                | State of the mirror entity and of the zone sensor                                                                                                                 |
| Latitude, longitude, GPS accuracy | Mirror entity attributes, only if **Expose GPS coordinates** is on                                                                                                |
| Matched zones (`matched_zones`)   | Mirror and zone sensor attributes, only if **Expose GPS coordinates** is on                                                                                       |
| Zone source URLs (`zone_uris`)    | Mirror entity attribute, only if **Expose GPS coordinates** is on; credentials and query strings removed                                                          |
| Home-zone membership (`in_zones`) | Mirror entity attribute, whenever a **Home zone** is set, regardless of **Expose GPS coordinates**                                                                |
| Source tracker (`source_entity`)  | Mirror and sensor attributes, always. The mirror also publishes load status                                                                                       |
| Zone history                      | Home Assistant's recorder database (`home-assistant_v2.db`)                                                                                                       |
| Last-reported timestamp           | State of the last-reported sensor, which is off by default (see below)                                                                                            |
| Downloaded zone file              | `<config>/polygonal_zones/<entry_id>.json` (mode 0600, directory 0700), only if **Download the GeoJSON files** is on; not deleted when you remove the integration |
| Zone details in logs              | `DEBUG` level only: zone names, matched zones and distances. Coordinates are never logged                                                                         |
| Consent timestamp                 | Config entry (`consent_confirmed_at`)                                                                                                                             |

### Home zone (`in_zones`)

When a **Home zone** is set, the mirror entity's `in_zones` attribute lists `zone.home` while the device is inside that zone. It shows only home or not home, with no coordinates, so it is published regardless of **Expose GPS coordinates**. Leave **Home zone** blank to turn it off.

### Expose GPS coordinates

This option controls whether latitude, longitude, GPS accuracy, `matched_zones` and `zone_uris` are written to entity attributes.

- New installs: off. Only the zone name is published, plus the attributes that are always published (see the table).
- Entries created before the option existed: on, and Home Assistant shows a repair issue until you save the setting. Check it under **Settings → Devices & Services → Polygonal Zones → ⋮ → Reconfigure**.

While it is on, the recorder keeps a location history for every tracked device, in its database and in backups. To stop that, untick it under ⋮ → Reconfigure.

### Recorder history

Even with coordinates off, the recorder stores state changes, which show when a person enters or leaves a zone. To stop that for this integration's entities, add this to `configuration.yaml`:

```yaml
recorder:
  exclude:
    entity_globs:
      - device_tracker.polygonal_zones_*
      - sensor.polygonal_zones_*
```

Restart Home Assistant after adding it.

### Last-reported sensor

Each tracked device has an optional last-reported sensor that holds the time the tracker last reported, for spotting a silent device. It is disabled by default and carries no coordinates, so **Expose GPS coordinates** does not affect it. Its value changes on every report, so while it is enabled the recorder stores a row per report, which shows when each device checked in. Leave it disabled or exclude it as above to avoid that history.

### Tracking other people

Any person whose `device_tracker` you select is tracked continuously. If that includes other people, such as household members or children, make sure they know before you add their device. Setup will not continue until you tick a confirmation that everyone has been told; tick it only when that is true. The tick records that you told them; it does not collect their agreement. Adding a tracker later under Reconfigure asks again.

### Outbound requests

Fetching an `http(s)://` zone URL sends a request from your HA instance, so the host of that URL sees its outbound IP address. The **Add-on save token**, if set, is sent as the `X-Save-Token` header only to hosts that look like a LAN add-on (`localhost`, `.local` names and private, loopback or link-local IP addresses). Private, loopback and link-local addresses are blocked by default; **Allow private-network URLs (LAN)** allows private ranges only. Redirects are refused. The token is stored in the config entry, so it is in Home Assistant backups, and it travels over plain `http://` to a local add-on.

### Logging

`DEBUG` lines contain zone names, matched zones and distances; coordinates are never logged. `INFO` lines record the Home Assistant user id of whoever runs a zone-editing action, and the tracker entity id when a mirror becomes unavailable or recovers. `WARNING` lines about a failed zone fetch contain the zone URL without credentials and query string, the error type and the config entry id. Redact them if you forward logs to an external service.

Do not put a secret in a zone URL (`user:pass@`, `?token=` or a path segment); use the **Add-on save token** field instead. Credentials and query strings are removed from logs and published attributes, but path segments are kept as written. Before 1.15.1 the full URL, credentials included, was written to the log and to the `zone_uris` attribute, and so to the recorder history and backups. If a zone URL ever carried a secret, rotate it and treat old logs and history as sensitive.

---

## Add-on: map tiles and zone file

### Third-party map tiles

The add-on's map editor loads tiles from third-party servers, depending on the active layer: OpenStreetMap, CARTO or Esri. Each tile request shows the provider your IP address, your Home Assistant address as the referrer, and the map area you are viewing. No zone geometry is sent. The providers' own privacy policies apply.

### zones.json is location data

`zones.json` holds the exact polygons of every place you drew.

- HA backups include it (it lives in the add-on's `/data`). Deleting a zone in the editor does not remove it from earlier backups; delete those backups too (**Settings → System → Backups → ⋮ → Remove**).
- Do not host it at a public URL. See the add-on's [DOCS.md](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/blob/main/polygonal_zones_editor/DOCS.md), section "Last resort: a public-CDN mirror (privacy warning)".
- A cloud backup that includes the recorder database sends every tracked person's location history to the backup provider. Exclude the entities with the `recorder` block above, or check the provider's data-processing terms first.

---

## Responding to a deletion request

If a tracked person asks for their location data to be removed:

1. Remove the tracker from the integration: Settings → Devices & Services → Polygonal Zones → ⋮ → Reconfigure, untick it and save. Delete any of its entities that remain listed under Settings → Devices & Services → Entities (the mirror, the zone sensor and the last-reported sensor). Home Assistant keeps each entity's last value in `.storage/core.restore_state`, and so in backups, for up to 7 days after removal.
2. Purge recorder history with `recorder.purge_entities` (Developer Tools → Actions), listing the integration's entities for that tracker and the source tracker:
   ```yaml
   entity_id:
     - device_tracker.polygonal_zones_<name>
     - sensor.polygonal_zones_<name>
     - sensor.polygonal_zones_<name>_last_reported
     - <the source tracker, for example device_tracker.alice_phone>
   ```
   With `keep_days: 0` (the default) all past state rows are removed at once.
3. If **Download the GeoJSON files** was on, delete `<config>/polygonal_zones/<entry_id>.json`.
4. Delete or wait out any backup taken before these steps, since it still holds the history.
