# Changelog

## 0.1.0

First release. A rebuild of [snikch/climate.escea](https://github.com/snikch/climate.escea) on the new [aioescea](https://github.com/olliemaller/aioescea) library.

- **Generation 3 Wi-Fi fires** through Escea's NCAPI: on/off, temperature (10–38 °C), Boost and Flame effect, plus what the fire is doing (starting, igniting, heating, pilot only, shutting down, error), whether it can hear its remote, and stored errors.
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
