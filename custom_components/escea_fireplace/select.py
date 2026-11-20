"""Mode select: normal, boost or flame effect."""

from __future__ import annotations

from aioescea import FireMode

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EsceaConfigEntry, EsceaCoordinator
from .entity import EsceaEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EsceaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the mode select."""
    async_add_entities([EsceaModeSelect(entry.runtime_data)])


class EsceaModeSelect(EsceaEntity, SelectEntity):
    """How the fire runs while it's on."""

    _attr_translation_key = "mode"
    _attr_options = [mode.value for mode in FireMode]

    def __init__(self, coordinator: EsceaCoordinator) -> None:
        super().__init__(coordinator, "mode")

    @property
    def current_option(self) -> str:
        """Return the mode, or the held one while the fire lights."""
        data = self.coordinator.data
        return FireMode(data.pending.get("mode", data.mode)).value

    async def async_select_option(self, option: str) -> None:
        """Change the mode."""
        await self.coordinator.async_set_mode(FireMode(option))
