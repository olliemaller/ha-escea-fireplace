"""Read the fire's web page now, instead of waiting for the next read."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EsceaAnyCoordinator, EsceaConfigEntry, EsceaCoordinator
from .entity import EsceaEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EsceaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the button (Ethernet fires with the web page turned on)."""
    coordinator = entry.runtime_data
    if isinstance(coordinator, EsceaCoordinator) and coordinator.web_enabled:
        async_add_entities([EsceaRefreshWebButton(coordinator)])


class EsceaRefreshWebButton(EsceaEntity, ButtonEntity):
    """Reads the timers, clock and diagnostics straight away."""

    _attr_translation_key = "refresh_web"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EsceaAnyCoordinator) -> None:
        super().__init__(coordinator, "refresh_web")

    async def async_press(self) -> None:
        """Read the web page now."""
        assert isinstance(self.coordinator, EsceaCoordinator)
        await self.coordinator.async_refresh_web()
