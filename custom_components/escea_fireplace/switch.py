"""Power switch, and the fire's two timers' on/off switches."""

from __future__ import annotations

from typing import Any

from aioescea import Timer

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EsceaAnyCoordinator, EsceaConfigEntry
from .entity import EsceaEntity, EsceaWebEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EsceaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the switches."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [EsceaPowerSwitch(coordinator)]
    if coordinator.web_enabled:
        entities += [EsceaTimerSwitch(coordinator, number) for number in (1, 2)]
    async_add_entities(entities)


class EsceaPowerSwitch(EsceaEntity, SwitchEntity):
    """The fire on or off, for dashboards and voice assistants."""

    _attr_translation_key = "power"

    def __init__(self, coordinator: EsceaAnyCoordinator) -> None:
        super().__init__(coordinator, "power")

    @property
    def is_on(self) -> bool:
        """Return True if the fire is on."""
        return self.coordinator.data.status.is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Light the fire."""
        await self.coordinator.async_turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fire off."""
        await self.coordinator.async_turn_off()


class EsceaTimerSwitch(EsceaWebEntity, SwitchEntity):
    """Turns one of the fire's built-in daily timers on or off."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EsceaAnyCoordinator, number: int) -> None:
        super().__init__(coordinator, f"timer_{number}")
        self._number = number
        self._attr_translation_key = "timer"
        self._attr_translation_placeholders = {"number": str(number)}

    @property
    def available(self) -> bool:
        """Needs the web login to change."""
        return super().available and self.coordinator.can_write_web

    @property
    def is_on(self) -> bool | None:
        """Return True if the timer is on."""
        page = self.coordinator.data.home_page
        return page.timers[self._number].enabled if page else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the timer on."""
        await self.coordinator.async_set_timer(Timer(self._number, None, None, True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the timer off."""
        await self.coordinator.async_set_timer(Timer(self._number, None, None, False))
