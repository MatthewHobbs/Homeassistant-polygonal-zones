# Polygonal Zones file format

This document is the canonical specification for the GeoJSON file consumed by the `polygonal_zones` Home Assistant integration. Producers of zone files (the companion [editor add-on](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon), third-party tools, or hand-written files) MUST follow this spec; the integration parses against it.

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
        "coordinates": [[[-0.135, 51.51], [-0.125, 51.51], [-0.125, 51.515], [-0.135, 51.515], [-0.135, 51.51]]]
      }
    }
  ]
}
```

Foreign members are explicitly permitted by RFC 7946 §6.1. Readers that don't know the `polygonal_zones` member MUST ignore it.

## Top-level members

| Member                        | Required | Type                  | Notes                                                                                  |
| ----------------------------- | -------- | --------------------- | -------------------------------------------------------------------------------------- |
| `type`                        | yes      | string, `"FeatureCollection"` | Standard GeoJSON.                                                              |
| `features`                    | yes      | array of Feature      | May be empty.                                                                          |
| `polygonal_zones.schema_version` | no    | integer ≥ 1           | Missing means implicit `1`. The integration refuses any value greater than `MAX_SUPPORTED` with a clear error. |

Integers only for `schema_version` — no semver. The integer increments by 1 on every breaking change; consumers need a single `if version > known` branch.

## Feature members

Each element of `features` is a GeoJSON `Feature`.

### `geometry`

- `type` MUST be `"Polygon"` or `"MultiPolygon"`.
- Coordinates are WGS-84 lon/lat in GeoJSON `[longitude, latitude]` order.
- Rings must close (first coordinate == last coordinate).
- Other geometry types (`Point`, `LineString`, `MultiPoint`, `GeometryCollection`, `null`) are rejected.

### `properties`

| Property                       | Required | Type    | Notes                                                                 |
| ------------------------------ | -------- | ------- | --------------------------------------------------------------------- |
| `name`                         | yes      | string  | Non-empty, ≤200 characters. Surfaced as the HA entity state.          |
| `priority`                     | no       | integer | Lower value = higher priority when zones overlap. Default: `0`.       |
| `polygonal_zones_ext.*`        | no       | object  | Reserved namespace for additive extensions. Free-form.                |

Unknown keys under `properties` are preserved round-trip but produce a WARNING log so drift is visible. Do **not** add new keys at the top-level `properties` map — put extensions under `properties.polygonal_zones_ext` so the canonical namespace stays small.

## Size limits

Applied at read time; the integration rejects anything that exceeds them.

| Limit                                 | Value       | Source                          |
| ------------------------------------- | ----------- | ------------------------------- |
| Remote HTTP body                      | 5 MiB       | `utils/general.py`              |
| Service-call payload (one Feature or FeatureCollection) | 1 MiB | `services/helpers.py`       |
| Zone name length                      | 200 chars   | `services/helpers.py`           |
| Features per FeatureCollection        | 500         | `services/helpers.py`           |
| Total vertices across a FeatureCollection | 10 000  | `services/helpers.py`           |

The vertex cap defends against event-loop stalls from pathological polygons.

## Versioning rules

### Additive (no `schema_version` bump)

- New optional keys under `properties.polygonal_zones_ext.*`.
- New optional top-level foreign members under `polygonal_zones.*` (e.g. `polygonal_zones.editor.last_modified`).
- Additional optional properties that readers may safely ignore.

### Breaking (bumps `schema_version` to the next integer)

- Changing or removing the semantics of an existing property.
- Changing the accepted geometry type set.
- Changing the addressing model (e.g. moving from `device_id` to a new identifier in service calls).
- Adding a new **required** key.

Producers MUST stamp `polygonal_zones.schema_version` matching the highest-numbered rule set they use.

## Compatibility contract

- **Producers** (editor add-on, third-party tools): emit `schema_version` that matches the features you use. Prefer additive changes. Never emit a version the integration hasn't released.
- **Consumer** (this integration): accept any `schema_version <= MAX_SUPPORTED`. Treat missing as `1`. Reject higher with a clear error and a repair issue pointing at this doc.

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
      "geometry": { "type": "Polygon", "coordinates": [[[-0.14, 51.50], [-0.12, 51.50], [-0.12, 51.52], [-0.14, 51.52], [-0.14, 51.50]]] }
    },
    {
      "type": "Feature",
      "properties": { "name": "Shop", "priority": 0 },
      "geometry": { "type": "Polygon", "coordinates": [[[-0.131, 51.512], [-0.128, 51.512], [-0.128, 51.514], [-0.131, 51.514], [-0.131, 51.512]]] }
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
  "geometry": { "type": "Polygon", "coordinates": [[ /* ... */ ]] }
}
```

The integration ignores `polygonal_zones_ext` but preserves it through any read-modify-write operation.
