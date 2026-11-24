"""Tests for Generation 3 (Wi-Fi) fires through the NCAPI."""

from __future__ import annotations

from unittest.mock import patch

from aioescea import EsceaConnectionError, FireMode
import aiohttp
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.escea_fireplace.const import (
    CONF_GENERATION,
    CONF_MAC,
    CONF_SERIAL,
    DOMAIN,
    GEN3,
)
from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.components.diagnostics import REDACTED
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_HOST,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .conftest import G3_HOST, FakeG3

CLIMATE = "climate.escea_654321"
STATE = "sensor.escea_654321_state"
ROOM = "sensor.escea_654321_room_temperature"
REMOTE = "binary_sensor.escea_654321_remote"
ERRORS = "binary_sensor.escea_654321_stored_errors"
MODE = "select.escea_654321_mode"


@pytest.fixture(autouse=True)
def no_gap() -> None:
    with patch("aioescea.ncapi.MIN_REQUEST_GAP", 0):
        yield


@pytest.fixture
async def g3_entry(hass: HomeAssistant, fake_g3: FakeG3) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="654321",
        title="Escea 654321",
        data={CONF_HOST: G3_HOST, CONF_SERIAL: 654321, CONF_GENERATION: GEN3},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant, fake_g3: FakeG3) -> None:
    """An address that answers NCAPI is added as a Generation 3 fire."""
    with patch(
        "custom_components.escea_fireplace.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: G3_HOST}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Escea 654321"
    assert result["data"] == {
        CONF_HOST: G3_HOST,
        CONF_SERIAL: 654321,
        CONF_GENERATION: GEN3,
    }


async def test_entities(hass: HomeAssistant, g3_entry: MockConfigEntry) -> None:
    """Generation 3 entities: state, remote, errors; no timers or web sensors."""
    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.OFF
    assert state.attributes["current_temperature"] == 18.5
    assert state.attributes[ATTR_TEMPERATURE] == 22.0
    assert state.attributes["min_temp"] == 10
    assert state.attributes["max_temp"] == 38
    assert state.attributes["target_temp_step"] == 0.5
    assert hass.states.get(STATE).state == "off"
    assert hass.states.get(REMOTE).state == STATE_ON
    assert hass.states.get(ERRORS).state == STATE_OFF
    assert hass.states.get(MODE).state == "normal"
    assert hass.states.get("switch.escea_654321_timer_1") is None
    assert (
        hass.states.get("binary_sensor.escea_654321_lighting_or_shutting_down") is None
    )


async def test_control(
    hass: HomeAssistant, g3_entry: MockConfigEntry, fake_g3: FakeG3
) -> None:
    """On, temperature, mode and off go out as NCAPI requests."""
    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: CLIMATE}, blocking=True
    )
    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.PREHEATING

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_TEMPERATURE: 23.5},
        blocking=True,
    )
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_PRESET_MODE: "flame_effect"},
        blocking=True,
    )
    await hass.services.async_call(
        CLIMATE_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: CLIMATE}, blocking=True
    )
    assert fake_g3.posts == [
        {"on": "true"},
        {"target_temp_deci_c": "235"},
        {"flame_effect": "true"},
        {"on": "false"},
    ]
    assert hass.states.get(STATE).state == "shutting_down"
    assert hass.states.get(CLIMATE).attributes[ATTR_HVAC_ACTION] == HVACAction.FAN


async def test_mode_while_off_refused(
    hass: HomeAssistant, g3_entry: MockConfigEntry, fake_g3: FakeG3
) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select",
            "select_option",
            {ATTR_ENTITY_ID: MODE, "option": "boost"},
            blocking=True,
        )
    assert fake_g3.posts == []


async def test_mode_reads_fire_before_guard(
    hass: HomeAssistant, g3_entry: MockConfigEntry, fake_g3: FakeG3
) -> None:
    """The off check reads the fire now, not the last poll."""
    fake_g3.state["state"] = "heating"
    await g3_entry.runtime_data.async_refresh()
    fake_g3.state["state"] = "off"  # turned off since the last poll
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select",
            "select_option",
            {ATTR_ENTITY_ID: MODE, "option": "boost"},
            blocking=True,
        )
    assert fake_g3.posts == []


async def test_stale_room_temperature(
    hass: HomeAssistant, g3_entry: MockConfigEntry, fake_g3: FakeG3
) -> None:
    """Without the remote, the room temperature is unknown, not stale."""
    fake_g3.state["remote_present"] = False
    fake_g3.state["errors"] = True
    await g3_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ROOM).state == STATE_UNKNOWN
    assert hass.states.get(CLIMATE).attributes["current_temperature"] is None
    assert hass.states.get(REMOTE).state == STATE_OFF
    assert hass.states.get(ERRORS).state == STATE_ON


async def test_electric_fire_has_no_modes(hass: HomeAssistant, fake_g3: FakeG3) -> None:
    """Fan boost and flame effect are gas only."""
    fake_g3.state["fire_type"] = "electric"
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="654321",
        title="Escea 654321",
        data={CONF_HOST: G3_HOST, CONF_SERIAL: 654321, CONF_GENERATION: GEN3},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(MODE) is None
    assert ATTR_PRESET_MODE not in hass.states.get(CLIMATE).attributes


G3_DHCP = DhcpServiceInfo(ip=G3_HOST, hostname="escea", macaddress="acde48ddeeff")


async def test_dhcp_finds_wifi_fire(hass: HomeAssistant, fake_g3: FakeG3) -> None:
    """A Wi-Fi fire found by DHCP is offered and saved with its MAC address."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=G3_DHCP
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    with patch(
        "custom_components.escea_fireplace.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_GENERATION] == GEN3
    assert result["data"][CONF_MAC] == "ac:de:48:dd:ee:ff"


async def test_dhcp_updates_wifi_fire_address(
    hass: HomeAssistant, fake_g3: FakeG3
) -> None:
    """A known Wi-Fi fire on a new address updates the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="654321",
        data={CONF_HOST: "192.0.2.1", CONF_SERIAL: 654321, CONF_GENERATION: GEN3},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=G3_DHCP
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == G3_HOST


async def test_diagnostics_hide_serial(
    hass: HomeAssistant, g3_entry: MockConfigEntry
) -> None:
    """The serial number inside the fire's status is redacted too."""
    from custom_components.escea_fireplace.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    result = await async_get_config_entry_diagnostics(hass, g3_entry)
    assert result["state"]["status"]["serial"] == REDACTED
    assert "654321" not in str(result)


async def test_reconfigure_wifi_fire(
    hass: HomeAssistant, fake_g3: FakeG3, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get("http://192.0.2.99/", exc=aiohttp.ClientError())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="654321",
        data={CONF_HOST: "192.0.2.1", CONF_SERIAL: 654321, CONF_GENERATION: GEN3},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.0.2.99"}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    with patch(
        "custom_components.escea_fireplace.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: G3_HOST}
        )
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == G3_HOST


async def test_modes_when_on(
    hass: HomeAssistant, g3_entry: MockConfigEntry, fake_g3: FakeG3
) -> None:
    fake_g3.state["state"] = "heating"
    await g3_entry.runtime_data.async_refresh()
    for option, key in (
        ("boost", "fan_boost"),
        ("flame_effect", "flame_effect"),
        ("normal", "flame_effect"),
    ):
        await hass.services.async_call(
            "select",
            "select_option",
            {ATTR_ENTITY_ID: MODE, "option": option},
            blocking=True,
        )
        assert fake_g3.posts[-1][key] == ("false" if option == "normal" else "true")


async def test_wifi_errors(
    hass: HomeAssistant, g3_entry: MockConfigEntry, fake_g3: FakeG3
) -> None:
    """A failed read marks entities unavailable; a failed change raises."""
    coordinator = g3_entry.runtime_data
    with (
        patch.object(
            coordinator.client, "async_set", side_effect=EsceaConnectionError("x")
        ),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: CLIMATE}, blocking=True
        )
    with pytest.raises(ServiceValidationError):
        await coordinator.async_set_timer(None)  # type: ignore[arg-type]
    with patch.object(
        coordinator.client, "async_get_status", side_effect=EsceaConnectionError("x")
    ):
        with pytest.raises(HomeAssistantError):
            await coordinator.async_set_mode(FireMode.BOOST)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(CLIMATE).state == STATE_UNAVAILABLE


async def test_flame_effect_shows_idle(
    hass: HomeAssistant, g3_entry: MockConfigEntry, fake_g3: FakeG3
) -> None:
    fake_g3.state.update(state="heating", flame_effect=True)
    await g3_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(CLIMATE).attributes[ATTR_HVAC_ACTION] == HVACAction.IDLE
