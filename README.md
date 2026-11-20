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
  <b>Your Escea gas fireplace in Home Assistant and Apple Home.</b><br>
  On and off, temperature, Boost and Flame effect, <b>the fire's own timers</b> and its <b>diagnostics</b>. All local, no cloud.
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

## What you get

| | |
|---|---|
| **Thermostat** | Heat or off, target temperature (4–30 °C), and **Normal**, **Boost** or **Flame effect**. Works in Apple Home through HomeKit Bridge. |
| **Power switch and mode select** | For dashboards, buttons and voice assistants. |
| **The fire's own timers** | Both daily timers: turn them on or off and change their times, straight from Home Assistant. |
| **Diagnostics** | Gas drive, flue and room fan drive, pilot valve, thermal cut-out, controller temperature and more, from the fire's own diagnostics page. |
| **Lighting state** | "Lighting or shutting down" for the minute after it's turned on or off, when the fire ignores commands. Anything you change in that minute is applied as soon as it's ready. |
| **Finds itself** | Searches every network Home Assistant is on, offers new fires as they join the network, and follows the fire if its IP address changes. |
| **Repairs** | Tells you if the fire's clock has drifted (so its timers run late), or if another Escea integration is fighting over the network port. |
| **Safe by design** | Never re-sends an old command, so it can't re-light a fire someone turned off with the remote or the Escea app. Won't light the fire just because you picked a mode. Turning off is never refused. |

## Which integration is right for you?

| | This one | [Built-in Escea](https://www.home-assistant.io/integrations/escea/) | [Escea (local)](https://github.com/derekclapham/ha-escea) |
|---|---|---|---|
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
3. **Add the integration.** Leave the address blank to search, or type the fire's IP address. It may also pop up under **Discovered**.

That's it. On most fires the web page login is the serial number and PIN, which the fire reports itself, so the timers and diagnostics just work. If yours is different, you'll be asked.

### Requirements

- An Escea fireplace **connected by Ethernet** (these controllers have no Wi-Fi). If the Escea app works on your home Wi-Fi without the internet, this will too.
- Home Assistant on the **same network**, or able to reach the fire on UDP 3300 (and TCP 80 for timers and diagnostics). Search only works on the same network; across VLANs, type the IP address.
- Your **router must answer pings** from the LAN. The fire pings its gateway every 50 seconds and restarts its network connection if there's no reply.

## Entities

| Entity | Type | Notes |
|---|---|---|
| Fireplace | Climate | Heat/off, target, presets Normal / Boost / Flame effect |
| Power | Switch | |
| Mode | Select | Normal / Boost / Flame effect |
| Room temperature | Sensor | Measured by the fire |
| Lighting or shutting down | Binary sensor | On for about a minute after a power change |
| Timer 1, Timer 2 | Switch (config) | Needs the web page |
| Timer 1 on/off, Timer 2 on/off | Time (config) | Needs the web page |
| Clock offset | Sensor (diagnostic) | Minutes the fire's clock is ahead (+) or behind (−) |
| Gas drive, flue fan drive, room fan drive | Sensor (diagnostic) | % |
| Controller temperature | Sensor (diagnostic) | |
| Pilot valve, thermal cut-out | Binary sensor (diagnostic) | |
| Ready in, duct temperature, solenoid and gas valve current, ignition, B2/SV, B3, auxiliary, automation and flue fan override | Diagnostic, off by default | Turn on in the entity settings |

## How it works

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

## Troubleshooting

| Problem | Try |
|---|---|
| Search finds nothing | Type the IP address. Look in your router for a device whose MAC starts `AC:DE:48`. |
| Keeps going unavailable | Make sure no other Escea integration is installed. Make sure your router answers pings from the LAN. |
| Timers and diagnostics unavailable | Open `http://<fire's IP>` in a browser. If it doesn't load, turn the fire off at the wall for a minute. |
| Fire never gets an IP address | A known controller fault: power cycle it. If it recurs, set your DHCP server to broadcast its offers to the fire's MAC address. |

Turn on debug logging for `custom_components.escea_fireplace` and `aioescea`, and attach a diagnostics download to any issue.

## Credits

Built on [aioescea](https://github.com/olliemaller/aioescea). Thanks to [snikch/climate.escea](https://github.com/snikch/climate.escea) (Mal Curtis), [lazdavila/pescea](https://github.com/lazdavila/pescea) (Laz Davila) and [derekclapham/ha-escea](https://github.com/derekclapham/ha-escea) (Derek Clapham), whose work this builds on.

## Licence

[MIT](LICENSE)
