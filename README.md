# Polygonal Zones

[![Latest release](https://img.shields.io/github/v/release/MatthewHobbs/Homeassistant-polygonal-zones?display_name=tag&sort=semver)](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/releases/latest)
[![Validate CI](https://img.shields.io/github/actions/workflow/status/MatthewHobbs/Homeassistant-polygonal-zones/validate.yml?branch=main&label=validate)](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/actions/workflows/validate.yml)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A598%25-brightgreen)](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/blob/main/.github/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5)](https://hacs.xyz/)
[![HA quality scale](https://img.shields.io/badge/quality--scale-bronze-cd7f32)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
[![License: MIT](https://img.shields.io/github/license/MatthewHobbs/Homeassistant-polygonal-zones)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/MatthewHobbs/Homeassistant-polygonal-zones)](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/commits/main)

Report the zone a `device_tracker` entity is in, using polygons drawn on a map.

The zones come from a GeoJSON file. GeoJSON is a text format for shapes on a map. Use it where Home Assistant's circular zones do not fit: an irregular property boundary, or a school catchment.

This is a community continuation of [MichelGerding/Homeassistant-polygonal-zones](https://github.com/MichelGerding/Homeassistant-polygonal-zones), which is no longer maintained. Pull requests are welcome.

## Quick start

### Automatic setup

1. Install the [Polygonal Zones Editor add-on](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon) version 0.7.0 or later. Start it, then draw and save your zones.
2. Install this integration version 1.16.0 or later through HACS. See [Installation](#installation). Restart Home Assistant.
3. The add-on announces itself through the Supervisor. Open **Settings → Devices & services** and confirm the discovered **Polygonal Zones** entry.
4. Open the entry's **⋮ → Reconfigure** menu. Choose your `device_tracker` entities, then confirm the tracking notice.

You do not enter a URL, map a port or copy a token.

### Manual setup

Use this path for an integration older than 1.16.0, for an add-on on another host, or for your own GeoJSON file.

1. Install the add-on if you want it, then draw and save your zones.
2. In the add-on's **Network** tab, assign host port 8000. Set a `save_token` in its configuration and restart the add-on.
3. Install the integration through HACS and restart Home Assistant. Open **Settings → Devices & services → Add Integration → Polygonal Zones**.
4. Enter the zones URL, or a path inside `/config`. For the add-on that is `http://<add-on-LAN-IP>:8000/zones.json`.
5. For the add-on's LAN address, turn on **Allow private-network URLs (LAN)** and enter the `save_token` as **Add-on save token**. Both fields are advanced, so turn on Advanced mode in your user profile to see them.
6. Choose your `device_tracker` entities. Tick the box confirming that everyone being tracked has been told. The form will not continue without it.

Use the add-on host's LAN IP address in the URL. A plain DNS name such as `homeassistant` receives no token, so the add-on answers 403. `.local` names are not resolved reliably, and `localhost` is always refused.

Each tracked entity gets a mirror `device_tracker.polygonal_zones_*`. Its state is the zone name (`Home`, `School`, …) or `away`. The [install guide](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/install/) has the full walkthrough.

## Contents

- [Installation](#installation)
- [Configuration options](#configuration-options)
- [Usage](#usage)
- [How updates flow](#how-updates-flow)
- [GeoJSON file format](#geojson-file-format)
- [Actions / services](#actions--services)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Privacy and data handling](#privacy-and-data-handling)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Licence](#licence)

## Installation

Requires Home Assistant 2026.9.1 or later.

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MatthewHobbs&repository=Homeassistant-polygonal-zones&category=integration)

If the button does not work:

1. Open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/MatthewHobbs/Homeassistant-polygonal-zones` with the category **Integration**.
3. Find **Polygonal Zones** in HACS and download it.

To install by hand, copy `custom_components/polygonal_zones/` into `custom_components/` in your Home Assistant config directory. Restart Home Assistant either way.

For a beta release, open the integration's HACS card, choose **⋮ → Redownload** and turn on **Show beta versions**.

Add-on setup and post-install checks: [install guide](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/install/).

## Configuration options

| Field                   | Required | Default                   | Notes                                                                                |
| ----------------------- | -------- | ------------------------- | ------------------------------------------------------------------------------------ |
| `zone_urls`             | yes\*    | —                         | URLs, or paths inside `/config`. \*May be empty when `download_zones` is on.         |
| `prioritize_zone_files` | no       | off                       | Prefer earlier files when a position matches zones in more than one.                 |
| `download_zones`        | no       | on, with exceptions       | Keep one editable local copy. Required by the four zone-editing actions.             |
| `expose_coordinates`    | no       | off; on for older entries | Publish latitude, longitude and accuracy as attributes. Off publishes the zone name. |
| `allow_private_urls`    | no       | off; on for discovered    | Allow private network addresses. Required for the add-on's LAN address.              |
| `zone_source_token`     | no       | —; set by discovery       | The add-on's `save_token`. Sent as `X-Save-Token` to the add-on only.                |
| `home_zone_id`          | no       | —                         | Zone `id` (preferred) or exact `name` that counts as home. Publishes `in_zones`.     |
| `entities`              | yes      | —; empty when discovered  | The `device_tracker.*` entities to evaluate.                                         |

`download_zones` is on for a new manual entry, unless every URL is a private or link-local IP address, `localhost` or a `.local` name. It is off for a legacy entry without the setting and for an entry created by discovery, because the add-on keeps the file.

`zone_source_token` is sent only to a host the integration recognises as the LAN add-on, or to the host an entry received from discovery. It is never sent to an unrelated public URL.

`home_zone_id` takes the zone's `id` before its `name`, so one value never designates two zones. A match publishes `in_zones` containing `zone.home` on the mirror, whether or not coordinates are exposed. See [Privacy](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/privacy/).

To change these settings, open **Settings → Devices & services → Polygonal Zones → ⋮ → Reconfigure**. Adding trackers there asks for the tracking notice again.

## Usage

For each tracked entity the integration creates a mirror `device_tracker` and a companion `sensor`:

```
device_tracker.alice_phone        →  device_tracker.polygonal_zones_alice_phone
                                   →  sensor.polygonal_zones_alice_phone
```

The mirror's state is the name of the zone the source device is inside, or `away`:

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

The mirror always exposes `source_entity`, `last_load_result` and `last_zones_loaded_at`.

With **Expose GPS coordinates** on, it also writes `latitude`, `longitude` and `gps_accuracy`. It publishes `zone_uris` with credentials and query strings removed, and `matched_zones`, which lists every zone the point intersects. Those two stay off without the option, because they reveal LAN hostnames or fine-grained location.

`sensor.polygonal_zones_*` holds the same zone name, or `away`, as a plain string. It resolves independently of the mirror. Read the zone name from this sensor rather than from the `device_tracker` state. See the deprecation notice below.

### Detecting a silent tracker

A stationary phone reports less often. Silence alone does not tell you whether it has stopped. `sensor.polygonal_zones_<name>_last_reported` is a diagnostic timestamp of the source tracker's last report, including reports that repeated an unchanged position.

The sensor is disabled by default. To enable it, open **Settings → Devices & services → Polygonal Zones → entities** and use the filter to show disabled entities.

You decide what "too long" means. This asks a Companion-app phone for a fresh location after ten minutes of silence:

```yaml
automation:
  - alias: "Ask Alice's phone for a location after 10 minutes of silence"
    triggers:
      - trigger: template
        value_template: >-
          {% set s = 'sensor.polygonal_zones_alice_phone_last_reported' %}
          {{ has_value(s) and now() - states(s) | as_datetime > timedelta(minutes=10) }}
    actions:
      - action: notify.mobile_app_alice_phone
        data:
          message: request_location_update
```

Use your own device's notify service. `request_location_update` is a Companion app command, [documented as unreliable on iOS](https://companion.home-assistant.io/docs/notifications/notification-commands/). Frequent requests drain the battery. Other tracker sources do not support the command, but the sensor works with any source.

> **Deprecation notice: zone name in `device_tracker` state**
>
> The integration uses Home Assistant's `location_name` property to publish the zone name as the mirror's `state`. Home Assistant removes that property in **2027.7**. The integration raises a repair issue in **Settings → Repairs**.
>
> Today `state` is still the zone name. Once the property is removed, `state` becomes Home Assistant's standard `home` / `not_home`, and automations that read the zone name from it break. No date is set for that change. To prepare:
>
> - Read the zone name from `sensor.polygonal_zones_*` instead. It carries the same value now.
> - Set `home_zone_id` in the integration's options to use Home Assistant's own zone occupancy, such as the person count of `zone.home`. It publishes `in_zones` on the mirror.
>
> Progress: [issue #86](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues/86).

## How updates flow

Updates are push-based. Nothing polls.

- Each source `device_tracker` has a `state_changed` listener. When its position changes, the mirror re-resolves its zone.
- Zones load once at startup, on `polygonal_zones.reload_zones`, and on `polygonal_zones.reload_all_zones`. Remote URLs are fetched only then, never per location update.
- Saving in the editor add-on calls `reload_all_zones` for you, so the new zones are live without a manual reload.
- A startup load makes up to 5 attempts with jittered exponential backoff, starting at 30 s. After the last failure it raises a repair issue, and the entities stay unavailable until a load succeeds. With **Download the GeoJSON files** on, a failed first download makes Home Assistant retry the setup itself.

## GeoJSON file format

A [GeoJSON](https://geojson.org/) `FeatureCollection` of `Feature` objects. Each has a `Polygon` or `MultiPolygon` geometry, a `name` property (which becomes the entity state) and an optional integer `priority`. When zones overlap, the lowest `priority` wins, then the nearest boundary. With `prioritize_zone_files` on, a zone without its own `priority` takes its file's position in the list. Coordinates are WGS-84 `[longitude, latitude]`.

Full specification, with the schema, size limits, versioning and examples: [matthewhobbs.github.io/Homeassistant-polygonal-zones/zones-format/](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/zones-format/).

## Actions / services

| Action                              | Target | Editable file required?     |
| ----------------------------------- | ------ | --------------------------- |
| `polygonal_zones.reload_zones`      | entity | no                          |
| `polygonal_zones.reload_all_zones`  | none   | no                          |
| `polygonal_zones.add_new_zone`      | device | yes (`download_zones=true`) |
| `polygonal_zones.edit_zone`         | device | yes                         |
| `polygonal_zones.delete_zone`       | device | yes                         |
| `polygonal_zones.replace_all_zones` | device | yes                         |

`reload_zones` reloads the zones and updates the entities. With **Download the GeoJSON files** on it re-reads the local copy, because the sources are fetched only when that copy is missing. `reload_all_zones` does the same for every entry, which is what the add-on calls after a save.

The four mutating actions write to the local file kept when `download_zones` is on. They need a Home Assistant administrator, and they are refused with `ZoneFileNotEditable` when the integration reads a remote URL directly.

A successful mutation refreshes every entity under the config entry, so you do not need `reload_zones` afterwards. Use `reload_zones` after editing a zone file outside these actions, or after a remote host recovers, because a startup load that used all its attempts does not retry on its own.

Worked YAML for each action: [docs/actions.md](docs/actions.md).

## Known limitations

- Only `Polygon` and `MultiPolygon` geometries are accepted. `Point`, `LineString`, `MultiPoint`, `GeometryCollection` and `null` are rejected.
- Only WGS-84 latitude and longitude are supported, in GeoJSON `[longitude, latitude]` order.
- HTTP zone files are capped at 5 MiB, and service payloads at 1 MiB.
- A `FeatureCollection` holds at most 500 features and 10,000 vertices in total, not per feature. The limits apply to both the read path and the service write path. See the [size-limit table](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/zones-format/).
- Zone names are limited to 200 characters on service writes.
- Loopback, link-local (including cloud metadata), multicast and reserved addresses are always refused, whether written as a name or as an IP literal. Private LAN addresses are refused unless **Allow private-network URLs (LAN)** is on. For a source on a blocked address, put the file under `/config` and use its path.
- HTTP 3xx responses are rejected, because the redirect target is not validated.
- Only the device's latest GPS fix is evaluated. History is not replayed.

## Troubleshooting

Fixes for an entity stuck on `unknown` or `away`, private-address errors, config-flow error banners, `ZoneFileNotEditable`, lock timeouts and log verbosity: [troubleshooting page](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/troubleshooting/).

## Privacy and data handling

The integration processes the GPS position of the tracked entities in real time. It runs locally, with no analytics and no third-party reporting.

- Latitude, longitude and accuracy go into attributes only when **Expose GPS coordinates** is on. That is off for new installs and on for entries created before the option existed.
- With coordinates off, the recorder still stores zone entry and exit times unless you exclude the mirror and zone-sensor entities.
- Setup requires a tick confirming that everyone being tracked has been told. Make sure that is true.

Recorder exclude snippet, logging, outbound requests, cloud backups and erasure steps: [privacy page](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/privacy/).

## Roadmap

Open work is tracked in [GitHub issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues) and the [add-on repo's issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/issues). The `location_name` removal is [issue #86](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues/86); see the [deprecation notice](#usage).

The integration ships through HACS and is not being submitted to Home Assistant core, so the manifest stays at `quality_scale: bronze`. The Silver, Gold and Platinum rules are implemented and tracked in [`quality_scale.yaml`](custom_components/polygonal_zones/quality_scale.yaml). Claiming a higher tier needs a core-team review.

## Contributing

This is a spare-time community project, so responses are best-effort. The most useful contributions are issues with reproduction steps, and small focused pull requests. Only English (`custom_components/polygonal_zones/translations/en.json`) ships today. To add a language, copy `en.json` to `translations/<lang>.json`, translate the user-facing strings and open a pull request. See [CONTRIBUTING.md](CONTRIBUTING.md) for the checks to run.

## Licence

MIT. See [LICENSE](LICENSE).
