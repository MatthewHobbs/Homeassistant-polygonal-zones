---
layout: page
title: Installation
nav_order: 2
permalink: /install/
---

# Installation

Polygonal Zones needs two pieces:

- the **Polygonal Zones Editor app**, where you draw your zones on a map;
- this **integration**, which watches your devices and works out which zone each one is in.

The app runs inside Home Assistant and hands your zones over on its own. Install both, confirm the connection, choose your devices — that is the whole job. No addresses, ports or passwords.

If you already have your zones as a GeoJSON file, from another tool or an older setup, you can skip the app and point the integration at that file instead. See [Using your own zones file](#using-your-own-zones-file).

**What you need**

- Home Assistant **2026.9.1** or later.
- The app, which needs a **64-bit** Home Assistant installation (`aarch64` or `amd64`). 32-bit is not supported.
- Something that reports where it is: a phone running the Home Assistant app, a car with a data connection, or a GPS tracker.

Home Assistant now calls these **apps**. Some versions call them **add-ons**; it is the same thing, and the pages here say **app**.

---

## Step 1 — Install the app, and draw a zone

[![Add app repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FMatthewHobbs%2FHomeassistant-polygonal-zones-addon.git)

If the button does not work, add the repository by hand: **Settings → Apps → Install app**, then the **⋮** menu at the top right, **Repositories**, and paste `https://github.com/MatthewHobbs/Homeassistant-polygonal-zones-addon`.

1. Find **Polygonal Zones** in the app store and choose **Install**, then **Start**.
2. Turn on **Watchdog** on the app's page, so it restarts itself if it stops.
3. Choose **Open Web UI**.
4. Choose the polygon button at the top of the map, then click each corner of the zone. Click the first corner again to close the shape.
5. Type a name — `Home`, `Work`, `School` — in the panel on the left.
6. Choose **Save**. Unsaved changes are lost when the app restarts.

Repeat for every zone you want. The app keeps them for you; you never have to copy a file or find an address.

---

## Step 2 — Install the integration

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MatthewHobbs&repository=Homeassistant-polygonal-zones&category=integration)

If the button does not work: open **HACS**, then the **⋮** menu, **Custom repositories**, paste `https://github.com/MatthewHobbs/Homeassistant-polygonal-zones`, set the category to **Integration**, choose **Add**, then find **Polygonal Zones** in HACS and choose **Download**.

Then restart Home Assistant: **Settings → System → Restart**.

---

## Step 3 — Connect the two, and choose your devices

This works with app 0.7.0 or later and integration 1.16.0 or later, on the same machine.

1. Open **Settings → Devices & services** and wait a minute.
2. A **Polygonal Zones** entry appears under **Discovered**. Choose **Configure** on it (some versions say **Confirm**).
3. Open the entry's **⋮** menu and choose **Reconfigure**.
4. Tick the devices you want followed.
5. Tick the box confirming that everyone being tracked has been told. The form does not continue without it.

Nothing to type: the app told Home Assistant where it is, and generated a password that only Home Assistant sees.

**No entry appeared?** Check the app is started, then restart it and look at its log: it says what it sent. If it still does not appear, use [setting up by hand](#if-you-have-to-set-it-up-by-hand).

---

## Step 4 — Check that it works

1. Open **Settings → Devices & services → Polygonal Zones**.
2. Open the device for the thing you are tracking. Its position line should read the name of your zone while it is inside it, and `away` when it leaves.

You can also see the same thing under **Settings → Devices & services → Entities**: one entity per tracked device, named `device_tracker.polygonal_zones_<name>`.

A device that has not reported a position yet shows `unknown`. That is normal until it does; a car that is asleep can take a while.

---

## If it does not work

| What you see                                    | What to do                                                                                                                                                                          |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Nothing under **Discovered**                    | The app must be installed and started before this integration can see it. Restart the app, then restart Home Assistant.                                                             |
| Set up, but the device always says `away`       | Check you ticked that device in **Reconfigure**, and that the zone was saved — it should be listed in the app.                                                                      |
| A device says `away` although it is inside      | The zone may be too small to be reliable, or the device's position may be rough. See [is this the right tool](https://matthewhobbs.github.io/Homeassistant-polygonal-zones-addon/). |
| Saving in the app says something went wrong     | Only happens after setting up by hand: the app's password and this integration's **App save token** disagree.                                                                       |
| Many extra devices called Polygonal Zones 1, 2… | An old version of this integration left them behind. Update, then delete the leftovers once by hand.                                                                                |

More detail, including the exact messages, is in [Troubleshooting](troubleshooting.md).

---

## If you have to set it up by hand

Only for the cases the automatic path cannot cover: an app older than 0.7.0, an integration older than 1.16.0, an app on another machine, or your own zones file.

You are joining the two pieces yourself, and three things have to agree: a port, a password and an address.

1. **Give the app a port.** **Settings → Apps → Polygonal Zones → Network**, host port `8000`, restart the app.
2. **Give the app a password.** On the app's **Configuration** page, set `save_token` to a long random value. Restart the app.
3. **Add the integration.** **Settings → Devices & services → Add integration → Polygonal Zones**.
4. **Tell it where the zones are.** `http://<app-address>:8000/zones.json`, where the address is the number that looks like `192.168.1.20`. Use the number, not a name such as `homeassistant`: this integration only sends the password to a number. `.local` names are unreliable and `localhost` is always refused.
5. **Allow your own network, and paste the password.** Turn on **Advanced mode** in your user profile if you cannot see these options. Turn on **Allow private-network URLs (LAN)**, and put the app's `save_token` in **App save token**.
6. **Choose your devices**, and tick the tracking notice.

The connection is not encrypted, so the password and your zones cross your home network in the clear. Use it only on a network you trust.

---

## Using your own zones file

Already have zones as GeoJSON from another tool, or a file you keep yourself? You do not need the app.

When adding the integration, give the address of the file instead of the app: a path inside `/config`, a `file://` path, or an `http(s)://` address. Everything after that is the same: choose your devices, and each one reports the zone it is in.

The [zone file format](ZONES_FORMAT.md) page describes what the file must contain.

---

## Removing it

1. **Settings → Devices & services → Polygonal Zones**, **⋮ → Delete**.
2. Remove the integration in HACS.
3. If **Download the GeoJSON files** was on, delete `<config>/polygonal_zones/<entry_id>.json`. Leave any other file in that folder alone.
4. Uninstall the app separately if you no longer want the editor.

---

## Privacy

The integration reads the position of the devices you choose. **Expose GPS coordinates** is off for new installs, so only the zone name is published. Home Assistant's recorder still stores when a device enters and leaves a zone unless you exclude these entities. See [Privacy](privacy.md).
