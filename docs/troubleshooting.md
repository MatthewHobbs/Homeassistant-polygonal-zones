---
layout: page
title: Troubleshooting
nav_order: 5
permalink: /troubleshooting/
---

# Troubleshooting

Home Assistant now calls these **apps**. Some versions call them **add-ons**; it is the same thing, and the menus below use **app**.

For app problems, start with the app log: **Settings → Apps → Polygonal Zones → Log**.

Integration source: [MatthewHobbs/Homeassistant-polygonal-zones](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones)
App source: [MatthewHobbs/Homeassistant-polygonal-zones-addon](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon)

---

## The mirror entity stays `unknown` or `away`

- The source `device_tracker.*` entity needs `latitude`, `longitude` and `gps_accuracy` attributes. A Wi-Fi-only tracker reports presence without them, and those updates are ignored.
- Search the log for `custom_components.polygonal_zones`. The line "Failed to load zones for entry=…" means a load failed. The first load is tried four more times, after about 30, 60, 120 and 240 seconds. Each wait is shortened by a random amount of up to half. After the last failure the entities become unavailable and a repair issue appears. Call `polygonal_zones.reload_zones` once the source is back.
- With **Download the GeoJSON files** on, a failed first download makes Home Assistant retry the setup itself. That case shows no warning line and no repair issue.
- Zones must be `Polygon` or `MultiPolygon` shapes. A file with any other shape fails to load.

---

## The app does not appear under Devices & services

The app announces itself to Home Assistant each time it starts. Automatic setup needs app 0.7.0 or later and integration 1.16.0 or later.

1. Restart the app once, then open **Settings → Devices & services**.
2. If nothing appears, open the app log and look for what it sent to Home Assistant.
3. If it still does not appear, use the manual setup in the [install guide](install.md).

An entry that already points at the app by URL is not offered a second time. Edit that entry instead, under **⋮ → Reconfigure**.

---

## Config-flow errors

"Config flow" is the setup form. Each banner below names one problem with it.

| Banner                | Meaning                                                                                                                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `invalid_url`         | A URL has no host, a broken port, or a scheme other than `http` or `https`.                                                                                                                      |
| `invalid_path`        | A non-URL entry is not an existing file under `/config`, or it resolves outside that folder.                                                                                                     |
| `private_url_blocked` | A URL host is a plain private address, such as `192.168.x.x`, and **Allow private-network URLs (LAN)** is off.                                                                                   |
| `blocked_address`     | A URL host is a plain loopback, link-local, multicast or reserved address, or a short form such as `127.1`. These are always refused. Use the host's network address, or a file under `/config`. |
| `own_entities`        | You picked an entity this integration created (`device_tracker.polygonal_zones_*`). Pick the device's own tracker.                                                                               |
| `consent_required`    | The tracking consent box is not ticked.                                                                                                                                                          |

---

## `Refusing to connect to '…': no reachable addresses available`

By default the integration refuses private, loopback, link-local, multicast, reserved and unspecified addresses. That includes the cloud metadata address `169.254.169.254`.

This stops a zone URL from reaching services inside your network. The check runs on every address the host name resolves to.

If your zone file is on your own network, including the app on the same machine, do one of these:

- Tick **Allow private-network URLs (LAN)** under Configure. This allows private ranges such as `10.x.x.x`, `172.16.x.x` to `172.31.x.x`, `192.168.x.x` and IPv6 unique local addresses. Loopback, link-local and metadata addresses stay blocked.
- Put `zones.json` in your Home Assistant config folder and point at it by path, for example `polygonal_zones/zones.json`. No network request is made.

---

## `Refusing redirect from '…' (status 3xx)`

A zone URL must serve the file directly, because the integration does not follow redirects. Use the final address.

---

## `Zone files of entity are not editable`

`add_new_zone`, `edit_zone`, `delete_zone` and `replace_all_zones` only work when **Download the GeoJSON files** is on. Without it there is no local file to change. Turn it on under Configure and save.

With it on, the integration fetches the sources once, when the local file does not exist, and reads the local file from then on. Later edits at the source are not picked up.

---

## `Path '…' resolves outside config directory`

A path in `zone_urls` points outside the Home Assistant config folder once it is tidied up. Use a path inside it.

---

## `Timed out waiting for zone file lock`

Another action on the same zone file held the lock for more than 15 seconds. Try again. If it keeps happening, check for slow storage. You can change the limit with `POLYGONAL_ZONES_LOCK_ACQUIRE_TIMEOUT`, in seconds, in the Home Assistant process environment.

---

## `Rate limit exceeded` or `reload_zones is being called too fast`

`reload_zones` and each of the four zone-editing actions accept one call every 2 seconds per entry. Wait and try again.

---

## Increasing log verbosity

Set the integration's logger to `DEBUG` to see zone results and lifecycle events:

```yaml
logger:
  default: info
  logs:
    custom_components.polygonal_zones: debug
```

Add this to `configuration.yaml` and restart Home Assistant. Zone names and match details appear only at `DEBUG`. Coordinates are never logged. Read [Privacy](privacy.md) before you send logs to anyone else.

---

## Opening an issue

If none of this helps, open an issue with:

- Your Home Assistant and integration versions. You can find the integration version in HACS, or under **Settings → Devices & services → Polygonal Zones**.
- The relevant `custom_components.polygonal_zones` log lines. At `DEBUG` they contain zone names and distances, so read them before you paste.
- The integration's diagnostics download. It removes zone URLs, tracker entities, the token, the home zone and the entry title.
- Whether you use the app or your own `zones.json`.

Issues are public. Do not paste coordinates, your `zones.json`, home or school zone names, or attribute dumps. They show where people are.

Integration issues: [github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues)
App issues: [github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/issues)
