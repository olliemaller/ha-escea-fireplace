"""Fixtures: a fake fire over real loopback UDP, and a fake web page."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Generator
from dataclasses import dataclass, field
import functools
import hashlib
import socket
from typing import Any
from unittest.mock import patch

from aioescea import EsceaConnectionError, EsceaTransport, EsceaWebClient
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.escea_fireplace.const import (
    CONF_PIN,
    CONF_SERIAL,
    DATA_TRANSPORT,
    DOMAIN,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .fake_fire import FakeFire

FIRE_HOST = "127.0.0.2"
SERIAL = 123456
PIN = 1234
TOKEN = "0123456789abcdef0123456789abcdef"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


@pytest.fixture(autouse=True)
def _sockets(socket_enabled: None) -> None:
    """The fake fire uses real UDP sockets on loopback."""


@pytest.fixture
def udp_port() -> int:
    """A free UDP port standing in for 3300."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(autouse=True)
async def patch_network(hass: HomeAssistant, udp_port: int) -> AsyncIterator[None]:
    """Bind the integration's socket to loopback and broadcast to the fake fire."""
    with (
        patch(
            "custom_components.escea_fireplace.transport.EsceaTransport",
            functools.partial(EsceaTransport, port=udp_port, bind_address="127.0.0.1"),
        ),
        patch(
            "custom_components.escea_fireplace.transport.async_broadcast_addresses",
            return_value=[FIRE_HOST],
        ),
        patch(
            "custom_components.escea_fireplace.coordinator.async_broadcast_addresses",
            return_value=[FIRE_HOST],
        ),
        patch("custom_components.escea_fireplace.transport.DISCOVERY_TIMEOUT", 0.3),
        patch("aioescea.transport.DEFAULT_TIMEOUT", 0.2),
    ):
        yield
    transport: EsceaTransport | None = hass.data.get(DATA_TRANSPORT)
    if transport is not None:
        await transport.close()


@pytest.fixture
async def fake_fire(udp_port: int) -> AsyncIterator[FakeFire]:
    """A fake fire on 127.0.0.2."""
    loop = asyncio.get_running_loop()
    fire = FakeFire(reply_port=udp_port)
    fire.state.serial = SERIAL
    fire.state.pin = PIN
    transport, _ = await loop.create_datagram_endpoint(
        lambda: fire, local_addr=(FIRE_HOST, udp_port)
    )
    yield fire
    transport.close()


def _row(label: str, value: str) -> str:
    return f'<tr><td>{label}:</td><td class ="t_right">{value}</td></tr>'


def _on_off(value: bool) -> str:
    return f'<font color="red">{"ON" if value else "OFF"}</font>'


@dataclass
class FakeWeb:
    """The fire's web page, answering through Home Assistant's HTTP mock."""

    fire: FakeFire
    username: str = str(SERIAL)
    password: str = str(PIN)
    clock: str = "17:12"
    timers: dict[int, list[Any]] = field(
        default_factory=lambda: {
            1: ["06:55", "08:00", True],
            2: ["16:00", "22:00", False],
        }
    )
    saves: list[list[tuple[str, str]]] = field(default_factory=list)
    reachable: bool = True

    def _page(self, rows: str, logged_in: bool = True) -> AiohttpClientMockResponse:
        menu = '<a href="#" onClick="logout();">Log out</a>' if logged_in else ""
        return AiohttpClientMockResponse(
            "get", URL(), text=f"<html>{menu}<table>{rows}</table></html>"
        )

    def index(self) -> AiohttpClientMockResponse:
        rows = [
            _row("Time", self.clock),
            _row("Current Room Temperature", " 18 &deg;C"),
        ]
        for n in (1, 2):
            rows.append(_row(f"Timer {n} on time", self.timers[n][0]))
            rows.append(_row(f"Timer {n} off time", self.timers[n][1]))
        for n in (1, 2):
            rows.append(_row(f"Timer {n} status", _on_off(self.timers[n][2])))
        return self._page("".join(rows), logged_in=False)

    async def handle(
        self, method: str, url: URL, data: Any
    ) -> AiohttpClientMockResponse:
        if not self.reachable:
            return AiohttpClientMockResponse(method, url, exc=TimeoutError())
        path = url.path
        if path == "/doLogin.html":
            good = (
                data["user"] == hashlib.md5(self.username.encode()).hexdigest()
                and data["password"] == hashlib.md5(self.password.encode()).hexdigest()
            )
            value = TOKEN if good else ""
            return AiohttpClientMockResponse(
                method, url, text=f'<input name="token" id="token" value="{value}">'
            )
        if path == "/diagnostics.html":
            return self._page(
                _row("Internal Processor Temperature", " 41 &deg;C")
                + _row("Power Detected Pilot Valve", _on_off(True))
                + _row("Power detected through thermal cut-out", _on_off(True))
                + _row("Current DX Gas Drive", " 23&#37;")
                + _row("Current Flue Fan Drive", " 99&#37;")
            )
        if path == "/index.html" and method.upper() == "POST":
            form = list(data.items())
            self.saves.append(form)
            values = dict(form)
            for n in (1, 2):
                self.timers[n] = [
                    values[f"TIMER{n}_ON_TIME"],
                    values[f"TIMER{n}_OFF_TIME"],
                    values[f"TIMER{n}_SW"] == "On",
                ]
            self.fire.state.is_on = values["ON_OFF_SWITCH"] == "On"
        return self.index()


@pytest.fixture
def fake_web(
    aioclient_mock: AiohttpClientMocker, fake_fire: FakeFire
) -> Generator[FakeWeb]:
    """Route every request for the fire's web page to FakeWeb.

    GETs go through aiohttp (Home Assistant's HTTP mock). aioescea sends POSTs
    over a raw socket, so those are routed to FakeWeb directly.
    """
    web = FakeWeb(fake_fire)
    for path in ("index.html", "doLogin.html", "diagnostics.html"):
        aioclient_mock.get(f"http://{FIRE_HOST}/{path}", side_effect=web.handle)

    async def post(
        client: EsceaWebClient,
        path: str,
        data: dict[str, str],
        *,
        token: str | None,
        timeout: float,
    ) -> str:
        reply = await web.handle("post", URL(f"http://{client.host}/{path}"), data)
        if reply.exc is not None:
            raise EsceaConnectionError(f"POST /{path} failed: {reply.exc!r}")
        return await reply.text()

    with patch.object(EsceaWebClient, "_post", post):
        yield web


@pytest.fixture
def entry() -> MockConfigEntry:
    """A config entry for the fake fire, with the web login."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(SERIAL),
        title=f"Escea {SERIAL}",
        data={
            CONF_HOST: FIRE_HOST,
            CONF_SERIAL: SERIAL,
            CONF_PIN: PIN,
            CONF_USERNAME: str(SERIAL),
            CONF_PASSWORD: str(PIN),
        },
    )


@pytest.fixture
async def loaded(
    hass: HomeAssistant, entry: MockConfigEntry, fake_fire: FakeFire, fake_web: FakeWeb
) -> MockConfigEntry:
    """The entry, set up."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def no_setup() -> Generator[None]:
    """Stop the config flow tests from setting the entry up."""
    with patch(
        "custom_components.escea_fireplace.async_setup_entry", return_value=True
    ):
        yield


@dataclass
class FakeG3:
    """A Generation 3 (Wi-Fi) fire's NCAPI, through Home Assistant's HTTP mock."""

    state: dict[str, Any] = field(
        default_factory=lambda: {
            "protocol_version": "1",
            "fire_type": "gas",
            "state": "off",
            "fan_boost": False,
            "flame_effect": False,
            "target_temp_deci_c": 220,
            "room_temp_deci_c": 185,
            "remote_present": True,
            "serial_number": "654321",
            "errors": False,
        }
    )
    posts: list[dict[str, str]] = field(default_factory=list)

    async def handle(
        self, method: str, url: URL, data: Any
    ) -> AiohttpClientMockResponse:
        if method.upper() == "GET":
            return AiohttpClientMockResponse(method, url, json=self.state)
        params = dict(url.query)
        self.posts.append(params)
        if "on" in params:
            self.state["state"] = (
                "starting" if params["on"] == "true" else "shutting_down"
            )
        if "target_temp_deci_c" in params:
            self.state["target_temp_deci_c"] = int(params["target_temp_deci_c"])
        if params.get("fan_boost") == "true":
            self.state.update(fan_boost=True, flame_effect=False)
        elif params.get("fan_boost") == "false":
            self.state["fan_boost"] = False
        if params.get("flame_effect") == "true":
            self.state.update(flame_effect=True, fan_boost=False)
        elif params.get("flame_effect") == "false":
            self.state["flame_effect"] = False
        return AiohttpClientMockResponse(method, url)


G3_HOST = "192.0.2.60"


@pytest.fixture
def fake_g3(aioclient_mock: AiohttpClientMocker) -> FakeG3:
    """A Generation 3 fire at G3_HOST."""
    fire = FakeG3()
    for method in ("get", "post"):
        aioclient_mock.request(method, f"http://{G3_HOST}/", side_effect=fire.handle)
    return fire


@pytest.fixture(autouse=True)
def no_g3_probe(request: pytest.FixtureRequest) -> Generator[None]:
    """Addresses aren't Generation 3 fires unless the test has one."""
    if "fake_g3" in request.fixturenames:
        yield
        return
    with patch(
        "custom_components.escea_fireplace.config_flow.async_probe", return_value=None
    ):
        yield
