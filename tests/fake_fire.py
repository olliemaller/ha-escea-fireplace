"""A simulated Escea fireplace on localhost, for tests.

It listens on a UDP port, keeps the state a real fire would, and answers
the way the spec describes. ``drop`` makes it ignore the next N requests.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from aioescea.protocol import Command, Response, encode


@dataclass
class FireState:
    is_on: bool = False
    fan_boost: bool = False
    flame_effect: bool = False
    target: int = 21
    room: int = 18
    serial: int = 123456
    pin: int = 1234


@dataclass
class FakeFire(asyncio.DatagramProtocol):
    reply_port: int
    state: FireState = field(default_factory=FireState)
    received: list[Command] = field(default_factory=list)
    drop: int = 0
    transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.DatagramTransport)
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        command = Command(data[1])
        self.received.append(command)
        if self.drop:
            self.drop -= 1
            return
        reply = self._handle(command, data)
        assert self.transport is not None
        # Real fires reply to port 3300 whatever the source port; here the
        # test's transport port stands in for 3300.
        self.transport.sendto(reply, (addr[0], self.reply_port))

    def _handle(self, command: Command, data: bytes) -> bytes:
        s = self.state
        if command is Command.STATUS_PLEASE:
            return encode(
                Response.STATUS,
                bytes([0, s.is_on, s.fan_boost, s.flame_effect, s.target, s.room]),
            )
        if command is Command.SEARCH_FOR_FIRES:
            payload = s.serial.to_bytes(4, "big") + s.pin.to_bytes(2, "big")
            return encode(Response.I_AM_A_FIRE, payload)
        if command is Command.POWER_ON:
            s.is_on = True
            return encode(Response.POWER_ON_ACK)
        if command is Command.POWER_OFF:
            s.is_on = False
            return encode(Response.POWER_OFF_ACK)
        if command is Command.FAN_BOOST_ON:
            s.fan_boost = True
            s.is_on = True  # the real quirk: this lights the fire
            return encode(Response.FAN_BOOST_ON_ACK)
        if command is Command.FAN_BOOST_OFF:
            s.fan_boost = False
            return encode(Response.FAN_BOOST_OFF_ACK)
        if command is Command.FLAME_EFFECT_ON:
            s.flame_effect = True
            s.is_on = True
            return encode(Response.FLAME_EFFECT_ON_ACK)
        if command is Command.FLAME_EFFECT_OFF:
            s.flame_effect = False
            return encode(Response.FLAME_EFFECT_OFF_ACK)
        if command is Command.NEW_SET_TEMP:
            s.target = data[3]
            return encode(Response.NEW_SET_TEMP_ACK)
        raise AssertionError(command)
