"""Failed lighting and faults on Wi-Fi fires, as events to automate on."""

from __future__ import annotations

from typing import cast

from aioescea import FireState, NcapiStatus

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import GEN3
from .coordinator import EsceaAnyCoordinator, EsceaConfigEntry
from .entity import EsceaEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EsceaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the fault event. Ethernet fires don't report faults."""
    coordinator = entry.runtime_data
    if coordinator.generation == GEN3:
        async_add_entities([EsceaFaultEvent(coordinator)])


class EsceaFaultEvent(EsceaEntity, EventEntity):
    """Fires when the fire starts retrying a failed lighting, or reports a fault.

    Only changes count: a fault already showing when Home Assistant starts
    isn't announced again (the State and Stored errors entities show it).
    """

    _attr_translation_key = "fault"
    _attr_event_types = ["ignition_failed", "fault"]

    def __init__(self, coordinator: EsceaAnyCoordinator) -> None:
        super().__init__(coordinator, "fault")
        self._last = self._status

    @property
    def _status(self) -> NcapiStatus:
        return cast(NcapiStatus, self.coordinator.data.status)

    @callback
    def _handle_coordinator_update(self) -> None:
        status, last = self._status, self._last
        self._last = status
        new_state = status.state is not last.state
        event = None
        if new_state and status.state is FireState.RETRYING:
            event = "ignition_failed"
        elif (new_state and status.state is FireState.ERROR) or (
            status.has_errors and not last.has_errors
        ):
            event = "fault"
        if event:
            self._trigger_event(
                event,
                {"state": status.state.value, "stored_errors": status.has_errors},
            )
        super()._handle_coordinator_update()
