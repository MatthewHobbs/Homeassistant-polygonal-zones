---
layout: page
title: Zone File Format
nav_order: 3
permalink: /zones-format/
---

# Polygonal Zones file format

The GeoJSON zone file the `polygonal_zones` integration reads. Producers (the companion [editor add-on](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon), other tools, hand-written files) must follow it.

Current version: **`schema_version: 1`**.

## Document shape

The file is a standard GeoJSON [`FeatureCollection`](https://datatracker.ietf.org/doc/html/rfc7946#section-3.3). A single top-level foreign member, `polygonal_zones`, carries spec metadata:

```json
{
  "type": "FeatureCollection",
  "polygonal_zones": { "schema_version": 1 },
  "features": [
    {
      "type": "Feature",
      "properties": { "name": "Home", "priority": 1 },
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [0, 0],
            [0.01, 0],
            [0.01, 0.005],
            [0, 0.005],
            [0, 0]
          ]
        ]
      }
    }
  ]
}
```

RFC 7946 §6.1 allows foreign members. The integration ignores `polygonal_zones` members it does not use and keeps them when it rewrites the file.

## Top-level members

| Member                           | Required | Type                          | Notes                                                                                                          |
| -------------------------------- | -------- | ----------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `type`                           | yes      | string, `"FeatureCollection"` | Standard GeoJSON.                                                                                              |
| `features`                       | yes      | array of Feature              | May be empty.                                                                                                  |
| `polygonal_zones.schema_version` | no       | integer ≥ 1                   | Missing means implicit `1`. The integration refuses any value greater than `MAX_SUPPORTED` with a clear error. |

## Feature members

Each element of `features` is a GeoJSON `Feature`.

### `geometry`

- `type` MUST be `"Polygon"` or `"MultiPolygon"`.
- Coordinates are WGS-84 lon/lat in GeoJSON `[longitude, latitude]` order.
- Rings should close (first coordinate == last coordinate); an unclosed ring is closed automatically.
- Other geometry types (`Point`, `LineString`, `MultiPoint`, `GeometryCollection`, `null`) are rejected.

### `properties`

| Property                | Required | Type    | Notes                                                                                                                               |
| ----------------------- | -------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `name`                  | yes      | string  | Non-empty. Shown as the entity state. Actions reject names over 200 characters.                                                     |
| `priority`              | no       | integer | Lower wins on overlap. Default `0`; with `prioritize_zone_files`, a missing value is the file's position in the URL list.           |
| `id`                    | no       | string  | Stable handle stamped by the editor add-on (UUID4 hex). Kept on every write. `home_zone_id` matches it first, then a zone's `name`. |
| `polygonal_zones_ext.*` | no       | object  | Reserved for extensions. Free-form.                                                                                                 |

Unknown keys under `properties` are kept when the file is rewritten, and the actions log a warning for them. Put new keys under `properties.polygonal_zones_ext`.

## Size limits

A file is rejected when it exceeds the body, feature or vertex limit. Action payloads are also checked against the payload and name limits.

| Limit                                                   | Value     | Source                                                  |
| ------------------------------------------------------- | --------- | ------------------------------------------------------- |
| Remote HTTP body                                        | 5 MiB     | `utils/general.py`                                      |
| Service-call payload (one Feature or FeatureCollection) | 1 MiB     | `services/helpers.py`                                   |
| Zone name length                                        | 200 chars | `services/helpers.py`                                   |
| Features per FeatureCollection                          | 500       | `utils/limits.py` (`MAX_FEATURES_PER_COLLECTION`)       |
| Total vertices across all features in a collection      | 10 000    | `utils/limits.py` (`MAX_TOTAL_VERTICES_PER_COLLECTION`) |

The vertex cap counts every ring of every polygon in the file together. Actions also apply it to a single Feature.

## Versioning

`schema_version` is an integer that rises by 1 on each breaking change: a changed or removed property meaning, a changed set of accepted geometry types, or a new required key. New optional keys under `properties.polygonal_zones_ext` or `polygonal_zones.*` do not change it.

Producers write the highest version whose rules they use, never one this integration has not released. The integration treats a missing version as `1` and refuses a file that declares a higher version than it supports; the error names this document. Actions rewrite the file with the current version.

## Examples

### Minimal file

```json
{
  "type": "FeatureCollection",
  "polygonal_zones": { "schema_version": 1 },
  "features": []
}
```

### Overlapping zones with priority

```json
{
  "type": "FeatureCollection",
  "polygonal_zones": { "schema_version": 1 },
  "features": [
    {
      "type": "Feature",
      "properties": { "name": "Town", "priority": 1 },
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [0, 0],
            [0.02, 0],
            [0.02, 0.02],
            [0, 0.02],
            [0, 0]
          ]
        ]
      }
    },
    {
      "type": "Feature",
      "properties": { "name": "Shop", "priority": 0 },
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [0.005, 0.005],
            [0.008, 0.005],
            [0.008, 0.007],
            [0.005, 0.007],
            [0.005, 0.005]
          ]
        ]
      }
    }
  ]
}
```

A point inside both zones resolves to `Shop` because its `priority` is lower.

### Additive extension under reserved namespace

```json
{
  "type": "Feature",
  "properties": {
    "name": "Office",
    "priority": 0,
    "polygonal_zones_ext": { "color": "#3366ff", "editor_version": "2.1" }
  },
  "geometry": {
    "type": "Polygon",
    "coordinates": [[/* ... */]]
  }
}
```

The integration ignores `polygonal_zones_ext` but preserves it through any read-modify-write operation.
