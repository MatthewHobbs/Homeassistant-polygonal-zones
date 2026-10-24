---
layout: page
title: Privacy
nav_order: 4
permalink: /privacy/
---

# Privacy and data handling

This page explains what the integration and the app handle, where that data goes, and how to keep less of it. It is written for people running this at home, not as a compliance document.

---

## Integration: what it handles

Each time a `device_tracker` you selected reports, the integration reads its latitude, longitude and GPS accuracy.

The zone calculation runs inside Home Assistant. The only network requests the integration makes fetch your zone addresses. See [Outbound requests](#outbound-requests).

### What is stored and where

| Data                              | Where it goes                                                                                                                                                                 |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Zone name                         | The state of the mirror entity and of the zone sensor                                                                                                                         |
| Latitude, longitude, accuracy     | Attributes of the mirror entity, only when **Expose GPS coordinates** is on                                                                                                   |
| Matched zones (`matched_zones`)   | Attributes of the mirror and the zone sensor, only when **Expose GPS coordinates** is on                                                                                      |
| Zone addresses (`zone_uris`)      | Attribute of the mirror entity, only when **Expose GPS coordinates** is on. Logins and query strings are removed                                                              |
| Home-zone membership (`in_zones`) | Attribute of the mirror entity, whenever a **Home zone** is set, whether or not **Expose GPS coordinates** is on                                                              |
| Source tracker (`source_entity`)  | Attributes of the mirror and the sensor, always. The mirror also reports its load status                                                                                      |
| Zone history                      | Home Assistant's recorder database, `home-assistant_v2.db`                                                                                                                    |
| Last-reported time                | State of the last-reported sensor, which is off by default (see below)                                                                                                        |
| Downloaded zone file              | `<config>/polygonal_zones/<entry_id>.json`, mode 0600 in a folder with mode 0700, only when **Download the GeoJSON files** is on. Removing the integration does not delete it |
| Zone details in logs              | `DEBUG` level only: zone names, matched zones and distances. Coordinates are never logged                                                                                     |
| Consent time                      | The config entry, as `consent_confirmed_at`                                                                                                                                   |

### Home zone (`in_zones`)

When a **Home zone** is set, the mirror entity's `in_zones` attribute lists `zone.home` while the device is inside that zone. It says home or not home and nothing else, with no coordinates. That is why it is published even when **Expose GPS coordinates** is off. Leave **Home zone** blank to turn this off.

### Expose GPS coordinates

This option decides whether latitude, longitude, GPS accuracy, `matched_zones` and `zone_uris` are written to entity attributes. An attribute is a named value that Home Assistant keeps next to an entity.

- New installs: off. Only the zone name is published, plus the values that are always published.
- Entries made before this option existed: on. Home Assistant shows a repair issue until you save the setting. Change it under **Settings → Devices & services → Polygonal Zones → ⋮ → Configure**.

While it is on, Home Assistant's recorder keeps a location history for every tracked device, in its database and in your backups. Untick it under **⋮ → Configure** to stop that.

### Recorder history

The recorder is the part of Home Assistant that stores past states. Even with coordinates off, it keeps state changes, which show when a person comes or goes. To stop that for these entities, add this to `configuration.yaml`:

```yaml
recorder:
  exclude:
    entity_globs:
      - device_tracker.polygonal_zones_*
      - sensor.polygonal_zones_*
```

Restart Home Assistant after adding it.

### Last-reported sensor

Each tracked device can have a last-reported sensor. It holds the time the tracker last reported, which helps you spot a device that has gone quiet. It is off by default and holds no coordinates, so **Expose GPS coordinates** does not affect it.

Its value changes on every report. While it is on, the recorder stores a row for each report, which shows when each device checked in. Leave it off, or exclude it as above, to avoid that history.

### Tracking other people

Any person whose `device_tracker` you select is followed continuously. If that includes someone else, such as a household member or a child, make sure they know before you add their device. Setup will not continue until you confirm that everyone has been told. Tick it only when that is true.

The tick records that you told them. It does not record their agreement. Adding a tracker later under **Reconfigure** asks again.

### Outbound requests

When the integration fetches an `http(s)://` zone address, the request comes from your Home Assistant machine, so that host sees your public IP address.

If **App save token** is set, it is sent as the `X-Save-Token` header only to hosts that look like the app on your own network: `localhost`, `.local` names, and private, loopback or link-local addresses. The token is also sent to the address an entry received from app discovery.

Private, loopback and link-local addresses are blocked by default. **Allow private-network URLs (LAN)** allows private ranges only. Redirects are refused. The token is stored in the config entry, so it is in Home Assistant backups, and it travels unencrypted over `http://` to a local app.

### Logging

- `DEBUG` lines contain zone names, matched zones and distances. Coordinates are never logged.
- `INFO` lines record the Home Assistant user id of whoever runs a zone-editing action, and the tracker entity id when a mirror becomes unavailable or recovers.
- `WARNING` lines about a failed zone fetch contain the zone address without logins or query strings, the error type and the config entry id.

Remove those details before you forward logs to another service.

Do not put a secret in a zone address, whether as `user:pass@`, as `?token=` or as part of the path. Use the **App save token** field instead. Logins and query strings are removed from logs and attributes, but path segments are kept as written.

Before 1.15.1, the whole address, logins included, went into the log and into the `zone_uris` attribute, and so into recorder history and backups. If an address ever carried a secret, change it, and treat old logs and history as sensitive.

---

## App: map tiles and zone file

### Third-party map tiles

The editor loads map tiles from third-party servers, depending on the layer: OpenStreetMap, CARTO or Esri. Each tile request shows that provider your IP address, your Home Assistant address as the referrer, and the area of the map you are viewing. No zone shape is sent. Each provider's own privacy policy applies.

### zones.json is location data

The file holds the exact outline of every place you drew.

- Home Assistant backups include it, because it lives in the app's `/data` folder. Deleting a zone in the editor does not remove it from earlier backups. Delete those backups too, under **Settings → System → Backups → ⋮ → Remove**.
- Do not host it at a public address. See the app's [DOCS.md](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/blob/main/polygonal_zones_editor/DOCS.md), section "Last resort: a public-CDN mirror (privacy warning)".
- A cloud backup that includes the recorder database sends every tracked person's location history to the backup provider. Either exclude the entities with the `recorder` block above, or read the provider's terms first.

---

## Responding to a deletion request

If a tracked person asks you to remove their location data:

1. Remove the tracker from the integration. Open **Settings → Devices & services → Polygonal Zones → ⋮ → Reconfigure**, untick it and save. Then delete any of its entities still listed under **Settings → Devices & services → Entities**: the mirror, the zone sensor and the last-reported sensor. Home Assistant keeps each entity's last value in `.storage/core.restore_state`, and so in backups, for up to 7 days after removal.
2. Clear the recorder history with `recorder.purge_entities` under **Developer Tools → Actions**. List that tracker's entities and the source tracker:
   ```yaml
   entity_id:
     - device_tracker.polygonal_zones_<name>
     - sensor.polygonal_zones_<name>
     - sensor.polygonal_zones_<name>_last_reported
     - <the source tracker, for example device_tracker.alice_phone>
   ```
   With `keep_days: 0`, the default, all past rows are removed at once.
3. If **Download the GeoJSON files** was on, delete `<config>/polygonal_zones/<entry_id>.json`.
4. Delete any backup taken before these steps, or wait until it expires. It still holds the history.
