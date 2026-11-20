"""Room temperature, and readings from the fire's diagnostics page."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from aioescea import FireState

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

from .const import GEN2, GEN3
from .coordinator import (
    EsceaAnyCoordinator,
    EsceaConfigEntry,
    EsceaData,
    clock_drift_minutes,
)
from .entity import EsceaEntity, EsceaWebEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EsceaSensorDescription(SensorEntityDescription):
    """How to read one sensor."""

    value_fn: Callable[[EsceaData], float | int | str | None]
    from_web: bool = False
    needs_login: bool = False
    generations: frozenset[int] = frozenset({GEN2, GEN3})


def _diag(attr: str) -> Callable[[EsceaData], int | None]:
    def value(data: EsceaData) -> int | None:
        return getattr(data.diagnostics, attr) if data.diagnostics else None

    return value


def _room_temperature(data: EsceaData) -> float | None:
    status = data.status
    # A Generation 3 fire's reading is stale when it can't hear its remote.
    if getattr(status, "remote_present", True) is False:
        return None
    return status.room_temperature


def _fire_state(data: EsceaData) -> str | None:
    state = getattr(data.status, "state", None)
    return state.value if state is not None else None


def _clock_offset(data: EsceaData) -> int | None:
    clock = data.home_page.clock if data.home_page else None
    return clock_drift_minutes(clock, dt_util.now())


SENSORS: tuple[EsceaSensorDescription, ...] = (
    EsceaSensorDescription(
        key="room_temperature",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=_room_temperature,
    ),
    EsceaSensorDescription(
        key="fire_state",
        translation_key="fire_state",
        device_class=SensorDeviceClass.ENUM,
        options=[state.value for state in FireState],
        value_fn=_fire_state,
        generations=frozenset({GEN3}),
    ),
    EsceaSensorDescription(
        key="ready_in",
        translation_key="ready_in",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: round(data.busy_remaining),
        generations=frozenset({GEN2}),
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
        if coordinator.generation in description.generations
        and (
            not description.from_web
            or (
                coordinator.web_enabled
                and (not description.needs_login or coordinator.has_web_login)
            )
        )
    )


class EsceaSensor(EsceaEntity, SensorEntity):
    """A sensor read over UDP."""

    entity_description: EsceaSensorDescription

    def __init__(
        self,
        coordinator: EsceaAnyCoordinator,
        description: EsceaSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | str | None:
        """Return the reading."""
        return self.entity_description.value_fn(self.coordinator.data)


class EsceaWebSensor(EsceaWebEntity, EsceaSensor):
    """A sensor read from the fire's web page."""
