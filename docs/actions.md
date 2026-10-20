---
layout: page
title: Action examples
nav_order: 6
permalink: /actions/
---

# Action examples

Worked YAML for each action. What each action does, and which need an editable zone file, is in the README under [Actions / services](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones#actions--services).

## `reload_zones`

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
          [-0.090, 51.515],
          [-0.085, 51.515],
          [-0.085, 51.518],
          [-0.090, 51.518],
          [-0.090, 51.515]
        ]]
      }
    }
```

## `edit_zone`

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

## `delete_zone`

```yaml
action: polygonal_zones.delete_zone
target:
  device_id: 0123456789abcdef0123456789abcdef
data:
  zone_name: "Office"
```

## `replace_all_zones`

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
