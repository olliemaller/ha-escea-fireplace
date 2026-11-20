"""Room temperature, and readings from the fire's diagnostics page."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import (
    EsceaConfigEntry,
    EsceaCoordinator,
    EsceaData,
    clock_drift_minutes,
)
from .entity import EsceaEntity, EsceaWebEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EsceaSensorDescription(SensorEntityDescription):
    """How to read one sensor."""

    value_fn: Callable[[EsceaData], float | int | None]
    from_web: bool = False
    needs_login: bool = False


def _diag(attr: str) -> Callable[[EsceaData], int | None]:
    def value(data: EsceaData) -> int | None:
        return getattr(data.diagnostics, attr) if data.diagnostics else None

    return value


def _clock_offset(data: EsceaData) -> int | None:
    if data.home_page is None:
        return None
    return clock_drift_minutes(data.home_page.clock, dt_util.now())


SENSORS: tuple[EsceaSensorDescription, ...] = (
    EsceaSensorDescription(
        key="room_temperature",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda data: data.status.room_temperature,
    ),
    EsceaSensorDescription(
        key="ready_in",
        translation_key="ready_in",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: round(data.busy_remaining),
    ),
    EsceaSensorDescription(
        key="clock_offset",
        translation_key="clock_offset",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_clock_offset,
        from_web=True,
    ),
    EsceaSensorDescription(
        key="processor_temperature",
        translation_key="processor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_diag("processor_temperature"),
        from_web=True,
        needs_login=True,
    ),
    EsceaSensorDescription(
        key="duct_temperature",
        translation_key="duct_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_diag("duct_temperature"),
        from_web=True,
        needs_login=True,
    ),
    *(
        EsceaSensorDescription(
            key=key,
            translation_key=key,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=_diag(key),
            from_web=True,
            needs_login=True,
        )
        for key in ("gas_drive", "flue_fan_drive", "room_fan_drive")
    ),
    *(
        EsceaSensorDescription(
            key=key,
            translation_key=key,
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=_diag(key),
            from_web=True,
            needs_login=True,
        )
        for key in ("solenoid_current", "valve_current")
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EsceaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        (EsceaWebSensor if description.from_web else EsceaSensor)(
            coordinator, description
        )
        for description in SENSORS
        if not description.from_web
        or (
            coordinator.web_enabled
            and (not description.needs_login or coordinator.web.has_credentials)
        )
    )


class EsceaSensor(EsceaEntity, SensorEntity):
    """A sensor read over UDP."""

    entity_description: EsceaSensorDescription

    def __init__(
        self, coordinator: EsceaCoordinator, description: EsceaSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | None:
        """Return the reading."""
        return self.entity_description.value_fn(self.coordinator.data)


class EsceaWebSensor(EsceaWebEntity, EsceaSensor):
    """A sensor read from the fire's web page."""
