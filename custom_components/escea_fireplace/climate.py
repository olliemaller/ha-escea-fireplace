"""The fireplace as a heating thermostat."""

from __future__ import annotations

from typing import Any

from aioescea import MAX_TEMPERATURE, MIN_TEMPERATURE, FireMode
from awesomeversion import AwesomeVersion

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_WHOLE,
    UnitOfTemperature,
    __version__ as HA_VERSION,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EsceaConfigEntry, EsceaCoordinator
from .entity import EsceaEntity

PARALLEL_UPDATES = 1

PRESETS = [mode.value for mode in FireMode]

#: Home Assistant 2026.11 renamed the climate temperature properties to
#: native_*. Use whichever this version expects, so neither warns.
NATIVE_TEMPERATURES = AwesomeVersion(HA_VERSION) >= AwesomeVersion("2026.11.0")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EsceaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the thermostat."""
    async_add_entities([EsceaClimate(entry.runtime_data)])


class EsceaClimate(EsceaEntity, ClimateEntity):
    """Heat or off, a target temperature, and normal, boost or flame effect."""

    _attr_name = None
    _attr_translation_key = "fireplace"
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = PRESETS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    if NATIVE_TEMPERATURES:
        _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    else:
        _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = PRECISION_WHOLE
    _attr_precision = PRECISION_WHOLE
    _attr_min_temp = MIN_TEMPERATURE
    _attr_max_temp = MAX_TEMPERATURE

    def __init__(self, coordinator: EsceaCoordinator) -> None:
        super().__init__(coordinator, "")

    def _room_temperature(self) -> float:
        """Return the room temperature the fire measures."""
        return self.coordinator.data.status.room_temperature

    def _target_temperature(self) -> float:
        """Return the target, or the held one while the fire lights."""
        data = self.coordinator.data
        return data.pending.get("temperature", data.status.target_temperature)

    if NATIVE_TEMPERATURES:
        native_current_temperature = property(_room_temperature)  # type: ignore[assignment]
        native_target_temperature = property(_target_temperature)  # type: ignore[assignment]
    else:
        current_temperature = property(_room_temperature)  # type: ignore[assignment]
        target_temperature = property(_target_temperature)  # type: ignore[assignment]

    @property
    def hvac_mode(self) -> HVACMode:
        """Return heat or off."""
        return HVACMode.HEAT if self.coordinator.data.status.is_on else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """Return heating while on, otherwise off."""
        return (
            HVACAction.HEATING if self.coordinator.data.status.is_on else HVACAction.OFF
        )

    @property
    def preset_mode(self) -> str:
        """Return the mode, or the held one while the fire lights."""
        data = self.coordinator.data
        return FireMode(data.pending.get("mode", data.mode)).value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show how long until the fire takes commands again."""
        return {"busy_seconds": round(self.coordinator.data.busy_remaining)}

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Turn on (heat) or off."""
        if hvac_mode is HVACMode.HEAT:
            await self.coordinator.async_turn_on()
        else:
            await self.coordinator.async_turn_off()

    async def async_turn_on(self) -> None:
        """Light the fire."""
        await self.coordinator.async_turn_on()

    async def async_turn_off(self) -> None:
        """Turn the fire off."""
        await self.coordinator.async_turn_off()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target, turning on or off first if a mode was given."""
        if (mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_set_hvac_mode(mode)
            if mode is HVACMode.OFF:
                return
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_set_temperature(temperature)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set normal, boost or flame effect."""
        await self.coordinator.async_set_mode(FireMode(preset_mode))
