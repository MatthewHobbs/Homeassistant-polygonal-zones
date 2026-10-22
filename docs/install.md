---
layout: page
title: Installation
nav_order: 2
permalink: /install/
---

# Installation

Install the **add-on first**, then the **integration**. The add-on draws your zones and serves `zones.json`; the integration reads that file. You need both.

**Requirements:** Home Assistant 2026.7.4 or later.

---

## Step 1 — Add-on: Polygonal Zones Editor

The add-on is a map editor inside Home Assistant. Draw polygons, name them and save; the result is the `zones.json` file the integration reads.

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

### 1d. Open the LAN port and set a token

The integration reads `zones.json` over the network, not through the sidebar, so the add-on's direct port must be open and protected:

1. **Settings → Add-ons → Polygonal Zones → Network**: assign host port `8000`, then restart the add-on.
2. **Settings → Add-ons → Polygonal Zones → Configuration**: set **`save_token`** to a long random value. The add-on refuses every request from outside Home Assistant that does not carry it.

The zones are then served at:

```
http://<your-ha-host>:8000/zones.json
```

You need this URL and the token in Step 2. Use the host's IP address, `localhost` or a `.local` name in the URL: the integration sends the token only to those, so a plain DNS name such as `homeassistant` gets a 403. The LAN port is plain HTTP, so use it only on a network you trust. To keep the editor one click away, enable **Show in sidebar** on the Configuration tab.

---

## Step 2 — Integration: Polygonal Zones

The integration watches your `device_tracker` entities and resolves their GPS position against your zones.

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

| Field                              | What to enter                                                                                                                                         |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **URLs of GeoJSON files**          | `http://<your-ha-host>:8000/zones.json` — the add-on URL from Step 1d.                                                                                |
| **Add-on save token**              | _(advanced)_ The `save_token` you set in Step 1d.                                                                                                     |
| **Entities**                       | The `device_tracker.*` entities you want to track against your zones.                                                                                 |
| **Tracking consent**               | A required checkbox: "I confirm everyone whose device I'm adding has been told it will be location-tracked." The form won't submit until you tick it. |
| **Prioritize order of zone files** | _(advanced)_ When a position matches zones from multiple files, prefer the earlier file.                                                              |
| **Download the GeoJSON files**     | _(advanced)_ Copies the remote file locally so you can mutate zones via automation actions.                                                           |

> **LAN URL.** The add-on URL is a private address, which the integration blocks by default as SSRF protection (SSRF is the server being tricked into fetching an internal address). Turn on **Allow private-network URLs (LAN)** in the advanced options (visible with Advanced mode on in your user profile). Loopback and link-local addresses stay blocked.

Click **Submit**. The integration creates one new entity per tracked device:

```
device_tracker.alice_phone  →  device_tracker.polygonal_zones_alice_phone
```

### 2e. Verify

Open **Developer Tools → States** and look for `device_tracker.polygonal_zones_*`. The state is a zone name or `away` once the source device has reported a GPS fix.

If the entity stays `unknown`, see [Troubleshooting](troubleshooting.md).

---

## Next steps

Use `device_tracker.polygonal_zones_<name>` (state: zone name or `away`) in automations. There is an example under [Usage in the README](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones#usage).

---

## Removing it

Settings → Devices & Services → Polygonal Zones → ⋮ → Delete, then remove the integration in HACS. If **Download the GeoJSON files** was on, also delete `<config>/polygonal_zones/<entry_id>.json` (the entry id is in the file name), which holds the downloaded zones; leave any other file you keep in that folder. Stop the add-on and uninstall it separately if you no longer need the editor.

---

## Privacy note

The integration processes the GPS position of the `device_tracker` entities you select. **Expose GPS coordinates** defaults to off for new installs, so only the zone name is published to attributes. The recorder still stores zone entry and exit times unless you exclude the entities; see [Privacy](privacy.md).
