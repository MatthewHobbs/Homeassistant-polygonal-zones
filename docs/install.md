---
layout: page
title: Installation
nav_order: 2
permalink: /install/
---

# Installation

Polygonal Zones has two parts. The **app** is a map editor where you draw your zones. The **integration** turns those zones into entities Home Assistant can use.

You need both parts, unless you already have your zones in a GeoJSON file. In that case the integration alone is enough.

**Requirements:** Home Assistant 2026.9.1 or later.

Home Assistant now calls these **apps**. Some versions call them **add-ons**; it is the same thing, and the menus below use **app**.

---

## Step 1 — Install the app

The app is a map editor that runs inside Home Assistant. You draw polygons, give them names and save.

### 1a. Add the app repository

[![Add app repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FMatthewHobbs%2FHomeassistant-polygonal-zones-addon.git)

If the button does not work, add the repository by hand:

1. Open **Settings → Apps**, then choose **Install app**.
2. In the store, open the **⋮** menu at the top right and choose **Repositories**.
3. Paste `https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon` and choose **Add**.

### 1b. Install the app

Back in the store, find **Polygonal Zones** in the list and choose **Install**.

### 1c. Draw your zones

1. Open **Settings → Apps → Polygonal Zones** and choose **Start**.
2. Choose **Open Web UI**.
3. Choose the pentagon button on the right of the map.
4. Click on the map to place the corners of your zone. Click the first corner again to close the shape.
5. Type a name for the zone in the sidebar.
6. Choose **Save**. Unsaved changes are lost when the app restarts.

Repeat this for every zone you want.

The app saves your zones as `zones.json`. Version 0.7.0 and later can hand that file to Home Assistant for you, so there is no URL to copy and no port to open. Step 3 explains this.

---

## Step 2 — Install the integration

The integration watches your `device_tracker` entities and works out which zone each one is in.

### 2a. Add it through HACS

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MatthewHobbs&repository=Homeassistant-polygonal-zones&category=integration)

If the button does not work:

1. Open **HACS** in the sidebar.
2. Open the **⋮** menu and choose **Custom repositories**.
3. Paste `https://github.com/MatthewHobbs/Homeassistant-polygonal-zones` and set the category to **Integration**.
4. Choose **Add**, then find **Polygonal Zones** in HACS and choose **Download**.

### 2b. Restart Home Assistant

Restart Home Assistant before you continue. Open **Settings → System → Restart**.

---

## Step 3 — Connect the two parts

### Automatic setup

This works with app 0.7.0 or later and integration 1.16.0 or later, on the same machine.

1. The app tells Home Assistant where to find your zones each time it starts.
2. Open **Settings → Devices & services**. A **Polygonal Zones** entry appears as discovered.
3. Choose **Configure** to accept it. There is no URL to type, no port to open and no token to copy.
4. Open the new entry's **⋮** menu and choose **Reconfigure**.
5. Choose the `device_tracker` entities you want to follow.
6. Tick the box confirming that everyone being tracked has been told. The form will not continue without it.

If no entry appears, restart the app once. Its log shows what it sent to Home Assistant.

### Manual setup

Use this if the automatic setup does not appear. It also covers an app on another machine, an older integration, or your own GeoJSON file.

1. Open **Settings → Apps → Polygonal Zones → Network** and give the app host port `8000`. Restart the app.
2. Open the app's **Configuration** tab and set **`save_token`** to a long random value. Without it the app refuses every request from outside Home Assistant.
3. Open **Settings → Devices & services → Add Integration** and search for **Polygonal Zones**.
4. Enter the zones URL, or a path inside `/config`. For the app that is `http://<app-LAN-IP>:8000/zones.json`.
5. Turn on **Allow private-network URLs (LAN)**, and enter the token as **App save token**. These fields are advanced, so turn on Advanced mode in your user profile to see them.
6. Choose your `device_tracker` entities and tick the tracking notice.

Use the app's LAN IP address, not a name. A plain name such as `homeassistant` receives no token, so the app answers 403. `.local` names are unreliable here, and `localhost` is always refused. The port carries no encryption, so use it only on a network you trust.

`Allow private-network URLs` exists because the integration blocks private addresses by default. Without the option, Home Assistant refuses to fetch anything on your home network, including this app.

---

## Step 4 — Check it worked

Open **Developer Tools → States** and find `device_tracker.polygonal_zones_*`. Each tracked device gets one entity. The state is a zone name, or `away` when the device is outside every zone.

States are `unknown` until the device reports a position. A device that has not moved for a while may wait. See [Troubleshooting](troubleshooting.md) if it stays `unknown`.

---

## Using the result

Use `device_tracker.polygonal_zones_<name>` in automations. The README has a worked example under [Usage](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones#usage).

---

## Removing it

1. Open **Settings → Devices & services → Polygonal Zones**, open the **⋮** menu and choose **Delete**.
2. Remove the integration in HACS.
3. If **Download the GeoJSON files** was on, delete `<config>/polygonal_zones/<entry_id>.json`. The entry id is part of the file name. Leave any other file in that folder alone.
4. Uninstall the app separately if you no longer want the editor.

---

## Privacy

The integration reads the position of the `device_tracker` entities you choose. **Expose GPS coordinates** is off for new installs, so only the zone name is published.

Home Assistant's recorder still stores when a device enters and leaves a zone, unless you exclude these entities. See [Privacy](privacy.md).
