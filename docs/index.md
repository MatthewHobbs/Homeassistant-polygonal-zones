---
layout: page
title: Home
nav_order: 1
permalink: /
---

# Polygonal Zones for Home Assistant

Polygonal Zones gives you zones shaped like real places. Draw a property boundary, a school catchment or any other outline. Each tracked device then reports the zone it is in, such as `Home` or `School`, or `away`.

Home Assistant's own zones are circles. They do not fit an irregular plot or a catchment area. Polygonal Zones takes the shape you draw instead.

This is a spare-time community continuation of [MichelGerding/Homeassistant-polygonal-zones](https://github.com/MichelGerding/Homeassistant-polygonal-zones) and [MichelGerding/Homeassistant-polygonal-zones-addon](https://github.com/MichelGerding/Homeassistant-polygonal-zones-addon). Neither original project is maintained. The current versions are the [integration](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones) and the [add-on](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon).

## Two parts that work together

The **editor add-on** runs inside Home Assistant. You draw and name your zones on a map, and it saves them as a file called `zones.json`.

The **integration** is a HACS component. It reads those zones and creates a mirror entity for each device you choose, named `device_tracker.polygonal_zones_<name>`. The state of that entity is the zone the device is in, or `away`.

With add-on 0.7.0 and integration 1.16.0 or later, the add-on hands its file to Home Assistant for you. You confirm the discovered integration and choose your devices. There is no URL to copy.

Requirements: Home Assistant 2026.9.1 or later.

---

[Install both parts &rarr;](install.md){: .btn }
&nbsp;&nbsp;
[Zone file format reference &rarr;](ZONES_FORMAT.md){: .btn }
