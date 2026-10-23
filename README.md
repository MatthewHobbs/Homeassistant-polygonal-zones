# Polygonal Zones

[![Latest release](https://img.shields.io/github/v/release/MatthewHobbs/Homeassistant-polygonal-zones?display_name=tag&sort=semver)](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/releases/latest)
[![Validate CI](https://img.shields.io/github/actions/workflow/status/MatthewHobbs/Homeassistant-polygonal-zones/validate.yml?branch=main&label=validate)](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/actions/workflows/validate.yml)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A598%25-brightgreen)](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/blob/main/.github/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5)](https://hacs.xyz/)
[![HA quality scale](https://img.shields.io/badge/quality--scale-bronze-cd7f32)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
[![License: MIT](https://img.shields.io/github/license/MatthewHobbs/Homeassistant-polygonal-zones)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/MatthewHobbs/Homeassistant-polygonal-zones)](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/commits/main)

Resolve any `device_tracker` entity into the polygonal zone it sits in, using zones from a GeoJSON file (a text format for shapes on a map). Use it where circular HA zones do not fit, such as irregular property boundaries or school catchments.

This is a community continuation of [MichelGerding/Homeassistant-polygonal-zones](https://github.com/MichelGerding/Homeassistant-polygonal-zones), which is no longer maintained. Pull requests are welcome.

## Quick start

1. Install the [Polygonal Zones Editor add-on](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon) (optional), start it and draw your zones. Under its **Network** tab assign host port 8000, and set a `save_token` in its configuration (see the [install guide](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/install/)). The zones are then served at `http://<your-ha-host>:8000/zones.json`.
2. Install this integration through HACS (see [Installation](#installation)) and restart Home Assistant.
3. Go to Settings → Devices & Services → Add Integration → Polygonal Zones.
4. Enter the zones URL (or a file path under `/config`), select the `device_tracker` entities and tick the box confirming that everyone being tracked knows about it. The form will not continue without it. The add-on URL is a LAN address and private addresses are blocked by default as SSRF protection (the server being tricked into fetching internal addresses), so turn on **Allow private-network URLs (LAN)** in the advanced options (visible with Advanced mode on in your user profile), and enter the add-on's `save_token` as **Add-on save token**. Use the add-on host's LAN IP address in the URL: a plain DNS name such as `homeassistant` gets no token and a 403, `.local` names are not reliably resolved, and `localhost` is always refused.

Each tracked entity now has a mirror `device_tracker.polygonal_zones_*` whose state is the zone name (`Home`, `School`, …) or `away`. The [install guide](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/install/) has the full walkthrough.

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
- [License](#license)

## Installation

Requires Home Assistant 2026.9.1 or later.

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MatthewHobbs&repository=Homeassistant-polygonal-zones&category=integration)

If the button does not work: HACS → ⋮ → Custom repositories, then add `https://github.com/MatthewHobbs/Homeassistant-polygonal-zones` as an Integration. To install manually, copy `custom_components/polygonal_zones/` into your HA config's `custom_components/` directory and restart. For beta releases, open the integration's HACS card → ⋮ → **Redownload** → toggle **Show beta versions**.

Add-on setup and post-install checks: [install guide](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/install/).

## Configuration options

| Field                   | Required | Default (new install)                                                                                | Notes                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------- | -------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `zone_urls`             | yes\*    | —                                                                                                    | List of `http(s)://…` URLs or paths inside `/config`. \*Can be empty if `download_zones` is enabled.                                                                                                                                                                                                                                                        |
| `prioritize_zone_files` | no       | off                                                                                                  | Prefer earlier files when a position matches zones in multiple files.                                                                                                                                                                                                                                                                                       |
| `download_zones`        | no       | **on**; **off** if every URL is an IP address, `localhost` or a `.local` host, or for a legacy entry | Materialise the source files into a single editable local file. Required to use the `add_new_zone` / `edit_zone` / `delete_zone` / `replace_all_zones` services.                                                                                                                                                                                            |
| `expose_coordinates`    | no       | **off** (new installs); on for entries created before this option existed                            | Write `latitude`, `longitude`, and `gps_accuracy` to entity attributes on every update. When off, only the zone name is published.                                                                                                                                                                                                                          |
| `allow_private_urls`    | no       | off                                                                                                  | Relax the SSRF block for RFC-1918 (private home-network addresses like 192.168.x.x) and similar private ranges. Required when using the add-on's LAN URL.                                                                                                                                                                                                   |
| `zone_source_token`     | no       | —                                                                                                    | The add-on's `save_token`. The add-on's LAN port refuses every request without it, and it also gates the add-on's read routes (`GET /zones.json`, `GET /trackers.json`), not just writes. Sent as the `X-Save-Token` header, but only on requests to a URL that looks like the LAN add-on; never sent to a public `https://` source.                        |
| `home_zone_id`          | no       | —                                                                                                    | The zone's `id` (preferred — see `properties.id` in your zone file, survives a rename) or exact `name` that counts as "home". Blank means no zone is home. Publishes `in_zones` (`zone.home`) on the mirror entity when matched, regardless of `expose_coordinates` — see [Privacy](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/privacy/). |
| `entities`              | yes      | —                                                                                                    | `device_tracker.*` entities to evaluate. Selectable from the entity picker.                                                                                                                                                                                                                                                                                 |

To change any of these settings after setup: Settings → Devices & Services → Polygonal Zones → ⋮ → Reconfigure.

## Usage

For each tracked entity the integration creates a mirror `device_tracker` and a companion `sensor`:

```
device_tracker.alice_phone        →  device_tracker.polygonal_zones_alice_phone
                                   →  sensor.polygonal_zones_alice_phone
```

The mirror's state is the name of the zone the source device is inside, or `away`. Use it in automations:

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

The mirror always exposes `source_entity`, `last_load_result` and `last_zones_loaded_at`. With **Expose GPS coordinates** on, it also writes `latitude`, `longitude`, `gps_accuracy`, `zone_uris` (credentials and query strings removed) and `matched_zones` (every zone the point intersects). The last two are gated because they reveal fine-grained location or LAN hostnames.

`sensor.polygonal_zones_*` holds the same zone name (or `away`) as a plain string, resolved independently of the mirror. Read the zone name from it rather than from the `device_tracker` state; see the deprecation notice below.

### Detecting a silent tracker

A stationary phone reports less often, so a quiet tracker looks like a dead one. `sensor.polygonal_zones_<name>_last_reported` is a diagnostic timestamp of the source tracker's last report, including reports that repeated an unchanged position. It is disabled by default: enable it under Settings → Devices & services → Polygonal Zones → entities (use the filter to show disabled entities).

You decide what "too long" means. For example, to ask a Companion-app phone for a fresh location after ten minutes of silence:

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

Use the notify service of your own device. `request_location_update` is a Companion app command that is [documented as unreliable on iOS](https://companion.home-assistant.io/docs/notifications/notification-commands/) and not recommended on a tight schedule because of battery use. Other tracker sources do not support it; the sensor works for any source.

> **Deprecation notice: zone name in `device_tracker` state**
>
> Home Assistant is removing the `location_name` property this integration uses to publish the zone name as the mirror's `state`, in **2027.7**. The integration raises a repair issue in **Settings → Repairs**. Today `state` is still the zone name. When the removal ships (no date set), `state` will become HA's standard `home` / `not_home`, and automations reading the zone name from it will break. To prepare:
>
> - Read the zone name from `sensor.polygonal_zones_*` instead. It carries the same value now.
> - For HA's own zone-occupancy features (such as the person count of `zone.home`), set `home_zone_id` in the integration's options. It publishes `in_zones` on the mirror.
>
> Progress: [issue #86](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues/86).

## How updates flow

Updates are push-based; nothing polls.

- Each source `device_tracker` has a `state_changed` listener. When its position changes, the mirror re-resolves its zone.
- Zones load once at startup and on `polygonal_zones.reload_zones`. Remote URLs are fetched only then, never per location update.
- If the startup load fails it makes up to 5 attempts with jittered exponential backoff (starting at 30 s). After the last failure it raises a repair issue; the entities are unavailable until a load succeeds. With **Download the GeoJSON files** on, a failed first download makes Home Assistant retry the setup itself instead.

## GeoJSON file format

A [GeoJSON](https://geojson.org/) `FeatureCollection` of `Feature`s, each with a `Polygon` or `MultiPolygon` geometry, a `name` property (the entity state) and an optional integer `priority`. When zones overlap, the lowest `priority` wins, then the nearest boundary. With `prioritize_zone_files` on, a zone without its own `priority` takes its file's position in the list. Coordinates are WGS-84 `[longitude, latitude]`.

Full specification (schema, size limits, versioning, examples): [matthewhobbs.github.io/Homeassistant-polygonal-zones/zones-format/](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/zones-format/)

## Actions / services

| Action                              | Target | Editable file required?     |
| ----------------------------------- | ------ | --------------------------- |
| `polygonal_zones.reload_zones`      | entity | no                          |
| `polygonal_zones.add_new_zone`      | device | yes (`download_zones=true`) |
| `polygonal_zones.edit_zone`         | device | yes                         |
| `polygonal_zones.delete_zone`       | device | yes                         |
| `polygonal_zones.replace_all_zones` | device | yes                         |

`reload_zones` reloads the zones and updates the entities' in-memory cache. With **Download the GeoJSON files** on it re-reads the local copy, because the sources are fetched only when that copy is missing. The four mutating actions write to the local file kept when `download_zones` is on, and need a Home Assistant administrator. They are refused with `ZoneFileNotEditable` when the integration reads a remote URL directly.

Mutating actions refresh every tracked entity under the config entry after a successful write, so you do not need `reload_zones` afterwards. Use `reload_zones` after editing a zone file outside these actions or after a remote host recovers (a startup load that used all its attempts does not retry on its own).

Worked YAML for each action: [docs/actions.md](docs/actions.md).

## Known limitations

- Only `Polygon` and `MultiPolygon` geometries are accepted. `Point`, `LineString`, `MultiPoint`, `GeometryCollection` and `null` are rejected.
- Only WGS-84 lat/lon is supported, in GeoJSON `[longitude, latitude]` order.
- HTTP zone files are capped at 5 MiB and service payloads at 1 MiB.
- A `FeatureCollection` holds at most 500 features and 10,000 vertices in total (not per feature), on both the file/URL read path and the service write path. See the [size-limit table](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/zones-format/).
- Zone names are limited to 200 characters on service writes.
- Loopback, link-local (including cloud metadata), multicast and reserved addresses are always refused, whether written as a name or a literal IP. Private LAN addresses are refused unless **Allow private-network URLs (LAN)** is on. For a source on a blocked address, put the file under `/config` and use its path.
- HTTP 3xx responses are rejected, because the redirect target is not validated.
- Only the device's latest GPS fix is evaluated; history is not replayed.

## Troubleshooting

Fixes for an entity stuck on `unknown` or `away`, private-address errors, config-flow error banners, `ZoneFileNotEditable`, lock timeouts and log verbosity: [troubleshooting page](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/troubleshooting/).

## Privacy and data handling

The integration processes the GPS position of the tracked `device_tracker` entities in real time. It runs locally, with no analytics or third-party reporting.

- Latitude, longitude and accuracy are written to attributes only when **Expose GPS coordinates** is on. It defaults to off for new installs and on for entries created before the option existed.
- With coordinates off, the recorder still stores zone entry and exit times unless you exclude the mirror and zone-sensor entities.
- Setup requires a tick confirming that everyone being tracked has been told. Make sure that is true.

Recorder exclude snippet, logging, outbound requests, cloud backups and erasure steps: [privacy page](https://matthewhobbs.github.io/Homeassistant-polygonal-zones/privacy/).

## Roadmap

Open work is tracked in [GitHub issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues) and the [add-on repo's issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon/issues). The `location_name` removal is [issue #86](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues/86); see the [deprecation notice](#usage).

The integration is distributed through HACS and is not being submitted to Home Assistant core, so the manifest stays at `quality_scale: bronze`. The Silver, Gold and Platinum rules are implemented and tracked in [`quality_scale.yaml`](custom_components/polygonal_zones/quality_scale.yaml); claiming a higher tier needs a core-team review.

## Contributing

This is a spare-time community project, so responses are best-effort. Issues with reproduction steps and small, focused pull requests are the most useful. Only English (`custom_components/polygonal_zones/translations/en.json`) ships today; to add a language, copy `en.json` to `translations/<lang>.json`, translate the user-facing strings and open a PR. See [CONTRIBUTING.md](CONTRIBUTING.md) for the checks to run.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
