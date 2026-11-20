"""Tests for setup, entities and control."""

from __future__ import annotations

import asyncio
from datetime import time as dt_time, timedelta
from unittest.mock import patch

from aioescea.protocol import Command
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.escea_fireplace.const import CONF_WEB_ENABLED, DOMAIN
from custom_components.escea_fireplace.coordinator import clock_drift_minutes
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.components.diagnostics import REDACTED
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_HOST,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir

from .conftest import SERIAL, FakeWeb
from .fake_fire import FakeFire

CLIMATE = f"climate.escea_{SERIAL}"
POWER = f"switch.escea_{SERIAL}_power"
MODE = f"select.escea_{SERIAL}_mode"
ROOM = f"sensor.escea_{SERIAL}_room_temperature"
TIMER1 = f"switch.escea_{SERIAL}_timer_1"
TIMER1_ON = f"time.escea_{SERIAL}_timer_1_on"
GAS = f"sensor.escea_{SERIAL}_gas_drive"
PILOT = f"binary_sensor.escea_{SERIAL}_pilot_valve"
BUSY = f"binary_sensor.escea_{SERIAL}_lighting_or_shutting_down"


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_setup_and_states(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire
) -> None:
    """Entities show the fire's state."""
    assert loaded.state is ConfigEntryState.LOADED
    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.OFF
    assert state.attributes["current_temperature"] == 18
    assert state.attributes[ATTR_TEMPERATURE] == 21
    assert state.attributes[ATTR_PRESET_MODE] == "normal"
    assert hass.states.get(POWER).state == STATE_OFF
    assert hass.states.get(MODE).state == "normal"
    assert hass.states.get(ROOM).state == "18"
    assert hass.states.get(TIMER1).state == STATE_ON
    assert hass.states.get(TIMER1_ON).state == "06:55:00"
    assert hass.states.get(GAS).state == "23"
    assert hass.states.get(PILOT).state == STATE_ON
    assert hass.states.get(BUSY).state == STATE_OFF


async def test_turn_on_and_off(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire
) -> None:
    """Heat lights the fire and starts the lighting window; off always works."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert fake_fire.state.is_on
    assert hass.states.get(CLIMATE).state == HVACMode.HEAT
    assert hass.states.get(BUSY).state == STATE_ON

    await hass.services.async_call(
        "switch", SERVICE_TURN_OFF, {ATTR_ENTITY_ID: POWER}, blocking=True
    )
    assert not fake_fire.state.is_on

    with pytest.raises(HomeAssistantError, match="still lighting"):
        await hass.services.async_call(
            "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: POWER}, blocking=True
        )


async def test_commands_held_while_lighting(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire
) -> None:
    """Temperature and mode chosen while it lights are sent once it's ready."""
    coordinator = loaded.runtime_data
    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: CLIMATE}, blocking=True
    )
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_TEMPERATURE: 25},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: MODE, "option": "boost"},
        blocking=True,
    )
    assert fake_fire.state.target == 21  # not sent yet
    assert not fake_fire.state.fan_boost
    state = hass.states.get(CLIMATE)
    assert state.attributes[ATTR_TEMPERATURE] == 25  # shown as held
    assert state.attributes[ATTR_PRESET_MODE] == "boost"

    coordinator.fireplace._busy_until = 0  # the 66 s are up
    await _refresh(hass, loaded)
    assert fake_fire.state.target == 25
    assert fake_fire.state.fan_boost
    assert hass.states.get(MODE).state == "boost"


async def test_held_commands_dropped_if_fire_turned_off(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire
) -> None:
    """If the remote turns the fire off while it lights, nothing is sent."""
    coordinator = loaded.runtime_data
    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: CLIMATE}, blocking=True
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: MODE, "option": "flame_effect"},
        blocking=True,
    )
    fake_fire.state.is_on = False  # the remote
    coordinator.fireplace._busy_until = 0
    fake_fire.received.clear()
    await _refresh(hass, loaded)
    assert fake_fire.received == [Command.STATUS_PLEASE]
    assert not fake_fire.state.is_on


async def test_missed_poll_never_relights(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire
) -> None:
    """The pescea #8 bug: a fire turned off by the app stays off."""
    fake_fire.state.is_on = True
    await _refresh(hass, loaded)
    assert hass.states.get(CLIMATE).state == HVACMode.HEAT

    fake_fire.state.is_on = False  # the Escea app
    fake_fire.drop = 100
    await _refresh(hass, loaded)
    assert hass.states.get(CLIMATE).state == STATE_UNAVAILABLE

    fake_fire.drop = 0
    fake_fire.received.clear()
    await _refresh(hass, loaded)
    assert hass.states.get(CLIMATE).state == HVACMode.OFF
    assert Command.POWER_ON not in fake_fire.received
    assert set(fake_fire.received) <= {Command.STATUS_PLEASE, Command.SEARCH_FOR_FIRES}


async def test_mode_while_off_refused(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire
) -> None:
    """Boost while off would light the fire."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: CLIMATE, ATTR_PRESET_MODE: "boost"},
            blocking=True,
        )
    assert not fake_fire.state.is_on
    assert Command.FAN_BOOST_ON not in fake_fire.received


async def test_set_mode_when_on(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire
) -> None:
    """Modes change straight away when the fire is on and ready."""
    fake_fire.state.is_on = True
    await _refresh(hass, loaded)
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_PRESET_MODE: "flame_effect"},
        blocking=True,
    )
    assert fake_fire.state.flame_effect
    assert not fake_fire.state.fan_boost


async def test_timer(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire, fake_web: FakeWeb
) -> None:
    """Timers save through the web page without touching the power."""
    await hass.services.async_call(
        "time",
        "set_value",
        {ATTR_ENTITY_ID: TIMER1_ON, "time": "06:30:00"},
        blocking=True,
    )
    await hass.services.async_call(
        "switch", SERVICE_TURN_OFF, {ATTR_ENTITY_ID: TIMER1}, blocking=True
    )
    assert fake_web.timers[1] == ["06:30", "08:00", False]
    assert all(dict(save)["ON_OFF_SWITCH"] == "Off" for save in fake_web.saves)
    assert not fake_fire.state.is_on
    assert hass.states.get(TIMER1_ON).state == "06:30:00"
    assert hass.states.get(TIMER1).state == STATE_OFF


async def test_web_down_keeps_control(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    fake_web: FakeWeb,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Web entities go unavailable when stale; UDP entities carry on."""
    fake_web.reachable = False
    freezer.tick(timedelta(hours=1))
    await _refresh(hass, loaded)
    assert hass.states.get(GAS).state == STATE_UNAVAILABLE
    assert hass.states.get(TIMER1).state == STATE_UNAVAILABLE
    assert hass.states.get(CLIMATE).state == HVACMode.OFF


async def test_web_disabled(
    hass: HomeAssistant, entry: MockConfigEntry, fake_fire: FakeFire, fake_web: FakeWeb
) -> None:
    """With the web page off, no timer or diagnostic entities."""
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options={CONF_WEB_ENABLED: False})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(CLIMATE)
    assert hass.states.get(TIMER1) is None
    assert hass.states.get(GAS) is None


async def test_clock_drift_issue(
    hass: HomeAssistant, entry: MockConfigEntry, fake_fire: FakeFire, fake_web: FakeWeb
) -> None:
    """A fire clock out by minutes raises a Repairs issue."""
    with patch(
        "custom_components.escea_fireplace.coordinator.clock_drift_minutes",
        return_value=12,
    ):
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"clock_drift_{SERIAL}")
    assert issue is not None
    assert issue.translation_placeholders["minutes"] == "12"


def test_clock_drift_maths() -> None:
    """Drift handles midnight both ways."""
    from datetime import datetime

    now = datetime(2026, 11, 20, 23, 58)
    assert clock_drift_minutes(dt_time(0, 3), now) == 5
    assert clock_drift_minutes(dt_time(23, 50), now) == -8
    assert clock_drift_minutes(None, now) is None


async def test_rediscovers_new_address(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire
) -> None:
    """After repeated failures it searches by serial and saves the new address."""
    coordinator = loaded.runtime_data
    coordinator.fireplace.host = "127.0.0.3"  # pretend the lease moved
    for _ in range(3):
        await _refresh(hass, loaded)
    assert loaded.data[CONF_HOST] == "127.0.0.2"
    await _refresh(hass, loaded)
    assert hass.states.get(CLIMATE).state == HVACMode.OFF


async def test_port_in_use(
    hass: HomeAssistant, entry: MockConfigEntry, udp_port: int, fake_fire: FakeFire
) -> None:
    """Another program on UDP 3300 raises a Repairs issue."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", udp_port))
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert ir.async_get(hass).async_get_issue(DOMAIN, "port_in_use")


async def test_conflict_with_core_escea(
    hass: HomeAssistant, entry: MockConfigEntry, fake_fire: FakeFire, fake_web: FakeWeb
) -> None:
    """The built-in Escea integration is flagged."""
    MockConfigEntry(domain="escea").add_to_hass(hass)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "conflict_escea")


async def test_diagnostics_redacted(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    """The download hides the login, PIN and serial."""
    from custom_components.escea_fireplace.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    result = await async_get_config_entry_diagnostics(hass, loaded)
    data = result["entry"]["data"]
    assert data["password"] == REDACTED
    assert data["pin"] == REDACTED
    assert data["serial"] == REDACTED
    assert result["state"]["diagnostics"]["gas_drive"] == 23


async def test_unload(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """Unloading closes the UDP socket."""
    assert await hass.config_entries.async_unload(loaded.entry_id)
    from custom_components.escea_fireplace.const import DATA_TRANSPORT

    assert not hass.data[DATA_TRANSPORT].is_open


async def test_poll_timer(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    fake_fire: FakeFire,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The 30 s poll picks up changes from the remote."""
    fake_fire.state.is_on = True
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    for _ in range(20):
        if hass.states.get(CLIMATE).state == HVACMode.HEAT:
            break
        await asyncio.sleep(0.05)
    assert hass.states.get(CLIMATE).state == HVACMode.HEAT
