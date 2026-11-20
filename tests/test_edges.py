"""Error paths and less common cases, for full coverage."""

from __future__ import annotations

from datetime import time as dt_time, timedelta
from ipaddress import IPv4Address
from unittest.mock import patch

from aioescea import DiscoveredFireplace, EsceaError, EsceaPortInUseError
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.escea_fireplace import transport as transport_module
from custom_components.escea_fireplace.const import (
    CONF_MAC,
    CONF_PIN,
    CONF_SERIAL,
    DOMAIN,
)
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.util import dt as dt_util

from .conftest import FIRE_HOST, PIN, SERIAL, FakeWeb
from .fake_fire import FakeFire

# Kept before the autouse fixture patches it.
BROADCAST_ADDRESSES = transport_module.async_broadcast_addresses

CLIMATE = f"climate.escea_{SERIAL}"
TIMER2 = f"switch.escea_{SERIAL}_timer_2"
TIMER1_OFF = f"time.escea_{SERIAL}_timer_1_off"


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)


# Config flow -----------------------------------------------------------------


async def test_search_unexpected_error(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.escea_fireplace.config_flow.async_discover_fireplaces",
        side_effect=EsceaError("odd"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: ""}
        )
    assert result["errors"] == {"base": "unknown"}


async def test_pick_from_several(
    hass: HomeAssistant, fake_fire: FakeFire, fake_web: FakeWeb, no_setup: None
) -> None:
    """With more than one fire found, the user picks."""
    fires = [
        DiscoveredFireplace(host=FIRE_HOST, serial=SERIAL, pin=PIN),
        DiscoveredFireplace(host="192.0.2.9", serial=654321, pin=1111),
    ]
    with patch(
        "custom_components.escea_fireplace.config_flow.async_discover_fireplaces",
        return_value=fires,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: ""}
        )
    assert result["step_id"] == "pick"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"fireplace": str(SERIAL)}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SERIAL] == SERIAL


async def test_web_page_unreachable(
    hass: HomeAssistant, fake_fire: FakeFire, fake_web: FakeWeb, no_setup: None
) -> None:
    """A web page that doesn't answer is reported, and can be skipped."""
    fake_web.reachable = False
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: FIRE_HOST}
    )
    assert result["step_id"] == "web"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "x", CONF_PASSWORD: "y"}
    )
    assert result["errors"] == {"base": "web_unreachable"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_PASSWORD not in result["data"]


async def test_reconfigure_errors(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(SERIAL),
        data={CONF_HOST: "192.0.2.1", CONF_SERIAL: SERIAL, CONF_PIN: PIN},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: FIRE_HOST}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    with patch(
        "custom_components.escea_fireplace.config_flow.async_identify",
        side_effect=EsceaPortInUseError("busy"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: FIRE_HOST}
        )
    assert result["errors"] == {"base": "port_in_use"}


# Coordinator -------------------------------------------------------------------


async def test_device_has_mac(
    hass: HomeAssistant, entry: MockConfigEntry, fake_fire: FakeFire, fake_web: FakeWeb
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=entry.unique_id,
        title=entry.title,
        data={**entry.data, CONF_MAC: "acde48aabbcc"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    [device] = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert (dr.CONNECTION_NETWORK_MAC, "ac:de:48:aa:bb:cc") in device.connections


async def test_rediscovery_finds_nothing_new(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire
) -> None:
    """Failed polls search for the fire; a failed or same-address search is fine."""
    fake_fire.drop = 100
    with patch(
        "custom_components.escea_fireplace.coordinator.async_find",
        side_effect=EsceaError("no"),
    ):
        for _ in range(3):
            await _refresh(hass, loaded)
    with patch(
        "custom_components.escea_fireplace.coordinator.async_find",
        return_value=DiscoveredFireplace(host=FIRE_HOST, serial=SERIAL, pin=PIN),
    ):
        await _refresh(hass, loaded)
    assert loaded.data[CONF_HOST] == FIRE_HOST


async def test_diagnostics_login_rejected_starts_reauth(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    fake_web: FakeWeb,
    freezer: FrozenDateTimeFactory,
) -> None:
    fake_web.password = "changed"
    loaded.runtime_data.web._token = None
    freezer.tick(timedelta(minutes=11))
    await _refresh(hass, loaded)
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(flow["context"]["source"] == "reauth" for flow in flows)


async def test_command_errors(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire
) -> None:
    coordinator = loaded.runtime_data
    with pytest.raises(ServiceValidationError):
        await coordinator.async_set_temperature(31)
    fake_fire.drop = 100
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            CLIMATE_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: CLIMATE}, blocking=True
        )


async def test_ready_refresh_sends_held(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    fake_fire: FakeFire,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The refresh scheduled for the end of the lighting window sends held commands."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: HVACMode.HEAT, ATTR_TEMPERATURE: 24},
        blocking=True,
    )
    assert fake_fire.state.is_on
    assert fake_fire.state.target == 21
    loaded.runtime_data.fireplace._busy_until = 0
    freezer.tick(timedelta(seconds=70))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert fake_fire.state.target == 24


async def test_set_temperature_when_ready(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire
) -> None:
    fake_fire.state.is_on = True
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_TEMPERATURE: 23},
        blocking=True,
    )
    assert fake_fire.state.target == 23
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: HVACMode.OFF, ATTR_TEMPERATURE: 22},
        blocking=True,
    )
    assert not fake_fire.state.is_on


async def test_held_commands_fail_quietly(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_fire: FakeFire
) -> None:
    """If the fire stops answering when held commands go, it's only logged."""
    coordinator = loaded.runtime_data
    await coordinator.async_turn_on()
    await coordinator.async_set_temperature(25)
    coordinator.fireplace._busy_until = 0
    coordinator.fireplace.async_set_temperature = _raise  # type: ignore[method-assign]
    await _refresh(hass, loaded)
    assert coordinator.data.pending == {}


async def _raise(*_: object) -> None:
    raise EsceaError("gone")


async def test_timer_switch_and_time(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_web: FakeWeb
) -> None:
    await hass.services.async_call(
        "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: TIMER2}, blocking=True
    )
    assert fake_web.timers[2][2] is True
    await hass.services.async_call(
        "time",
        "set_value",
        {ATTR_ENTITY_ID: TIMER1_OFF, "time": "08:30"},
        blocking=True,
    )
    assert fake_web.timers[1][1] == "08:30"
    assert hass.states.get(TIMER1_OFF).state == dt_time(8, 30).isoformat()


async def test_timer_errors(
    hass: HomeAssistant, loaded: MockConfigEntry, fake_web: FakeWeb
) -> None:
    coordinator = loaded.runtime_data
    with (
        patch.object(coordinator.web, "async_set_timer", side_effect=EsceaError("no")),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: TIMER2}, blocking=True
        )
    fake_web.password = "changed"
    coordinator.web._token = None
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: TIMER2}, blocking=True
        )
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(flow["context"]["source"] == "reauth" for flow in flows)


async def test_timer_needs_web_page(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    coordinator = loaded.runtime_data
    coordinator._home_page = None
    with pytest.raises(ServiceValidationError):
        await coordinator.async_set_timer(None)  # type: ignore[arg-type]


async def test_broadcast_addresses(hass: HomeAssistant) -> None:
    with patch(
        "homeassistant.components.network.async_get_ipv4_broadcast_addresses",
        return_value={IPv4Address("192.168.1.255")},
    ):
        assert await BROADCAST_ADDRESSES(hass) == ["192.168.1.255"]


async def test_clock_in_step_clears_issue(
    hass: HomeAssistant, entry: MockConfigEntry, fake_fire: FakeFire, fake_web: FakeWeb
) -> None:
    """A fire clock within a few minutes of real time raises no issue."""
    fake_web.clock = dt_util.now().strftime("%H:%M")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"clock_drift_{SERIAL}") is None
