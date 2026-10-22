---
layout: page
title: Troubleshooting
nav_order: 5
permalink: /troubleshooting/
---

# Troubleshooting

For add-on problems, start with the add-on log: **Settings → Add-ons → Polygonal Zones → Log**.

Integration source: [MatthewHobbs/Homeassistant-polygonal-zones](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones)
Add-on source: [MatthewHobbs/Homeassistant-polygonal-zones-addon](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon)

---

## The mirror entity stays `unknown` or `away`

- The source `device_tracker.*` entity needs `latitude`, `longitude` and `gps_accuracy` attributes. Wi-Fi-only trackers report presence without them, and the mirror ignores those updates.
- Look for `custom_components.polygonal_zones` in the log. "Failed to load zones for entry=…" means a load failed. The first load is retried four times, after roughly 30, 60, 120 and 240 seconds (each delay is shortened by a random amount of up to half). After the last failure the entities are unavailable and a repair issue appears. Call `polygonal_zones.reload_zones` once the source is back.
- Zone geometry must be `Polygon` or `MultiPolygon`. A file with any other type fails to load.

---

## Config-flow errors

| Banner                | Meaning                                                                                                     |
| --------------------- | ----------------------------------------------------------------------------------------------------------- |
| `invalid_url`         | A URL has no host, a malformed port, or a scheme other than `http` or `https`.                              |
| `invalid_path`        | A non-URL entry is not an existing file under `/config`, or resolves outside it.                            |
| `private_url_blocked` | A URL host is a literal private, loopback or link-local IP and **Allow private-network URLs (LAN)** is off. |
| `consent_required`    | The location-tracking consent box is not ticked.                                                            |

---

## `Refusing to connect to '…': no reachable addresses available`

By default the integration refuses private, loopback, link-local, multicast, reserved and unspecified addresses, including the cloud metadata address `169.254.169.254`. This blocks server-side request forgery (SSRF): a zone URL reaching services inside your network. The check applies to every address the host name resolves to.

If the zone file is on your LAN, including the companion add-on on the same host, either:

- Tick **Allow private-network URLs (LAN)** under Configure, Advanced options. This allows private ranges such as `10.x.x.x`, `172.16.x.x` to `172.31.x.x`, `192.168.x.x` and IPv6 unique local addresses. Loopback, link-local and metadata addresses stay blocked.
- Put `zones.json` under your HA config directory and reference it by path, for example `polygonal_zones/zones.json`. No network request is made.

---

## `Refusing redirect from '…' (status 3xx)`

Zone URLs must serve the file directly: the integration does not follow redirects. Use the final URL.

---

## `Zone files of entity are not editable`

`add_new_zone`, `edit_zone`, `delete_zone` and `replace_all_zones` work only when **Download the GeoJSON files** is on. Without it there is no local file to change. Turn it on under Configure and save.

With it on, the integration fetches the sources once, when the local file does not exist, and reads the local file from then on. Edits made at the source afterwards are not picked up.

---

## `Path '…' resolves outside config directory`

A path in `zone_urls` points outside the HA config directory once normalised. Use a path inside it.

---

## `Timed out waiting for zone file lock`

Another action on the same zone file held the lock for more than 15 seconds. Retry. If it recurs, check for slow storage. Setting `POLYGONAL_ZONES_LOCK_ACQUIRE_TIMEOUT` (seconds) in the Home Assistant process environment changes the limit.

---

## `Rate limit exceeded` or `reload_zones is being called too fast`

`reload_zones` and each of the four zone-editing actions accept one call every 2 seconds per config entry. Wait and retry.

---

## Increasing log verbosity

Set the integration's logger to `DEBUG` to see zone resolution results and lifecycle events:

```yaml
logger:
  default: info
  logs:
    custom_components.polygonal_zones: debug
```

Add this to `configuration.yaml` and restart HA. Zone names and match details appear only at `DEBUG`; coordinates are never logged. See [Privacy](privacy.md) before sending logs elsewhere.

---

## Opening an issue

If the above does not fix it, open an issue with:

- The HA and integration versions (HACS, or **Settings → Devices & Services → Polygonal Zones**).
- The relevant `custom_components.polygonal_zones` log lines. At `DEBUG` they contain zone names and distances, so check them before pasting.
- The integration's diagnostics download, which redacts zone URLs, tracker entities, the token, the home zone and the entry title.
- Whether you use the add-on or a self-hosted `zones.json`.

Issues are public. Do not paste coordinates, your `zones.json`, home or school zone names, or attribute dumps: they show where people are.

Integration issues: [github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues)
Add-on issues: [github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/issues)
