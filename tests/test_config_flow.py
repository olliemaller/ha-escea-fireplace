"""Tests for the config flow."""

from __future__ import annotations

from unittest.mock import patch

from aioescea import EsceaPortInUseError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escea_fireplace.const import (
    CONF_MAC,
    CONF_PIN,
    CONF_SERIAL,
    CONF_WEB_ENABLED,
    CONF_WEB_INTERVAL,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .conftest import FIRE_HOST, PIN, SERIAL, FakeWeb
from .fake_fire import FakeFire

pytestmark = pytest.mark.usefixtures("no_setup")

DHCP = DhcpServiceInfo(ip=FIRE_HOST, hostname="escea", macaddress="acde48aabbcc")


async def test_search_finds_fire_and_logs_in(
    hass: HomeAssistant, fake_fire: FakeFire, fake_web: FakeWeb
) -> None:
    """Blank address: broadcast, find one fire, log in with serial and PIN."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: ""}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Escea {SERIAL}"
    assert result["result"].unique_id == str(SERIAL)
    assert result["data"] == {
        CONF_HOST: FIRE_HOST,
        CONF_SERIAL: SERIAL,
        CONF_PIN: PIN,
        CONF_USERNAME: str(SERIAL),
        CONF_PASSWORD: str(PIN),
    }


async def test_manual_address(
    hass: HomeAssistant, fake_fire: FakeFire, fake_web: FakeWeb
) -> None:
    """An address is asked directly with SEARCH_FOR_FIRES."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: FIRE_HOST}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == FIRE_HOST


async def test_nothing_answers(hass: HomeAssistant) -> None:
    """No fire on the network."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: ""}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_fireplaces"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: FIRE_HOST}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_port_in_use(hass: HomeAssistant) -> None:
    """Another program has UDP 3300."""
    with patch(
        "custom_components.escea_fireplace.config_flow.async_discover_fireplaces",
        side_effect=EsceaPortInUseError,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: ""}
        )
    assert result["errors"] == {"base": "port_in_use"}


async def test_wrong_login_then_skip(
    hass: HomeAssistant, fake_fire: FakeFire, fake_web: FakeWeb
) -> None:
    """If serial and PIN don't log in, ask; blank fields skip the web page."""
    fake_web.password = "9999"
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: FIRE_HOST}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "web"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: str(SERIAL), CONF_PASSWORD: "1111"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "", CONF_PASSWORD: ""}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_PASSWORD not in result["data"]


async def test_wrong_login_then_right(
    hass: HomeAssistant, fake_fire: FakeFire, fake_web: FakeWeb
) -> None:
    """A custom web login is accepted."""
    fake_web.username, fake_web.password = "admin", "secret"
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_HOST: FIRE_HOST}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USERNAME] == "admin"


async def test_dhcp(
    hass: HomeAssistant, fake_fire: FakeFire, fake_web: FakeWeb
) -> None:
    """A fire joining the network is offered, with its MAC address."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC] == "ac:de:48:aa:bb:cc"


async def test_dhcp_not_a_fire(hass: HomeAssistant) -> None:
    """Something else with that MAC prefix is ignored."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_escea"


async def test_dhcp_updates_address(hass: HomeAssistant, fake_fire: FakeFire) -> None:
    """A known fire on a new address updates the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(SERIAL),
        data={CONF_HOST: "192.0.2.1", CONF_SERIAL: SERIAL, CONF_PIN: PIN},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == FIRE_HOST
    assert entry.data[CONF_MAC] == "ac:de:48:aa:bb:cc"


async def test_reconfigure(hass: HomeAssistant, fake_fire: FakeFire) -> None:
    """Change the address."""
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
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == FIRE_HOST


async def test_reconfigure_wrong_fire(hass: HomeAssistant, fake_fire: FakeFire) -> None:
    """An address belonging to another fire is refused."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="999",
        data={CONF_HOST: "192.0.2.1", CONF_SERIAL: 999, CONF_PIN: PIN},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: FIRE_HOST}
    )
    assert result["reason"] == "wrong_fireplace"


async def test_reauth(
    hass: HomeAssistant, entry: MockConfigEntry, fake_fire: FakeFire, fake_web: FakeWeb
) -> None:
    """A new web login is checked and saved."""
    entry.add_to_hass(hass)
    fake_web.password = "4321"
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: str(SERIAL), CONF_PASSWORD: "0000"}
    )
    assert result["errors"] == {"base": "invalid_auth"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: str(SERIAL), CONF_PASSWORD: "4321"}
    )
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "4321"


async def test_options(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Web page options."""
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_WEB_ENABLED: False, CONF_WEB_INTERVAL: 15}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_WEB_ENABLED: False, CONF_WEB_INTERVAL: 15}
