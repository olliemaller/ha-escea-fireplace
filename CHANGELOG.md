# Changelog

## 0.3.0

Released 25 November 2026. Needs aioescea 0.1.4.

**Added**

- Maximum run time (all fires): an option, off by default, that turns the fire off once it has been on for 1 to 12 hours. It only ever turns the fire off. The count starts when Home Assistant sees the fire on and starts again whenever it's turned off and on. Nothing is saved over a restart, so a fire that's on when Home Assistant starts is counted from then: it can run longer than the limit after a restart, but it's never turned off early. When it acts it logs a warning and fires an `escea_fireplace_auto_off` event. Wi-Fi fires now have a Configure page for this.
- Fault event (Wi-Fi fires): `ignition_failed` when the fire starts retrying a failed lighting, and `fault` when it goes into error or stores a new error. Shows in the logbook and can trigger a notification.

**Docs**

- How to count run hours and estimate gas use with Home Assistant's History stats and Template helpers, and automation examples for the new event and the maximum run time.

## 0.2.3

Released 24 November 2026. Needs aioescea 0.1.4.

**Fixed**

- Saving a timer could turn the fire back on. The timer form on the fire's web page also carries its power switch, and the power was read once, before a web login that can take a minute. If the fire was turned off in that time, the save turned it back on. The power is now read again right before the form is sent (and again before a resend after an expired login), and if the fire was turned on or off since the save started, nothing is sent and you get an error asking you to try again.
- Saving one timer could undo a change made to the other in the Escea app, because the other timer came from a reading up to 45 minutes old. Both timers are now read fresh as part of the save.
- On Wi-Fi fires, choosing Boost or Flame effect checks whether the fire is on by asking it, not from the last 30 second poll, since either would light a fire that had been turned off since.
- Saving a timer while the fire can't be reached gives the usual "didn't answer" message instead of a raw error.
- After the fire moves to a new IP address, the device page's link to its web page follows it.

**Docs**

- The temperature range is right for Wi-Fi fires (10-38 °C). New sections for installing through HACS or by hand, debug logging, diagnostics, troubleshooting, what it's been tested with, and getting help. New security policy, contributing guide and bug report form.

**Other**

- The tests run on macOS too, and the checks fail if the pinned aioescea isn't on PyPI instead of quietly testing its unreleased main branch.

## 0.2.2

**Fixed**

- The web page login still timed out on a real fire after 0.2.1, so timers, the clock and diagnostics stayed unavailable. The fire's web server only reads the first network packet of a request, and the login form arrived in a second one. aioescea 0.1.3 sends the whole request in one packet.

## 0.2.1

**Fixed**

- A correct web page login (serial number and PIN) was reported as "didn't answer" on fires whose web page is slow, so timers and diagnostics couldn't be set up. The web page now gets 30 s per page and 60 s to log in (aioescea 0.1.2), and a login that can't be checked during setup is saved anyway. If it's wrong, the first web page read asks you to fix it.

**New**

- **Reconfigure** can now add or change the web page login, so a fire added with the web page skipped can get timers and diagnostics later without removing it.

## 0.2.0

- New **Read web page now** button (Ethernet fires): reads the timers, clock
  and diagnostics straight away instead of waiting up to 10 minutes. It also
  clears any backoff after the page struggled.
- In flame effect mode the thermostat shows **idle** rather than heating,
  since flame effect gives very little heat.

## 0.1.2

- Fixed: when asked for the web page login while adding a fire, leaving the
  password blank to skip it failed with an error, because the username box
  is filled in for you. A blank password now skips it, as the form says.
- Every module is fully tested (CI fails below 95%) and type checked with
  `mypy --strict`, and `quality_scale.yaml` records where the integration
  stands against Home Assistant's quality scale.
- On Home Assistant 2026.10 and later, the config flow uses `probatio`, the
  schema library Home Assistant moved to.
- Docs: options, known limitations, and removing the integration.

## 0.1.1

Fixes, and needs aioescea 0.1.1.

- Wi-Fi (Generation 3) fires are now found by DHCP, and a known one that
  moves to a new address is updated automatically. Before, DHCP only knew
  how to talk to Ethernet fires.
- Turning off a fire that's already off (say, a nightly "make sure it's off"
  automation) no longer blocks turning it on for 66 seconds.
- The fire's web page is read in the background after setup. A slow page
  could hold up the status poll, and the refresh after a command, for 10
  seconds or more.
- Saving a timer after the web login has expired logs in again instead of
  failing.
- Half degrees held while the fire lights now round up (22.5 °C sets 23 °C).
- Diagnostics no longer include the serial number from a Wi-Fi fire's
  status.
- The web page options are hidden for Wi-Fi fires, which have no web page.
- The Wi-Fi fire check when adding by address gives up after 5 seconds
  instead of 10.
- Manifest categories (`climate.thermostats_heating`), and brand images
  trimmed to Home Assistant's rules.

## 0.1.0

First release. A rebuild of [snikch/climate.escea](https://github.com/snikch/climate.escea) on the new [aioescea](https://github.com/olliemaller/aioescea) library.

- **Generation 3 Wi-Fi fires** through Escea's NCAPI: on/off, temperature (10-38 °C), Boost and Flame effect, plus what the fire is doing (starting, igniting, heating, pilot only, shutting down, error), whether it can hear its remote, and stored errors.
- Set up from the UI: search every network, type an address, or accept a fire found when it joins the network (DHCP, MAC `AC:DE:48`).
- Thermostat with Normal, Boost and Flame effect presets, plus a power switch, mode select and room temperature sensor.
- The fire's two built-in timers, as switches and times you can change.
- The fire's diagnostics page as sensors: gas drive, fan drives, pilot valve, thermal cut-out, controller temperature and more.
- Logs in to the fire's web page with its serial number and PIN automatically.
- Holds temperature and mode changes made while the fire is lighting and sends them when it's ready. Drops them if the fire is turned off.
- Never re-sends an old command, so it can't re-light a fire turned off with the remote or app.
- Refuses Boost or Flame effect while the fire is off, since that would light it.
- Follows the fire to a new IP address.
- Repairs issues for a drifting fire clock, a busy UDP port 3300, or another Escea integration installed.
- Diagnostics download with the login, PIN and serial number removed.
- Reconfigure (change address), reauthenticate (web login) and options (web page on/off and how often).
