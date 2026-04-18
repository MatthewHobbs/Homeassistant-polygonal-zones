> ℹ️ **Fork Notice**
>
> This is a community-maintained continuation of the original [MichelGerding/Homeassistant-polygonal-zones](https://github.com/MichelGerding/Homeassistant-polygonal-zones), which is no longer actively maintained.
> Development continues here at [MatthewHobbs/Homeassistant-polygonal-zones](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones).
>
> Pull requests and contributions are welcome.

# Polygonal Zones

This homeassistant integration provides the ability to create polygonal zones and use them in automations.
It gives you the ability to provide a location for a GeoJSON file that contains the zones you want to monitor.
The integration will create a sensor for each device you want to track and provide you the zone it is currently in.

## Installation

Installing the integration can be done using hacs but also manually. Installation using hacs is recommended.

### Install using hacs

To install the integration using hacs you can either add the url to your custom repositories or use the button below

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MatthewHobbs&repository=Homeassistant-polygonal-zones&category=integration)

### Manual installation

Installing the integration manually can be done by copying the `custom_components/polygonal_zones` folder to your
`custom_components`
folder in your homeassistant configuration folder.

## Configuration

The configuration is done in the homeassistant UI.

1. Go to Configuration -> Integrations
2. Click on the `+` button to add a new integration.
3. Search for `Polygonal Zones` and click on it.
4. Fill in the required fields:
   - GeoJSON URIs: The URLs to the GeoJSON files that contains the zones you want to track.
   - Devices: The devices you want to track.

If you want to create an empty GeoJSON file you can omit the GeoJSON URIs field but the download option is required. The section below explains the options further.

### Configuration options

The configuration exposes you to a couple of different options.
These options are as follows:

- GeoJSON uris: This is a list of the GeoJSON files that contain the zones you want to track. This can either be a local
  file or a URL to a website.
- Prioritize zone files: If you want to prioritize the order of the zone files, enable this option. This means that if a
  tracker is in multiple zones it will only consider those with the lowest priority.
- Download zones: Use a local GeoJSON file to store the zones in. This will load the above defined files into a single
  file. The provided urls will be replaced with the location of this file. If you want to edit the zone files using
  actions, you will need to enable this option.
- Registered entities: Select the entities that you want to track in the zones.

## Usage

The integration will create an entity for each entity you want to track. The state of this entity will be the zone the
device is currently in. You can use this entity in automations to trigger actions based on the zone the device is in.

The entities name will be generated based on the tracked entity. For example, if you are tracking a device called
`device_tracker.my_phone`, the entity will be called `device_tracker.polygonal_zones_device_tracker_my_phone`. If that
entity is already defined, the integration will append `_n` to the name where `n` is the number of the entity.

## GeoJSON file

The zones are stored in geojson files. GeoJSON is a well-defined standard for storing geospatial data. It is a
JSON-based format that is easy for humans to read and write and easy for machines to parse and generate.
Currently only polygons are supported. An example of this file is shown below.

For ease of creating and managing this file in the UI an optional add-on is available that will generate and host
the file. This add-on can be found in the [polygonal zones editor repo](https://github.com/MichelGerding/Homeassistant-polygonal-zones-addon/). This add-on can be added by using the button below.

[![Add zone editor add-on to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FMichelGerding%2FHomeassistant-polygonal-zones-addon.git)

### Example file

The `priority` property is optional; a lower number means higher priority.

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "name": "Home",
        "priority": 0
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": []
      }
    }
  ]
}
```

## Actions

The integration provides a couple of different actions that can be used to modify the zones. It also provides an action
to reload the zones cache.

These actions are as follows:

- `polygonal_zones.add_new_zone`: This action will add a new zone to the GeoJSON file. This expects a GeoJSON feature as input.
- `polygonal_zones.delete_zone`: This action will delete a zone from the GeoJSON file. This expects the name of the zone to delete as input.
- `polygonal_zones.edit_zone`: This action will edit a zone in the GeoJSON file. This expects a GeoJSON feature as input and the name of the zone to edit as input.
- `polygonal_zones.replace_all_zones`: This action will replace all zones in the GeoJSON file with the provided zones. This expects a GeoJSON feature collection as input.
- `polygonal_zones.reload_zones`: This action will reload the zones from the GeoJSON files.

all but the reload_zones action expect the device to be used as target. This is because the zone files are for the entire
device and not a single entity. You will also still need to call the reload zones integration action to update the entities.
The reload_zones action expects the entities to be reloaded as target and returns the newly loaded zones to the user.

## Privacy and data handling

This integration processes real-time GPS coordinates of the `device_tracker` entities you choose to track. Everything runs locally inside your Home Assistant instance — no analytics, telemetry, or third-party reporting is performed by the integration itself.

What is stored where:

- **Entity state**: the resolved zone name (e.g. `Home`) is the entity state. Latitude, longitude, GPS accuracy, and the source entity are written to the entity's attributes on every update.
- **Recorder history**: by default Home Assistant's recorder will persist these attributes, which means a full location history of tracked devices accumulates in the HA database unless you exclude it.
- **Zone files**: when `download_zones` is enabled, the integration writes a GeoJSON file under `<config>/polygonal_zones/<entry_id>.json` with mode `0600` inside a directory with mode `0700`.
- **Outbound requests**: when `zone_urls` points at an http(s) URL, the integration fetches it from your HA instance. The server hosting the GeoJSON learns your public IP. Private, loopback, and link-local addresses are rejected to prevent SSRF.
- **Logging**: GPS coordinates and zone names are only logged at `DEBUG` level. At default log levels they are not written to the HA log.

If you do not want location history retained, add something like the following to your HA configuration:

```yaml
recorder:
  exclude:
    entity_globs:
      - device_tracker.polygonal_zones_*
```

Note that any person whose `device_tracker` entity you select will have their location continuously monitored. Please make sure they are aware before tracking them.

## Roadmap

Open work items are tracked as GitHub issues: [MatthewHobbs/Homeassistant-polygonal-zones/issues](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones/issues).

## Contributing

This is a community-supported fork of the original project, maintained in spare time rather than by a dedicated team. That means responses and releases move at a best-effort pace, and the long-term health of the integration depends on contributions from the people who use it.

If you rely on this integration, please consider getting involved:

- **Found a bug or have an idea?** Open an issue — clear reproduction steps or a concrete use case make a big difference.
- **Comfortable with Python?** Pull requests are very welcome, whether that's a small fix, a test, or a new feature. Smaller, focused PRs are easier to review and merge.
- **Not a coder?** Help with documentation, translations, or triaging issues is just as valuable.

I'll do my best to respond to issues and review pull requests as quickly as I can, but patience is appreciated.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details
