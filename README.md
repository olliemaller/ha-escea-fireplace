<p align="center">
  <img src="https://raw.githubusercontent.com/olliemaller/ha-escea-fireplace/main/images/banner.png" alt="Escea Fireplace for Home Assistant" width="100%">
</p>

<p align="center">
  <a href="https://www.home-assistant.io/integrations/marketplace/"><img src="https://img.shields.io/badge/Marketplace-Custom-FFFFFF?style=for-the-badge&logo=homeassistant&logoColor=white&labelColor=000000" alt="Home Assistant Marketplace"></a>
  <a href="https://github.com/olliemaller/ha-escea-fireplace/releases"><img src="https://img.shields.io/github/v/release/olliemaller/ha-escea-fireplace?style=for-the-badge&color=FFFFFF&labelColor=000000" alt="Release"></a>
  <a href="https://github.com/olliemaller/ha-escea-fireplace/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/olliemaller/ha-escea-fireplace/validate.yml?branch=main&style=for-the-badge&label=checks&labelColor=000000" alt="Checks"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2025.8%2B-FFFFFF?style=for-the-badge&logo=homeassistant&logoColor=white&labelColor=000000" alt="Home Assistant 2025.8+">
  <a href="https://github.com/olliemaller/ha-escea-fireplace/blob/main/LICENSE"><img src="https://img.shields.io/github/license/olliemaller/ha-escea-fireplace?style=for-the-badge&color=FFFFFF&labelColor=000000" alt="Licence"></a>
</p>

<p align="center">
  <b>Your Escea fireplace in Home Assistant and Apple Home.</b><br>
  Ethernet <b>and the newer Wi-Fi fires</b>. On and off, temperature, Boost and Flame effect, the fire's own timers and its diagnostics. All local, no cloud.
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=olliemaller&repository=ha-escea-fireplace&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open in the Marketplace"></a>
  &nbsp;
  <a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=escea_fireplace"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Add integration"></a>
</p>

---

> [!IMPORTANT]
> **Unofficial.** Not affiliated with or endorsed by Escea. "Escea" is a trademark of its owner, used here only to describe compatibility.

> [!WARNING]
> **It controls a gas appliance.** Home Assistant can light the fire when nobody's in the room. Follow Escea's safety instructions, keep the area in front of the fire clear, and think before you automate lighting it.

## Which fires?

| | Generation 2 (Ethernet) | Generation 3 (Wi-Fi, from 2024) |
|---|---|---|
| How to tell | Network cable to the fire | Wi-Fi in the Escea Smartheat app; newer remote style |
| Talks over | Escea's UDP protocol (port 3300) | Escea's NCAPI (HTTP on port 80) |
| Setup | Found automatically | Turn on **Escea NCAPI Settings** in the Smartheat app, reserve its IP address, then enter the address |
| On/off, temperature, Boost, Flame effect | ✓ (4–30 °C) | ✓ (10–38 °C, 0.5 °C steps) |
| What the fire is doing (starting, igniting, heating, pilot only, shutting down, error) | | ✓ |
| Remote seen, stored errors | | ✓ |
| Fire's built-in timers, clock and diagnostics | ✓ | |

Both protocols come from Escea: the LAN protocol specification (v0.3, still current for Generation 2) and the Network Communication API (NCAPI, document 640051, 2024) for Generation 3.

## What you get

| | |
|---|---|
| **Thermostat** | Heat or off, target temperature (4–30 °C), and **Normal**, **Boost** or **Flame effect**. Works in Apple Home through HomeKit Bridge. |
| **Power switch and mode select** | For dashboards, buttons and voice assistants. |
| **The fire's own timers** | Both daily timers: turn them on or off and change their times, straight from Home Assistant. |
| **Diagnostics** | Gas drive, flue and room fan drive, pilot valve, thermal cut-out, controller temperature and more, from the fire's own diagnostics page. |
| **What it's doing** | Wi-Fi fires report starting, igniting, heating, pilot only, shutting down and errors, shown as the thermostat's action and a State sensor. Ethernet fires show "Lighting or shutting down" for the minute after a power change, when they ignore commands; anything you change in that minute is applied as soon as it's ready. |
| **Finds itself** | Searches every network Home Assistant is on, offers new fires as they join the network, and follows the fire if its IP address changes. |
| **Repairs** | Tells you if the fire's clock has drifted (so its timers run late), or if another Escea integration is fighting over the network port. |
| **Safe by design** | Never re-sends an old command, so it can't re-light a fire someone turned off with the remote or the Escea app. Won't light the fire just because you picked a mode. Turning off is never refused. |

## Which integration is right for you?

| | This one | [Built-in Escea](https://www.home-assistant.io/integrations/escea/) | [Escea (local)](https://github.com/derekclapham/ha-escea) |
|---|---|---|---|
| Wi-Fi (Generation 3) fires | ✓ | | |
| On, off, temperature | ✓ | ✓ | ✓ |
| Boost and Flame effect | Preset and select | Fan mode | Preset |
| Fire's timers | ✓ | | ✓ |
| Diagnostics page | ✓ | | ✓ |
| Finds new fires automatically | ✓ (DHCP) | ✓ (broadcast) | |
| Follows IP address changes | ✓ | ✓ | |
| Clock drift warning | ✓ | | |
| Can't re-light a fire turned off elsewhere | ✓ | [No](https://github.com/lazdavila/pescea/issues/8) | ✓ |

**Use only one.** Escea fires always reply to UDP port 3300, so only one program per computer can hear them. Remove the built-in Escea integration (and the old snikch custom component) before adding this one. This integration warns you in Repairs if it finds another.

## Quick start

1. **Install** from the Marketplace (Home Assistant 2026.11+) or HACS with the button above, then restart Home Assistant.
2. **Remove** any other Escea integration and restart again.
3. **Add the integration.** Leave the address blank to search, or type the fire's IP address. Ethernet fires may also pop up under **Discovered**.

That's it for Ethernet fires. On most of them the web page login is the serial number and PIN, which the fire reports itself, so the timers and diagnostics just work. If yours is different, you'll be asked.

**Wi-Fi fires** need two things first, both from Escea's instructions:

1. In the **Escea Smartheat app**, connect to the fire by Bluetooth (you need its PIN), go to **Fire Settings** and turn on **Escea NCAPI Settings**. If it isn't there, use **Check for Updates** on the same page (firmware 1.5.9 or later).
2. In your router, **reserve the fire's IP address** (shown with its MAC on the app's Wi-Fi settings page). The fire always uses DHCP and can't be found by searching.

### Requirements

- **Ethernet fires:** Home Assistant on the same network, or able to reach the fire on UDP 3300 (and TCP 80 for timers and diagnostics). Search only works on the same network; across VLANs, type the IP address. Your **router must answer pings** from the LAN: the fire pings its gateway every 50 seconds and restarts its network connection if there's no reply.
- **Wi-Fi fires:** 2.4 GHz Wi-Fi, firmware 1.5.9 or later, NCAPI turned on, a DHCP reservation, and Home Assistant able to reach the fire on TCP 80.

## Entities

| Entity | Type | Notes |
|---|---|---|
| Fireplace | Climate | Heat/off, target, presets Normal / Boost / Flame effect |
| Power | Switch | |
| Mode | Select | Normal / Boost / Flame effect |
| Room temperature | Sensor | Measured by the fire |
| State | Sensor | Wi-Fi fires: off, starting, igniting, heating, pilot only, shutting down, error… |
| Remote | Binary sensor (diagnostic) | Wi-Fi fires: the fire can hear its remote (it needs to, to start) |
| Stored errors | Binary sensor | Wi-Fi fires: errors to check on the remote or app |
| Lighting or shutting down | Binary sensor | Ethernet fires: on for about a minute after a power change |
| Timer 1, Timer 2 | Switch (config) | Ethernet fires, needs the web page |
| Timer 1 on/off, Timer 2 on/off | Time (config) | Ethernet fires, needs the web page |
| Read web page now | Button (diagnostic) | Ethernet fires: reads the timers, clock and diagnostics straight away |
| Clock offset | Sensor (diagnostic) | Ethernet fires: minutes the fire's clock is ahead (+) or behind (−) |
| Gas drive, flue fan drive, room fan drive | Sensor (diagnostic) | Ethernet fires, % |
| Controller temperature | Sensor (diagnostic) | Ethernet fires |
| Pilot valve, thermal cut-out | Binary sensor (diagnostic) | Ethernet fires |
| Ready in, duct temperature, solenoid and gas valve current, ignition, B2/SV, B3, auxiliary, automation and flue fan override | Diagnostic, off by default | Ethernet fires. Turn on in the entity settings |

Mode and the thermostat's presets are on gas fires only. In flame effect mode the thermostat shows **idle** rather than heating, since flame effect is mostly for looks.

## How it works

### Wi-Fi fires

- The fire's state is read over NCAPI every 30 seconds, and changes are sent as one request each. Requests are spaced out, since the fire refuses requests that come too fast.
- If the fire can't hear its remote, the room temperature shows as unknown rather than an old reading.

### Ethernet fires

- **Live control and status** use the fire's UDP protocol on port 3300, polled every 30 seconds. Changes from the remote or app show up within 30 seconds.
- **Timers, clock and diagnostics** come from the fire's web page on port 80, read every 10 minutes (change it in **Configure**, or turn it off). The web server can only handle the odd request and stops answering if pushed, so it's read gently and backed off if it struggles. If it hasn't been read for 45 minutes, those entities show unavailable rather than an old value.
- **After it's turned on or off, the fire ignores commands for about 66 seconds** while it lights or purges. Temperature and mode changes in that time are held and sent when it's ready, as long as the fire is still on. Nothing is ever held for a fire that's been turned off, and turning on is never held.
- **Choosing Boost or Flame effect while the fire is off would light it** (that's how Escea fires work), so it's refused. Turn it on first; you can pick the mode straight away.

## Automations

Warm the lounge before you get home, but only if someone's home:

```yaml
triggers:
  - trigger: zone
    entity_id: person.alex
    zone: zone.home
    event: enter
conditions:
  - condition: numeric_state
    entity_id: sensor.escea_123456_room_temperature
    below: 18
actions:
  - action: climate.set_temperature
    target:
      entity_id: climate.escea_123456
    data:
      hvac_mode: heat
      temperature: 22
```

Turn it off when everyone leaves:

```yaml
triggers:
  - trigger: state
    entity_id: zone.home
    to: "0"
actions:
  - action: climate.turn_off
    target:
      entity_id: climate.escea_123456
```

## Options

Under **Settings → Devices & services → Escea Fireplace → Configure** (Ethernet fires only):

| Option | Default | What it does |
|---|---|---|
| Read the fire's web page | On | Timers, clock and diagnostics. Turn it off if the web page gives you trouble; control carries on over UDP. |
| Minutes between reads | 10 | 5 to 60. The web server is fragile, so keep this at 10 unless you have a reason. |

When adding an Ethernet fire you may be asked for the **web page login** (username and password). It's usually the serial number and PIN, tried for you. Leave the password blank to skip it. To add or change it later, open the fireplace's **⋮ → Reconfigure** and enter the password (leave it blank to keep the current one).

The fire's web page is slow, often 10–20 seconds a page. If it doesn't answer while you're adding the fire, the login is saved anyway and checked on the first read; if it's wrong, Home Assistant asks you to fix it.

## Known limitations

- **Ethernet fires:** only one program per host can use UDP port 3300, so this can't run alongside another Escea integration, or alongside a second Home Assistant on the same machine.
- **Ethernet fires** ignore commands for about 66 seconds after turning on or off. Temperature and mode are held until then; turning on again isn't.
- **Wi-Fi fires** have no timers or diagnostics through Escea's API, and can't be found by searching: they need a DHCP reservation.
- Fan boost and flame effect are on gas fires only.
- The fire's clock can't be set from Home Assistant. If it drifts, a Repairs issue says so; set it on the remote.


| Problem | Try |
|---|---|
| Search finds nothing | Type the IP address. Ethernet fires' MAC addresses start `AC:DE:48`. Wi-Fi fires are never found by searching. |
| Wi-Fi fire won't add | Check Escea NCAPI Settings is on in the Smartheat app, and open `http://<fire's IP>/` in a browser: it should show a short block of JSON. |
| Wi-Fi fire won't light | Check the **Remote** sensor: the fire needs to hear its remote to start. |
| Keeps going unavailable | Make sure no other Escea integration is installed. Make sure your router answers pings from the LAN. |
| Timers and diagnostics unavailable | Open `http://<fire's IP>` in a browser. If it doesn't load, turn the fire off at the wall for a minute. |
| Fire never gets an IP address | A known controller fault: power cycle it. If it recurs, set your DHCP server to broadcast its offers to the fire's MAC address. |

Turn on debug logging for `custom_components.escea_fireplace` and `aioescea`, and attach a diagnostics download to any issue.

## Removing the integration

1. Go to **Settings → Devices & services → Escea Fireplace**, open the **⋮** menu on the fire and choose **Delete**.
2. If you installed it through HACS, remove it there too, then restart Home Assistant.

The fire itself is untouched: its timers, clock and settings stay as they were.

## Credits

Built on [aioescea](https://github.com/olliemaller/aioescea). Thanks to [snikch/climate.escea](https://github.com/snikch/climate.escea) (Mal Curtis), [lazdavila/pescea](https://github.com/lazdavila/pescea) (Laz Davila) and [derekclapham/ha-escea](https://github.com/derekclapham/ha-escea) (Derek Clapham), whose work this builds on.

## Licence

[MIT](LICENSE)
