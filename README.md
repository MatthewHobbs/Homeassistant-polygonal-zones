# Polygonal Zones

[![Latest release](https://img.shields.io/github/v/release/MatthewHobbs/Homeassistant-polygonal-zones?display_name=tag&sort=semver)](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/releases/latest)
[![Validate CI](https://img.shields.io/github/actions/workflow/status/MatthewHobbs/Homeassistant-polygonal-zones/validate.yml?branch=main&label=validate)](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/actions/workflows/validate.yml)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A598%25-brightgreen)](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/blob/main/.github/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5)](https://hacs.xyz/)
[![HA quality scale](https://img.shields.io/badge/quality--scale-bronze-cd7f32)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
[![License: MIT](https://img.shields.io/github/license/MatthewHobbs/Homeassistant-polygonal-zones)](LICENSE)
[![Maintenance](https://img.shields.io/maintenance/yes/2026)](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/commits/main)

**Full documentation (install guide, zone format reference, privacy notice):** [matthewhobbs.github.io/Homeassistant-polygonal-zones](https://matthewhobbs.github.io/Homeassistant-polygonal-zones)

This Home Assistant integration lets you define arbitrary polygonal zones from a GeoJSON file and resolve any tracked `device_tracker` entity into the zone it currently sits inside. Use it when the built-in circular HA zones aren't expressive enough — irregular property boundaries, school catchments, neighbourhoods, town centres, etc.

**Status:** Actively maintained; HACS-ready. Manifest declares `quality_scale: bronze`; the rules for Silver, Gold, and Platinum are implemented and tracked in [`quality_scale.yaml`](custom_components/polygonal_zones/quality_scale.yaml), but a higher tier can only be claimed after a Home Assistant architecture-team review (which happens through the [core-integration submission process](https://developers.home-assistant.io/docs/creating_component_index/), not by self-declaration).

> **Fork Notice**
>
> This is a community-maintained continuation of the original [MichelGerding/Homeassistant-polygonal-zones](https://github.com/MichelGerding/Homeassistant-polygonal-zones), which is no longer actively maintained.
> Development continues here at [MatthewHobbs/Homeassistant-polygonal-zones](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones).
>
> Pull requests and contributions are welcome.

## Quick start

1. **Install the editor add-on** (optional but recommended): add the [Polygonal Zones Editor add-on](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon) to your HA Supervisor, start it, and draw your zones. It serves a GeoJSON (a text format for shapes on a map) file at `http://<your-ha-host>:8000/zones.json`.
2. **Install this integration** via HACS (see the button below) or by copying `custom_components/polygonal_zones/` into your HA config.
3. **Add the integration**: Settings → Devices & Services → Add Integration → "Polygonal Zones".
4. **Configure it**: paste your zones URL (or a file path under `/config`), select the `device_tracker` entities to follow, and submit. If you're using a LAN address from the editor add-on, enable **Allow private-network URLs (LAN)** in the advanced options — the integration blocks private addresses by default as an SSRF protection (a protection that stops the server being tricked into fetching internal addresses).
5. **Done**: each tracked entity now has a mirror `device_tracker.polygonal_zones_*` whose state is the zone name (`Home`, `School`, …) or `away`.

> Need more detail? See the [full install guide](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/install/).

## Contents

- [Companion add-on](#companion-add-on)
- [Installation](#installation)
- [Configuration options](#configuration-options)
- [Usage](#usage)
- [Use cases](#use-cases)
- [How updates flow](#how-updates-flow)
- [GeoJSON file format](#geojson-file-format)
- [Actions / services](#actions--services)
- [Action examples](#action-examples)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Privacy and data handling](#privacy-and-data-handling)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Companion add-on

This integration is one half of a paired system. The other half is the **[Polygonal Zones Editor add-on](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon)** — a map editor that runs inside Home Assistant where you draw zones and save them. It serves the `zones.json` file this integration reads.

If you're setting up for the first time, install the add-on first: it gives you a URL (`http://<your-ha-host>:8000/zones.json`) to paste into the integration's `zone_urls` field. See the [full install guide](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/install/) for a step-by-step walkthrough of both.

## Installation

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MatthewHobbs&repository=Homeassistant-polygonal-zones&category=integration)

If the button doesn't work: HACS → ⋮ → Custom repositories → add `https://github.com/MatthewHobbs/Homeassistant-polygonal-zones` as an Integration. For manual installation, copy `custom_components/polygonal_zones/` into your HA config's `custom_components/` directory and restart. For beta releases, open the integration's HACS card → ⋮ → **Redownload** → toggle **Show beta versions**.

Full guide (add-on setup, post-install verification, first-run tips): [matthewhobbs.github.io/Homeassistant-polygonal-zones/install/](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/install/)

## Configuration options

| Field                   | Required | Default (new install)                                                     | Notes                                                                                                                                                            |
| ----------------------- | -------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `zone_urls`             | yes\*    | —                                                                         | List of `http(s)://…` URLs or paths inside `/config`. \*Can be empty if `download_zones` is enabled.                                                             |
| `prioritize_zone_files` | no       | off                                                                       | Prefer earlier files when a position matches zones in multiple files.                                                                                            |
| `download_zones`        | no       | **on** (new installs); **off** when reconfiguring a legacy entry          | Materialise the source files into a single editable local file. Required to use the `add_new_zone` / `edit_zone` / `delete_zone` / `replace_all_zones` services. |
| `expose_coordinates`    | no       | **off** (new installs); on for entries created before this option existed | Write `latitude`, `longitude`, and `gps_accuracy` to entity attributes on every update. When off, only the zone name is published.                               |
| `allow_private_urls`    | no       | off                                                                       | Relax the SSRF block for RFC-1918 (private home-network addresses like 192.168.x.x) and similar private ranges. Required when using the add-on's LAN URL.        |
| `entities`              | yes      | —                                                                         | `device_tracker.*` entities to evaluate. Selectable from the entity picker.                                                                                      |

To change any of these settings after setup: Settings → Devices & Services → Polygonal Zones → ⋮ → Reconfigure.

## Usage

For each tracked entity the integration creates a mirror entity:

```
device_tracker.alice_phone        →  device_tracker.polygonal_zones_alice_phone
```

The mirror's state is the name of the zone the source device is inside, falling back to `"away"`. Use it directly in automations:

```yaml
automation:
  - alias: "Notify when Alice arrives at school"
    triggers:
      - trigger: state
        entity_id: device_tracker.polygonal_zones_alice_phone
        to: "School"
    actions:
      - action: notify.mobile_app
        data:
          message: "Alice has arrived at school"
```

The mirror entity always exposes `zone_uris`, `source_entity`, `last_load_result`, `last_zones_loaded_at`, and `matched_zones` in its attributes. When **Expose GPS coordinates** is enabled, `latitude`, `longitude`, and `gps_accuracy` are also written on each update, so templates can read them without referencing the underlying tracker.

## Use cases

A few scenarios where polygonal zones are a better fit than HA's built-in circular zones:

- **Property boundary that isn't a circle** — flag-shaped lots, mews flats with awkward driveways, farms.
- **School catchment / neighbourhood** — fire an automation when a child arrives in a defined area larger than a single circle would naturally cover.
- **Town centre / shopping district** — irregular footprints where a circle would either miss the edges or include unwanted streets.
- **Multi-zone presence with priority** — overlapping zones (e.g. "Town" containing "Shop") where you want the more specific one to win automation triggers. Combine with `prioritize_zone_files` or per-feature `priority`.
- **Geofence handover between vehicles and phones** — track multiple `device_tracker` entities into the same zone set; correlate their `polygonal_zones_*` mirror states.

## How updates flow

The integration is **push-based**. There is no polling schedule.

- Each tracked source `device_tracker` entity has a `state_changed` listener attached.
- When the source's `latitude` / `longitude` / `gps_accuracy` change, the mirror entity recomputes which zone it sits in and updates its state.
- Zone definitions are loaded once on startup (and on `polygonal_zones.reload_zones`). Remote URLs are fetched only at those moments — never per location update.
- If the initial zone fetch fails it retries with exponential backoff (30 s → 60 s → 120 s → 240 s → 480 s, 5 attempts) before raising a Home Assistant repair issue and marking the entity unavailable.

## GeoJSON file format

[GeoJSON](https://geojson.org/) is a standard text format for shapes on a map. This integration accepts a `FeatureCollection` where each `Feature` has a `Polygon` or `MultiPolygon` geometry, a `name` property (shown as the entity state), and an optional integer `priority` (lower = higher priority when zones overlap). Coordinates are WGS-84 `[longitude, latitude]` order; polygon rings must close (first == last coordinate).

Full format specification (schema, size limits, versioning, examples): [matthewhobbs.github.io/Homeassistant-polygonal-zones/zones-format/](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/zones-format/)

[![Add zone editor add-on to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FMatthewHobbs%2FHomeassistant-polygonal-zones-addon.git)

## Actions / services

| Action                              | Target | Editable file required?     |
| ----------------------------------- | ------ | --------------------------- |
| `polygonal_zones.reload_zones`      | entity | no                          |
| `polygonal_zones.add_new_zone`      | device | yes (`download_zones=true`) |
| `polygonal_zones.edit_zone`         | device | yes                         |
| `polygonal_zones.delete_zone`       | device | yes                         |
| `polygonal_zones.replace_all_zones` | device | yes                         |

`reload_zones` re-fetches the zone files and updates the entity's in-memory cache. The four mutating actions write to the on-disk file managed when `download_zones` is enabled — they are refused with `ZoneFileNotEditable` if the integration is reading directly from a remote URL.

After a mutating action, call `reload_zones` to apply the change to the entity.

## Action examples

### `reload_zones`

```yaml
action: polygonal_zones.reload_zones
target:
  entity_id: device_tracker.polygonal_zones_alice_phone
```

Optionally returns the loaded zones (names + polygon coordinates) — useful for debugging:

```yaml
action: polygonal_zones.reload_zones
target:
  entity_id: device_tracker.polygonal_zones_alice_phone
response_variable: zones
```

### `add_new_zone`

```yaml
action: polygonal_zones.add_new_zone
target:
  device_id: 0123456789abcdef0123456789abcdef
data:
  zone: |
    {
      "type": "Feature",
      "properties": {"name": "Office", "priority": 0},
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [-0.090, 51.515],
          [-0.085, 51.515],
          [-0.085, 51.518],
          [-0.090, 51.518],
          [-0.090, 51.515]
        ]]
      }
    }
```

### `edit_zone`

Replace the geometry of an existing zone. The `zone_name` matches the existing zone; the `zone` payload is the new Feature.

```yaml
action: polygonal_zones.edit_zone
target:
  device_id: 0123456789abcdef0123456789abcdef
data:
  zone_name: "Office"
  zone: |
    {
      "type": "Feature",
      "properties": {"name": "Office", "priority": 0},
      "geometry": { "type": "Polygon", "coordinates": [[ ... ]] }
    }
```

### `delete_zone`

```yaml
action: polygonal_zones.delete_zone
target:
  device_id: 0123456789abcdef0123456789abcdef
data:
  zone_name: "Office"
```

### `replace_all_zones`

Replaces the entire local file with a new `FeatureCollection`. Useful when the editor add-on regenerates the file.

```yaml
action: polygonal_zones.replace_all_zones
target:
  device_id: 0123456789abcdef0123456789abcdef
data:
  zone: |
    {
      "type": "FeatureCollection",
      "features": [ ... ]
    }
```

## Known limitations

- **Geometry types**: only `Polygon` and `MultiPolygon` are accepted. `Point`, `LineString`, `MultiPoint`, `GeometryCollection`, and a `null` geometry are rejected at the service boundary.
- **Coordinate system**: only WGS-84 lat/lon (the GeoJSON default, `[longitude, latitude]` order). No projected coordinate systems.
- **Zone-file size**: HTTP zone files are capped at **5 MiB**. Service payloads (`add_new_zone`, `edit_zone`, `replace_all_zones`) at **1 MiB**.
- **Zone names**: max **200 characters**.
- **Network targets**: outbound zone-file fetches **refuse private, loopback, link-local, multicast, reserved, and metadata IPs** to prevent SSRF. If your zones live on a LAN or `169.254.x` host, place the file under `/config` and reference the path instead of a URL.
- **No 3xx redirects**: HTTP responses with status 300–399 are rejected (the redirect target hasn't been validated by our DNS resolver).
- **Service mutations require a downloaded local file**: `add_new_zone`, `edit_zone`, `delete_zone`, and `replace_all_zones` are refused with `ZoneFileNotEditable` when the integration is reading directly from a remote URL. Toggle **Download the GeoJSON files** in the integration options to enable mutations.
- **Single point in time per device**: only the source device's most recent GPS fix is evaluated; history isn't replayed.
- **Async constraints**: `shapely` is a sync compute library — geometry math runs on the event loop. For typical home setups (≤20 tracked devices, ≤100 zones) this is imperceptible. Very large zone sets may stall the loop.

## Troubleshooting

### The mirror entity stays `unknown` or `away`

- Check the source `device_tracker.*` actually has `latitude`, `longitude`, and `gps_accuracy` attributes. Many wifi-only trackers don't.
- Look in the HA log for messages tagged `custom_components.polygonal_zones`. A `WARNING` line that says "Failed to load zones for entry=…" means the GeoJSON couldn't be fetched on startup. The integration retries with exponential backoff (30 s, 60 s, 120 s, 240 s, 480 s) before giving up. Call `reload_zones` after the source recovers.
- Confirm the polygon ring is closed (first coordinate == last coordinate) and the geometry type is `Polygon` or `MultiPolygon`.

### "Refusing to connect to non-public address"

The integration won't fetch from `192.168.x.x`, `10.x.x.x`, `169.254.x.x`, or any other private / loopback / link-local / metadata IP by default (SSRF protection). To fix: enable **Allow private-network URLs (LAN)** in the integration's Configure dialog, or place the file under `/config` and reference it as a path.

For config-flow error banners (`invalid_url`, `invalid_path`, `unreachable_url`), `ZoneFileNotEditable`, lock-timeout errors, and log verbosity: [matthewhobbs.github.io/Homeassistant-polygonal-zones/troubleshooting/](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/troubleshooting/)

## Privacy and data handling

The integration continuously processes real-time GPS coordinates of the tracked `device_tracker` entities. Everything runs locally — no analytics or third-party reporting. Key points:

- **Coordinates in attributes**: latitude, longitude, and GPS accuracy are only written to entity attributes when **Expose GPS coordinates** is enabled. New installs default this to **off**; only the zone name is published.
- **Recorder**: even with coordinates off, the recorder logs state-change timestamps (zone entry/exit events) unless you explicitly exclude the entities:

  ```yaml
  recorder:
    exclude:
      entity_globs:
        - device_tracker.polygonal_zones_*
  ```

- **Consent**: any person whose `device_tracker` entity you select will have their location continuously monitored. Setup requires you to tick a confirmation that everyone being tracked has been told — make sure that's true before you do.

Full privacy details (logging, outbound requests, cloud-backup GDPR note, deletion/right-to-erasure steps): [matthewhobbs.github.io/Homeassistant-polygonal-zones/privacy/](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/privacy/)

## Roadmap

Open work items are tracked as [GitHub issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues); editor add-on work lives in the [add-on repo's issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/issues).

**Distribution.** This integration is intentionally distributed through **HACS** and is **not** being submitted to Home Assistant core. The Silver/Gold/Platinum quality-scale rules are implemented (see [`quality_scale.yaml`](custom_components/polygonal_zones/quality_scale.yaml)), but the manifest stays at `bronze` because a higher tier requires HA architecture-team review via core submission — a trade we deliberately decline, to keep HACS's release autonomy. (Revisitable if adoption grows substantially.)

## Contributing

This is a community-supported fork of the original project, maintained in spare time rather than by a dedicated team. That means responses and releases move at a best-effort pace, and the long-term health of the integration depends on contributions from the people who use it.

If you rely on this integration, please consider getting involved:

- **Found a bug or have an idea?** Open an issue — clear reproduction steps or a concrete use case make a big difference.
- **Comfortable with Python?** Pull requests are very welcome, whether that's a small fix, a test, or a new feature. Smaller, focused PRs are easier to review and merge.
- **Not a coder?** Help with documentation, translations, or triaging issues is just as valuable. The non-English translation files under `custom_components/polygonal_zones/translations/` (`de`, `fr`, `es`, `nl`, `it`) were machine-generated as a starting point — native-speaker corrections via PR are very welcome.

I'll do my best to respond to issues and review pull requests as quickly as I can, but patience is appreciated.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
