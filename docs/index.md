---
layout: page
title: Home
nav_order: 1
permalink: /
---

# Polygonal Zones for Home Assistant

Define irregular, polygon-shaped zones and resolve `device_tracker` entities against them. Where HA's circular zones do not fit (an oddly shaped property, a school catchment), you draw the shape and get an entity whose state is the zone name (for example `Home` or `School`) or `away`.

Polygonal Zones is a spare-time community continuation of [MichelGerding/Homeassistant-polygonal-zones](https://github.com/MichelGerding/Homeassistant-polygonal-zones) and [MichelGerding/Homeassistant-polygonal-zones-addon](https://github.com/MichelGerding/Homeassistant-polygonal-zones-addon), neither of which is maintained. Current versions: [integration](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones) and [add-on](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon).

## Two paired components

The editor add-on is a Home Assistant add-on where you draw and name zones on a map. It saves them as `zones.json` and serves the file at `http://<your-ha-host>:8000/zones.json`.

The integration is a HACS custom integration. It reads that file and creates a mirror entity (`device_tracker.polygonal_zones_<name>`) for each tracked device, whose state is the zone the device is in, or `away`.

Install the add-on, then point the integration at its `zones.json` URL.

Requirements: Home Assistant 2026.9.1 or later.

---

[Install both components &rarr;](install.md){: .btn }
&nbsp;&nbsp;
[Zone file format reference &rarr;](ZONES_FORMAT.md){: .btn }
