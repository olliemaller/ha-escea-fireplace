"""One shared UDP socket for every fireplace.

Fires always reply to UDP port 3300, so Home Assistant can only have one
socket on that port. Every config entry and the config flow share it.
"""

from __future__ import annotations

from aioescea import (
    DiscoveredFireplace,
    EsceaTransport,
    async_discover,
)
from aioescea.protocol import Command, decode_identity

from homeassistant.components import network
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback

from .const import DATA_TRANSPORT, DISCOVERY_TIMEOUT


async def async_get_transport(hass: HomeAssistant) -> EsceaTransport:
    """Return the shared transport, opening it on first use.

    Raises EsceaPortInUseError if another program has UDP 3300.
    """
    transport: EsceaTransport | None = hass.data.get(DATA_TRANSPORT)
    if transport is None:
        transport = EsceaTransport()
        hass.data[DATA_TRANSPORT] = transport

        @callback
        def _close(_: Event) -> None:
            hass.async_create_task(transport.close())

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _close)
    await transport.open()
    return transport


async def async_close_transport_if_unused(hass: HomeAssistant, in_use: bool) -> None:
    """Close the shared transport when no fireplace needs it."""
    transport: EsceaTransport | None = hass.data.get(DATA_TRANSPORT)
    if transport is not None and not in_use:
        await transport.close()


async def async_broadcast_addresses(hass: HomeAssistant) -> list[str]:
    """Return the broadcast address of every network Home Assistant uses."""
    return [
        str(addr) for addr in await network.async_get_ipv4_broadcast_addresses(hass)
    ]


async def async_discover_fireplaces(hass: HomeAssistant) -> list[DiscoveredFireplace]:
    """Broadcast on every network and return the fires that answer."""
    transport = await async_get_transport(hass)
    return await async_discover(
        transport, await async_broadcast_addresses(hass), timeout=DISCOVERY_TIMEOUT
    )


async def async_identify(hass: HomeAssistant, host: str) -> DiscoveredFireplace:
    """Ask one address for its serial number and PIN.

    SEARCH_FOR_FIRES is sent straight to the address rather than broadcast,
    so this works across subnets. Raises EsceaConnectionError if nothing
    answers.
    """
    transport = await async_get_transport(hass)
    frame = await transport.request(host, Command.SEARCH_FOR_FIRES)
    identity = decode_identity(frame)
    return DiscoveredFireplace(host=host, serial=identity.serial, pin=identity.pin)
