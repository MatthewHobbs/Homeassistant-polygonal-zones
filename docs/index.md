---
layout: page
title: Home
nav_order: 1
permalink: /
---

# Polygonal Zones for Home Assistant

Polygonal Zones gives you zones shaped like real places. Draw a property boundary, a school catchment or any other outline. Each tracked device then reports the zone it is in, such as `Home` or `School`, or `away`.

Home Assistant's own zones are circles. They do not fit an irregular plot or a catchment area. Polygonal Zones takes the shape you draw instead.

This is a spare-time community continuation of [MichelGerding/Homeassistant-polygonal-zones](https://github.com/MichelGerding/Homeassistant-polygonal-zones) and [MichelGerding/Homeassistant-polygonal-zones-addon](https://github.com/MichelGerding/Homeassistant-polygonal-zones-addon). Neither original project is maintained. The current versions are the [integration](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones) and the [app](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon).

## Two parts that work together

The **editor app** runs inside Home Assistant. You draw zones on a map, give them names, and save.

The **integration** watches the phones, cars or trackers you choose, and gives each one a zone name: `Home`, `School`, or `away` when it is outside them all.

Install both of the current versions and they find each other. You confirm the discovered entry and tick your devices; there is no address, port or password to supply.

Requirements: Home Assistant 2026.9.1 or later. The app needs a 64-bit installation (`aarch64` or `amd64`); 32-bit is not supported.

---

[Install both parts &rarr;](install.md){: .btn }
&nbsp;&nbsp;
[Zone file format reference &rarr;](ZONES_FORMAT.md){: .btn }
