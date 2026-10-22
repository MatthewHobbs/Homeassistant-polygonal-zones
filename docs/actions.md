---
layout: page
title: Action examples
nav_order: 6
permalink: /actions/
---

# Action examples

Worked YAML for each action. What each action does, and which need an editable zone file, is in the README under [Actions / services](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones#actions--services). `reload_zones` and the four zone-editing actions are each limited to one call per 2 seconds for each config entry. The zone-editing actions also need an administrator.

## `reload_zones`

```yaml
action: polygonal_zones.reload_zones
target:
  entity_id: device_tracker.polygonal_zones_alice_phone
```

With `response_variable`, the action returns the loaded zones as a list of `name`, `priority` and `geometry` (exterior-ring coordinates):

```yaml
action: polygonal_zones.reload_zones
target:
  entity_id: device_tracker.polygonal_zones_alice_phone
response_variable: zones
```

## `add_new_zone`

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
          [0, 0],
          [0.005, 0],
          [0.005, 0.003],
          [0, 0.003],
          [0, 0]
        ]]
      }
    }
```

## `edit_zone`

Replaces the zone named `zone_name` with the Feature in `zone`, properties included.

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

## `delete_zone`

```yaml
action: polygonal_zones.delete_zone
target:
  device_id: 0123456789abcdef0123456789abcdef
data:
  zone_name: "Office"
```

## `replace_all_zones`

Replaces the whole local file with a `FeatureCollection`. It does not read the existing file, so it also replaces a corrupt one.

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
