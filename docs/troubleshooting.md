---
layout: page
title: Troubleshooting
nav_order: 5
permalink: /troubleshooting/
---

# Troubleshooting

Covers the most common problems with the integration. For add-on issues, check the add-on log first: **Settings → Add-ons → Polygonal Zones → Log**.

Integration source: [MatthewHobbs/Homeassistant-polygonal-zones](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones)
Add-on source: [MatthewHobbs/Homeassistant-polygonal-zones-addon](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon)

---

## The mirror entity stays `unknown` or `away`

- Check that the source `device_tracker.*` entity actually has `latitude`, `longitude`, and `gps_accuracy` attributes. Many Wi-Fi-only trackers don't provide GPS coordinates — they report presence but not position. The integration needs all three attributes to evaluate zone membership.
- Look in the HA log for messages tagged `custom_components.polygonal_zones`. A `WARNING` line saying "Failed to load zones for entry=…" means the GeoJSON couldn't be fetched on startup. The integration retries with exponential backoff (30 s, 60 s, 120 s, 240 s, 480 s, five attempts) before giving up and raising a HA repair issue. After the source recovers, call `polygonal_zones.reload_zones` to force a retry.
- Confirm the polygon ring is closed: the first coordinate must equal the last coordinate.
- Confirm the geometry type is `Polygon` or `MultiPolygon`. `Point`, `LineString`, and other types are rejected.

---

## Config-flow errors

| Banner            | Meaning                                                                                                                                     |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `invalid_url`     | One of the entries isn't a valid `http(s)` URL. Check the protocol and that the host is present.                                            |
| `invalid_path`    | A non-URL entry doesn't resolve to an existing file inside `/config`, or it tries to escape the config directory (e.g. `../../etc/passwd`). |
| `unreachable_url` | The URL passed validation but couldn't be fetched at setup time.                                                                            |

---

## "Refusing to connect to non-public address"

The integration won't fetch from `127.0.0.1`, `192.168.x.x`, `10.x.x.x`, `169.254.x.x`, or any other private, loopback, link-local, or metadata IP by default. This prevents SSRF (server-side request forgery — tricking the server into fetching an internal address it shouldn't).

If your zones file is served from a LAN address (including the companion add-on on the same host), you have two options:

- **Enable `allow_private_urls`.** Re-open the integration's Configure dialog, expand Advanced options, and tick **Allow private-network URLs (LAN)**. This unlocks RFC-1918 space (the private home-network address ranges like `192.168.x.x` / `10.x.x.x`); loopback, link-local, and metadata ranges stay blocked.
- **Use a `/config` path instead.** Place the `zones.json` file under your HA config directory and reference it as a path (e.g. `polygonal_zones/zones.json`). No network request is made.

---

## `ZoneFileNotEditable` from a service call

The mutating actions (`add_new_zone`, `edit_zone`, `delete_zone`, `replace_all_zones`) only work when **Download the GeoJSON files** is enabled in the integration options. Without it, the integration reads the source URL directly on every reload and has no local file to mutate.

To fix: re-open Configure → enable **Download the GeoJSON files** → save.

---

## `Path '…' resolves outside config directory`

A path you supplied in `zone_urls` (or via a service call) escapes `/config` when normalised. Fix the path so it stays within the HA config directory.

---

## `Timed out waiting for lock on …`

A previous service call against the same zone file didn't complete within 15 seconds. Usually transient — retry the action. If it recurs, check for very slow remote fetches or filesystem issues.

---

## The add-on's map won't load / tiles are broken

The add-on loads map tiles from third-party providers (OpenStreetMap, CARTO, Esri). If tiles fail to render, check:

- Your HA instance has outbound internet access.
- A browser console error identifies which tile provider is failing and why.
- If tiles worked before and broke after an upgrade, check the add-on [CHANGELOG](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/blob/main/polygonal_zones_editor/CHANGELOG.md) for tile-layer changes.

---

## Increasing log verbosity

Set the integration's logger to `DEBUG` to see GPS coordinates, zone resolution results, and full lifecycle events:

```yaml
logger:
  default: info
  logs:
    custom_components.polygonal_zones: debug
```

Add this to `configuration.yaml` and restart HA. GPS coordinates and zone names are only emitted at `DEBUG` level — see [Privacy](privacy.md) before shipping logs to an external service.

For the add-on, set `log_level: debug` under **Settings → Add-ons → Polygonal Zones → Configuration** and restart the add-on.

---

## Opening an issue

If the above doesn't resolve your problem, open an issue with:

- HA version and integration version (shown in HACS or **Settings → Devices & Services → Polygonal Zones**)
- The relevant log lines from `custom_components.polygonal_zones` (at `DEBUG` level if possible — but redact any personal coordinates before pasting)
- Whether you're using the add-on or a self-hosted `zones.json`

Integration issues: [github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues)
Add-on issues: [github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/issues)
