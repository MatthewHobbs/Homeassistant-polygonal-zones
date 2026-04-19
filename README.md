# Polygonal Zones

This Home Assistant integration lets you define arbitrary polygonal zones from a GeoJSON file and resolve any tracked `device_tracker` entity into the zone it currently sits inside. Use it when the built-in circular HA zones aren't expressive enough — irregular property boundaries, school catchments, neighbourhoods, town centres, etc.

> ℹ️ **Fork Notice**
>
> This is a community-maintained continuation of the original [MichelGerding/Homeassistant-polygonal-zones](https://github.com/MichelGerding/Homeassistant-polygonal-zones), which is no longer actively maintained.
> Development continues here at [MatthewHobbs/Homeassistant-polygonal-zones](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones).
>
> Pull requests and contributions are welcome.

## Contents

- [Installation](#installation)
- [First-time setup](#first-time-setup)
- [Configuration options](#configuration-options)
- [Usage](#usage)
- [GeoJSON file format](#geojson-file-format)
- [Actions / services](#actions--services)
- [Action examples](#action-examples)
- [Troubleshooting](#troubleshooting)
- [Privacy and data handling](#privacy-and-data-handling)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Installation

Two paths: HACS (recommended) or manual copy.

### Install via HACS

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MatthewHobbs&repository=Homeassistant-polygonal-zones&category=integration)

If the button doesn't work: HACS → ⋮ → Custom repositories → add `https://github.com/MatthewHobbs/Homeassistant-polygonal-zones` as an Integration.

### Manual installation

Copy `custom_components/polygonal_zones/` into the `custom_components/` directory inside your Home Assistant config folder, then restart Home Assistant.

## First-time setup

1. **Add the integration**: Settings → Devices & Services → Add Integration → search "Polygonal Zones".
2. **Fill in the form**:
   - **URLs of GeoJSON files**: one or more `https://…/zones.json` URLs, or relative paths under `/config` (e.g. `polygonal_zones/my_zones.json`). Leave empty if you want a blank file created for you (toggle **Download the GeoJSON files** below).
   - **Entities**: the `device_tracker.*` entities whose location you want to evaluate against the zones.
   - **Prioritize order of zone files** _(advanced)_: when one position falls inside zones from more than one file, prefer the earlier file in the list.
   - **Download the GeoJSON files** _(advanced)_: download / merge the source URLs into a single local file under `<config>/polygonal_zones/<entry_id>.json`. **Required if you want to mutate zones from automations** via the action services below.
3. **Submit**. The integration creates one new entity per selected device, named `device_tracker.polygonal_zones_<original_entity>`. The state is the zone name (e.g. `Home`, `School`) or `away` if the device falls outside every zone.
4. **Verify**: open Developer Tools → States and find `device_tracker.polygonal_zones_*`. The `latitude`, `longitude`, `gps_accuracy`, and `zone_uris` attributes should populate within a few seconds.

If the entity stays unknown for more than a minute, see [Troubleshooting](#troubleshooting).

## Configuration options

| Field                   | Required | Notes                                                                                                                                                            |
| ----------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `zone_urls`             | yes\*    | List of `http(s)://…` URLs or paths inside `/config`. \*Can be empty if `download_zones` is enabled.                                                             |
| `prioritize_zone_files` | no       | Prefer earlier files when a position matches zones in multiple files.                                                                                            |
| `download_zones`        | no       | Materialise the source files into a single editable local file. Required to use the `add_new_zone` / `edit_zone` / `delete_zone` / `replace_all_zones` services. |
| `entities`              | yes      | `device_tracker.*` entities to evaluate. Selectable from the entity picker.                                                                                      |

Re-open the integration's Configure dialog to change `zone_urls` and `prioritize_zone_files` later. To add or remove tracked entities, delete and re-add the integration entry.

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

The mirror entity also exposes the source coordinates in its attributes (`latitude`, `longitude`, `gps_accuracy`) so templates can read them directly without referencing the underlying tracker.

## GeoJSON file format

[GeoJSON](https://geojson.org/) is a standard JSON-based geospatial format. This integration accepts a `FeatureCollection` containing `Feature` objects whose geometry is a `Polygon` or `MultiPolygon`. Other geometry types (`Point`, `LineString`, etc.) are rejected.

Each Feature must have:

- `properties.name` — display name shown as the entity state.
- `properties.priority` — _(optional)_ integer, lower number = higher priority when zones overlap and `prioritize_zone_files` is off.
- `geometry` — `Polygon` or `MultiPolygon` with coordinates in standard GeoJSON `[longitude, latitude]` order.

For convenience, an optional add-on with a UI editor lives at the [polygonal zones editor repo](https://github.com/MichelGerding/Homeassistant-polygonal-zones-addon/):

[![Add zone editor add-on to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FMichelGerding%2FHomeassistant-polygonal-zones-addon.git)

### Example file

A minimal file with two zones — `Home` (a small square in central London for illustration) and `Park` (a higher-priority overlapping area):

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "name": "Home",
        "priority": 1
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [-0.135, 51.51],
            [-0.125, 51.51],
            [-0.125, 51.515],
            [-0.135, 51.515],
            [-0.135, 51.51]
          ]
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {
        "name": "Park",
        "priority": 0
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [-0.131, 51.512],
            [-0.128, 51.512],
            [-0.128, 51.514],
            [-0.131, 51.514],
            [-0.131, 51.512]
          ]
        ]
      }
    }
  ]
}
```

Things worth knowing:

- The first and last coordinate of each polygon ring **must be identical** (the ring closes itself).
- Coordinates are `[longitude, latitude]` — that's the GeoJSON convention, the opposite of how Home Assistant usually displays positions.
- A point that lies in `Park` and `Home` will resolve to `Park` because its priority value is lower.

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

## Troubleshooting

### The mirror entity stays `unknown` or `away`

- Check the source `device_tracker.*` actually has `latitude`, `longitude`, and `gps_accuracy` attributes. Many wifi-only trackers don't.
- Look in the HA log for messages tagged `custom_components.polygonal_zones`. A `WARNING` line that says "Failed to load zones for entry=…" means the GeoJSON couldn't be fetched on startup. The integration retries with exponential backoff (30s, 60s, 120s, 240s, 480s) before giving up. Call `reload_zones` after the source recovers.
- Confirm the polygon ring is closed (first coordinate == last coordinate) and the geometry type is `Polygon` or `MultiPolygon`.

### Config-flow errors

| Banner            | Meaning                                                                                                                                     |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `invalid_url`     | One of the entries isn't a valid `http(s)` URL. Check the protocol and that the host is present.                                            |
| `invalid_path`    | A non-URL entry doesn't resolve to an existing file inside `/config`, or it tries to escape the config directory (e.g. `../../etc/passwd`). |
| `unreachable_url` | The URL passed shape validation but couldn't be fetched.                                                                                    |

### "Refusing to connect to non-public address"

The integration won't fetch from `127.0.0.1`, `192.168.x.x`, `10.x.x.x`, `169.254.x.x`, or any other private / loopback / link-local / metadata IP. This is to prevent SSRF. Solutions:

- Host the GeoJSON on a public URL.
- Place the file in `/config` and reference it as a path (e.g. `polygonal_zones/zones.json`).

### `ZoneFileNotEditable` from a service call

The mutating actions only work when **Download the GeoJSON files** is enabled in the integration options. Without it, the integration reads the source URL directly on every reload and has no local file to mutate.

### `Path '…' resolves outside config directory`

A path you supplied (in `zone_urls` or via a service call) resolves outside `/config` when normalised. Fix the path so it stays within the HA config directory.

### `Timed out waiting for lock on …`

A previous service call against the same zone file hasn't finished within 15 seconds. Usually transient (e.g. slow remote fetch). Retry the action.

### Increasing log verbosity

Set the integration's logger to `DEBUG` to see GPS coordinates, zone resolution, and full lifecycle events:

```yaml
logger:
  default: info
  logs:
    custom_components.polygonal_zones: debug
```

GPS coordinates and zone names are **only** emitted at DEBUG level — see [Privacy](#privacy-and-data-handling) for details.

## Privacy and data handling

This integration processes real-time GPS coordinates of the `device_tracker` entities you choose to track. Everything runs locally inside your Home Assistant instance — no analytics, telemetry, or third-party reporting is performed by the integration itself.

What is stored where:

- **Entity state**: the resolved zone name (e.g. `Home`) is the entity state. Latitude, longitude, GPS accuracy, and the source entity are written to the entity's attributes on every update.
- **Recorder history**: by default Home Assistant's recorder will persist these attributes, which means a full location history of tracked devices accumulates in the HA database unless you exclude it.
- **Zone files**: when `download_zones` is enabled, the integration writes a GeoJSON file under `<config>/polygonal_zones/<entry_id>.json` with mode `0600` inside a directory with mode `0700`.
- **Outbound requests**: when `zone_urls` points at an http(s) URL, the integration fetches it from your HA instance. The server hosting the GeoJSON learns your public IP. Private, loopback, and link-local addresses are rejected to prevent SSRF.
- **Logging**: GPS coordinates and zone names are only logged at `DEBUG` level. At default log levels they are not written to the HA log. `WARNING`-level logs (raised when a zone fetch fails) include the source `entity_id` (e.g. `device_tracker.alice_phone`) — if you ship Home Assistant logs to an external aggregator, consider filtering or redacting these.

If you do not want location history retained, add something like the following to your HA configuration:

```yaml
recorder:
  exclude:
    entity_globs:
      - device_tracker.polygonal_zones_*
```

If you use Nabu Casa cloud backup (or any other backup that includes the recorder database), the location history above will be included in the backup. Apply the `recorder` exclude block before the next backup if you do not want that data leaving the local network.

The `polygonal_zones.reload_zones` service accepts an optional `return_response: true`. When set, it returns the loaded zone names and polygon coordinates to the caller. This is intended for debugging — be careful not to forward that response to external services (e.g. a notification body), as zone names and shapes are sensitive location data.

Note that any person whose `device_tracker` entity you select will have their location continuously monitored. Please make sure they are aware before tracking them.

## Roadmap

Open work items are tracked as GitHub issues: [MatthewHobbs/Homeassistant-polygonal-zones/issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues).

## Contributing

This is a community-supported fork of the original project, maintained in spare time rather than by a dedicated team. That means responses and releases move at a best-effort pace, and the long-term health of the integration depends on contributions from the people who use it.

If you rely on this integration, please consider getting involved:

- **Found a bug or have an idea?** Open an issue — clear reproduction steps or a concrete use case make a big difference.
- **Comfortable with Python?** Pull requests are very welcome, whether that's a small fix, a test, or a new feature. Smaller, focused PRs are easier to review and merge.
- **Not a coder?** Help with documentation, translations, or triaging issues is just as valuable. The non-English translation files under `custom_components/polygonal_zones/translations/` (`de`, `fr`, `es`, `nl`, `it`) were machine-generated as a starting point — native-speaker corrections via PR are very welcome.

I'll do my best to respond to issues and review pull requests as quickly as I can, but patience is appreciated.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
