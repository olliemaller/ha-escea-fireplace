"""Lighting state, and switch and power states from the diagnostics page."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EsceaConfigEntry, EsceaCoordinator, EsceaData
from .entity import EsceaEntity, EsceaWebEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EsceaBinarySensorDescription(BinarySensorEntityDescription):
    """How to read one binary sensor."""

    value_fn: Callable[[EsceaData], bool | None]
    from_web: bool = False


def _diag(attr: str) -> Callable[[EsceaData], bool | None]:
    def value(data: EsceaData) -> bool | None:
        return getattr(data.diagnostics, attr) if data.diagnostics else None

    return value


BINARY_SENSORS: tuple[EsceaBinarySensorDescription, ...] = (
    EsceaBinarySensorDescription(
        key="busy",
        translation_key="busy",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda data: data.busy_remaining > 0,
    ),
    EsceaBinarySensorDescription(
        key="pilot_valve_power",
        translation_key="pilot_valve_power",
        device_class=BinarySensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_diag("pilot_valve_power"),
        from_web=True,
    ),
    EsceaBinarySensorDescription(
        key="thermal_cutout_power",
        translation_key="thermal_cutout_power",
        device_class=BinarySensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_diag("thermal_cutout_power"),
        from_web=True,
    ),
    *(
        EsceaBinarySensorDescription(
            key=key,
            translation_key=key,
            device_class=BinarySensorDeviceClass.POWER,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=_diag(key),
            from_web=True,
        )
        for key in (
            "ignition_power",
            "power_b2_sv",
            "power_b3",
            "aux_switch",
            "automation_switch",
            "flue_fan_override",
        )
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EsceaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the binary sensors."""
    coordinator = entry.runtime_data
    web_ok = coordinator.web_enabled and coordinator.web.has_credentials
    async_add_entities(
        (EsceaWebBinarySensor if description.from_web else EsceaBinarySensor)(
            coordinator, description
        )
        for description in BINARY_SENSORS
        if not description.from_web or web_ok
    )


class EsceaBinarySensor(EsceaEntity, BinarySensorEntity):
    """A binary sensor read over UDP."""

    entity_description: EsceaBinarySensorDescription

    def __init__(
        self, coordinator: EsceaCoordinator, description: EsceaBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)


class EsceaWebBinarySensor(EsceaWebEntity, EsceaBinarySensor):
    """A binary sensor read from the diagnostics page."""
