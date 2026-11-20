"""The fireplace as a heating thermostat."""

from __future__ import annotations

from typing import Any

from aioescea import FireMode, FireState
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
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    UnitOfTemperature,
    __version__ as HA_VERSION,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EsceaAnyCoordinator, EsceaConfigEntry
from .entity import EsceaEntity

PARALLEL_UPDATES = 1

PRESETS = [mode.value for mode in FireMode]

#: Home Assistant 2026.11 renamed the climate temperature properties to
#: native_*. Use whichever this version expects, so neither warns.
NATIVE_TEMPERATURES = AwesomeVersion(HA_VERSION) >= AwesomeVersion("2026.11.0")

#: What a Generation 3 fire's reported state means for Home Assistant.
G3_ACTIONS: dict[FireState, HVACAction] = {
    FireState.STARTING: HVACAction.PREHEATING,
    FireState.RETRYING: HVACAction.PREHEATING,
    FireState.IGNITING: HVACAction.PREHEATING,
    FireState.HEATING: HVACAction.HEATING,
    FireState.BURN_OFF: HVACAction.HEATING,
    FireState.GAS_ADJUST: HVACAction.HEATING,
    FireState.PILOT_ONLY: HVACAction.IDLE,
    FireState.SHUTTING_DOWN: HVACAction.FAN,
    FireState.COOL_DOWN: HVACAction.FAN,
}


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
    if NATIVE_TEMPERATURES:  # pragma: no cover - depends on the HA version
        _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    else:  # pragma: no cover
        _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: EsceaAnyCoordinator) -> None:
        super().__init__(coordinator, "")
        self._attr_min_temp = coordinator.min_temp
        self._attr_max_temp = coordinator.max_temp
        self._attr_target_temperature_step = coordinator.temp_step
        self._attr_precision = (
            PRECISION_WHOLE if coordinator.temp_step == 1 else PRECISION_TENTHS
        )
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if coordinator.supports_modes:
            features |= ClimateEntityFeature.PRESET_MODE
            self._attr_preset_modes = PRESETS
        self._attr_supported_features = features

    def _room_temperature(self) -> float | None:
        """Return the room temperature, or None if it's stale."""
        status = self.coordinator.data.status
        if getattr(status, "remote_present", True) is False:
            return None
        return status.room_temperature

    def _target_temperature(self) -> float:
        """Return the target, or the held one while the fire lights."""
        data = self.coordinator.data
        return float(data.pending.get("temperature", data.status.target_temperature))

    if NATIVE_TEMPERATURES:  # pragma: no cover - depends on the HA version
        native_current_temperature = property(_room_temperature)
        native_target_temperature = property(_target_temperature)
    else:  # pragma: no cover
        current_temperature = property(_room_temperature)
        target_temperature = property(_target_temperature)

    @property
    def hvac_mode(self) -> HVACMode:
        """Return heat or off."""
        return HVACMode.HEAT if self.coordinator.data.status.is_on else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """Return what the fire is doing.

        Generation 3 fires report their state; Generation 2 only on or off.
        Flame effect is for looks and gives little heat, so it shows as idle.
        """
        status = self.coordinator.data.status
        state = getattr(status, "state", None)
        if state is not None:
            action = G3_ACTIONS.get(state, HVACAction.OFF)
        else:
            action = HVACAction.HEATING if status.is_on else HVACAction.OFF
        if action is HVACAction.HEATING and status.flame_effect:
            return HVACAction.IDLE
        return action

    @property
    def preset_mode(self) -> str | None:
        """Return the mode, or the held one while the fire lights.

        Only read when the fire supports modes (PRESET_MODE is set).
        """
        data = self.coordinator.data
        return FireMode(data.pending.get("mode", data.mode)).value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show what the fire is doing, or how long until it takes commands."""
        data = self.coordinator.data
        state = getattr(data.status, "state", None)
        if state is not None:
            return {"fire_state": state.value}
        return {"busy_seconds": round(data.busy_remaining)}

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
