"""Constants for the Escea Fireplace integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.const import Platform

DOMAIN = "escea_fireplace"
LOGGER = logging.getLogger(__package__)
MANUFACTURER = "Escea"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

CONF_SERIAL = "serial"
CONF_GENERATION = "generation"
#: Ethernet fires with the UDP protocol (and a web page for timers).
GEN2 = 2
#: Wi-Fi fires (from 2024) with Escea's NCAPI over HTTP.
GEN3 = 3
CONF_PIN = "pin"
CONF_MAC = "mac"
CONF_WEB_ENABLED = "web_enabled"
CONF_WEB_INTERVAL = "web_interval"

#: UDP status poll. The fire answers in milliseconds; 30 s keeps the remote
#: and app changes showing up quickly without loading the controller.
UPDATE_INTERVAL = timedelta(seconds=30)

#: The web page is fragile (one connection at a time, can stop answering
#: until the fire is power cycled), so it's read every few minutes at most.
DEFAULT_WEB_INTERVAL_MINUTES = 10
MIN_WEB_INTERVAL_MINUTES = 5
MAX_WEB_INTERVAL_MINUTES = 60
#: After this many failed web reads in a row, back off to the maximum.
WEB_MAX_BACKOFF = timedelta(hours=2)
#: Web values older than this are shown as unavailable, not stale.
WEB_STALE_AFTER = timedelta(minutes=45)

#: Failed status polls in a row before searching for the fire by serial
#: number, in case its DHCP address changed.
REDISCOVER_AFTER_FAILURES = 3

#: Fire clock drift (minutes) that raises a Repairs issue, since the fire's
#: own timers run on its clock.
CLOCK_DRIFT_MINUTES = 5

DISCOVERY_TIMEOUT = 5.0
NCAPI_PROBE_TIMEOUT = 5.0
DATA_TRANSPORT = f"{DOMAIN}_transport"
