"""On and off times of the fire's two built-in daily timers."""

from __future__ import annotations

from datetime import time

from aioescea import Timer

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EsceaConfigEntry, EsceaCoordinator
from .entity import EsceaWebEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EsceaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the timer times."""
    coordinator = entry.runtime_data
    if not coordinator.web_enabled:
        return
    async_add_entities(
        EsceaTimerTime(coordinator, number, which)
        for number in (1, 2)
        for which in ("on", "off")
    )


class EsceaTimerTime(EsceaWebEntity, TimeEntity):
    """When one of the fire's timers turns it on or off."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EsceaCoordinator, number: int, which: str) -> None:
        super().__init__(coordinator, f"timer_{number}_{which}")
        self._number = number
        self._which = which
        self._attr_translation_key = f"timer_{which}"
        self._attr_translation_placeholders = {"number": str(number)}

    @property
    def available(self) -> bool:
        """Needs the web login to change."""
        return super().available and self.coordinator.can_write_web

    @property
    def native_value(self) -> time | None:
        """Return the time."""
        page = self.coordinator.data.home_page
        if page is None:
            return None
        timer = page.timers[self._number]
        return timer.on_time if self._which == "on" else timer.off_time

    async def async_set_value(self, value: time) -> None:
        """Change the time (to the minute)."""
        value = value.replace(second=0, microsecond=0)
        if self._which == "on":
            timer = Timer(self._number, value, None, None)
        else:
            timer = Timer(self._number, None, value, None)
        await self.coordinator.async_set_timer(timer)
