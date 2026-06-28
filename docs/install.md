---
layout: page
title: Installation
nav_order: 2
permalink: /install/
---

# Installation

Install the **add-on first**, then the **integration**. The add-on draws your zones and serves `zones.json`; the integration reads that file. You need both.

**Requirements:** Home Assistant 2026.6.4 or later, Python 3.14 (bundled with HA OS — no action needed if you run HA OS or Supervised).

---

## Step 1 — Add-on: Polygonal Zones Editor

The add-on is a map editor that runs inside Home Assistant. You draw polygons on a map, name them, and save. The result is a `zones.json` file the integration consumes.

### 1a. Add the custom repository

Click the button to add the add-on repository to your Home Assistant Supervisor:

[![Add add-on repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FMatthewHobbs%2FHomeassistant-polygonal-zones-addon.git)

If the button doesn't work, add it manually:

1. **Settings → Add-ons → Add-on Store**
2. Click **⋮** (top right) → **Repositories**
3. Paste `https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon` and click **Add**

### 1b. Install the add-on

After adding the repository, find **Polygonal Zones** in the Add-on Store and click **Install**.

> **32-bit hosts.** HA 2025.12 deprecated `armhf`, `armv7`, and `i386` addon architectures. Add-on releases from 0.2.26 onwards are `aarch64` and `amd64` only. If you're on a 32-bit host (Raspberry Pi 0/1, 32-bit OS), pin to add-on version 0.2.25 or upgrade to a 64-bit HA OS install.

### 1c. Start the add-on and draw your zones

1. Go to **Settings → Add-ons → Polygonal Zones** and click **Start**.
2. Click **Open Web UI** to open the map editor.
3. Click the pentagon (Draw Polygon) button on the right side of the map.
4. Click points on the map to define your zone's shape, then click the first point again to close it.
5. Give the zone a name in the sidebar.
6. Click **Save** (bottom of the sidebar). Unsaved changes are lost on restart.

Repeat for each zone you want to define.

### 1d. Note the zones.json URL

The add-on serves your zones at:

```
http://<your-ha-host>:8000/zones.json
```

You'll need this URL when you configure the integration in Step 2. You can also enable **Show in sidebar** on the add-on's Configuration tab to keep the editor one click away.

---

## Step 2 — Integration: Polygonal Zones

The integration is a HACS custom integration that watches `device_tracker` entities and resolves their GPS position against your polygon zones.

### 2a. Add via HACS

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MatthewHobbs&repository=Homeassistant-polygonal-zones&category=integration)

If the button doesn't work, add it manually in HACS:

1. Open **HACS** in the sidebar
2. Click **⋮** (top right) → **Custom repositories**
3. Paste `https://github.com/MatthewHobbs/Homeassistant-polygonal-zones` and set category to **Integration**
4. Click **Add**, then find **Polygonal Zones** in HACS and click **Download**

### 2b. Restart Home Assistant

After downloading the integration, restart Home Assistant (**Settings → System → Restart**) before proceeding.

### 2c. Add the integration

[![Add Polygonal Zones integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=polygonal_zones)

Or navigate manually: **Settings → Devices & Services → Add Integration** → search for **Polygonal Zones**.

### 2d. Configure the integration

Fill in the setup form:

| Field                              | What to enter                                                                               |
| ---------------------------------- | ------------------------------------------------------------------------------------------- |
| **URLs of GeoJSON files**          | `http://<your-ha-host>:8000/zones.json` — the add-on URL from Step 1d.                      |
| **Entities**                       | The `device_tracker.*` entities you want to track against your zones.                       |
| **Prioritize order of zone files** | _(advanced)_ When a position matches zones from multiple files, prefer the earlier file.    |
| **Download the GeoJSON files**     | _(advanced)_ Copies the remote file locally so you can mutate zones via automation actions. |

> **LAN URL note.** The integration's SSRF defence blocks private network addresses (`192.168.x.x`, `10.x.x.x`, etc.) by default. Because the add-on URL is a LAN address, you need to enable **Allow private-network URLs (LAN)** in the integration's advanced options. This unlocks RFC-1918 space; loopback, link-local, and metadata ranges stay blocked regardless.
>
> In the add-on, also make sure `allow_all_ips: true` is set under **Settings → Add-ons → Polygonal Zones → Configuration** so the integration's requests are accepted.

Click **Submit**. The integration creates one new entity per tracked device:

```
device_tracker.alice_phone  →  device_tracker.polygonal_zones_alice_phone
```

### 2e. Verify

Open **Developer Tools → States** and look for `device_tracker.polygonal_zones_*`. The state should be a zone name or `away` within a few seconds of the source device reporting a GPS fix.

If the entity stays `unknown` for more than a minute, see [Troubleshooting](troubleshooting.md).

---

## What you'll have when done

- A map editor (add-on) reachable from your HA sidebar or via **Open Web UI**
- A `zones.json` served at `http://<ha-host>:8000/zones.json`
- One `device_tracker.polygonal_zones_<name>` entity per tracked device, with state = zone name or `away`
- Automation triggers like "notify me when Alice arrives at School"

Use the mirror entity's state directly in automations:

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

---

## Privacy note

The integration continuously processes real GPS coordinates of the `device_tracker` entities you select. New installs default `Expose GPS coordinates` to **off** — only the zone name is published to entity attributes. However, the recorder still logs state-change timestamps unless you exclude the entities. See [Privacy](privacy.md) for the full picture, including how to exclude entities from the recorder and how to handle deletion requests.
