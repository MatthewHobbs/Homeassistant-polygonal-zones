---
layout: page
title: Home
nav_order: 1
permalink: /
---

# Polygonal Zones for Home Assistant

Polygonal Zones lets you define irregular, polygon-shaped zones in Home Assistant and track `device_tracker` entities against them. Where HA's built-in circular zones don't fit — an oddly shaped property, a school catchment, a neighbourhood boundary — you draw the actual shape and get an entity whose state is simply the zone name (e.g. `Home`, `School`, `Park`) or `away`.

> **Fork Notice**
>
> Polygonal Zones is a community-maintained continuation of the original [MichelGerding/Homeassistant-polygonal-zones](https://github.com/MichelGerding/Homeassistant-polygonal-zones) and [MichelGerding/Homeassistant-polygonal-zones-addon](https://github.com/MichelGerding/Homeassistant-polygonal-zones-addon), both of which are no longer actively maintained. Development continues here, run as a spare-time community project.
>
> Integration: [MatthewHobbs/Homeassistant-polygonal-zones](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones)
>
> Add-on: [MatthewHobbs/Homeassistant-polygonal-zones-addon](https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon)

## Two paired components

This project is made up of two pieces that work together:

**Add-on — Polygonal Zones Editor**
A Home Assistant add-on (Starlette web app + Leaflet map) where you draw zones on a map, name them, and hit Save. It stores your zones as a `zones.json` file and serves it over HTTP at `http://<your-ha-host>:8000/zones.json`.

**Integration — Polygonal Zones**
A HACS custom integration (pure Python) that watches `device_tracker` entities and resolves each one against your polygon zones. It reads the `zones.json` produced by the add-on and creates a mirror entity (`device_tracker.polygonal_zones_<name>`) whose state is whichever zone the device is currently inside, or `away`.

The typical setup is: install the add-on to draw your zones, then point the integration at the add-on's `zones.json` URL.

**Requirements:** Home Assistant 2026.7.1 or later (the integration runs on Python 3.14, which ships with HA OS/Supervised — nothing extra to install).

---

[Install both components &rarr;](install.md){: .btn }
&nbsp;&nbsp;
[Zone file format reference &rarr;](ZONES_FORMAT.md){: .btn }
