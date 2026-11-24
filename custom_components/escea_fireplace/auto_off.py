"""Maximum run time: turn the fire off once it has run for too long.

This only ever turns the fire off.

The clock starts when Home Assistant sees the fire on and stops when it sees
it off, so turning the fire off and on again starts a fresh count. Nothing is
saved over a restart: Home Assistant can't tell whether someone relit the
fire while it was down, so a fire that's on at startup is counted from
startup. After a restart a fire can run longer than the limit, but it's
never turned off early.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later

from .const import CONF_MAX_RUN_HOURS, EVENT_AUTO_OFF, LOGGER, UPDATE_INTERVAL
from .coordinator import EsceaConfigEntry


@callback
def async_setup_auto_off(hass: HomeAssistant, entry: EsceaConfigEntry) -> None:
    """Watch the fire if a maximum run time is set."""
    hours = int(entry.options.get(CONF_MAX_RUN_HOURS, 0))
    if not hours:
        return
    coordinator = entry.runtime_data
    unsub: CALLBACK_TYPE | None = None

    @callback
    def cancel() -> None:
        nonlocal unsub
        if unsub:
            unsub()
            unsub = None

    async def turn_off(_: datetime) -> None:
        nonlocal unsub
        unsub = None
        LOGGER.warning(
            "%s has run for %s hours, the maximum run time; turning it off",
            entry.title,
            hours,
        )
        try:
            await coordinator.async_turn_off()
        except HomeAssistantError as err:
            LOGGER.warning("Couldn't turn %s off, trying again: %s", entry.title, err)
            unsub = async_call_later(hass, UPDATE_INTERVAL, turn_off)
            return
        hass.bus.async_fire(
            EVENT_AUTO_OFF,
            {"entry_id": entry.entry_id, "name": entry.title, "hours": hours},
        )

    @callback
    def check() -> None:
        nonlocal unsub
        # A missed poll keeps the last reading, so it doesn't stop the clock.
        if not coordinator.data.status.is_on:
            cancel()
        elif unsub is None:
            unsub = async_call_later(hass, timedelta(hours=hours), turn_off)

    check()
    entry.async_on_unload(coordinator.async_add_listener(check))
    entry.async_on_unload(cancel)
