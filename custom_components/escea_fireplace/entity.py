"""Base entity for the Escea Fireplace integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MAC, DOMAIN, MANUFACTURER
from .coordinator import EsceaCoordinator


class EsceaEntity(CoordinatorEntity[EsceaCoordinator]):
    """An entity belonging to one fireplace."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EsceaCoordinator, key: str) -> None:
        super().__init__(coordinator)
        serial = coordinator.serial
        entry = coordinator.config_entry
        self._attr_unique_id = f"{serial}_{key}" if key else str(serial)
        connections = set()
        if mac := entry.data.get(CONF_MAC):
            connections.add((CONNECTION_NETWORK_MAC, format_mac(mac)))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(serial))},
            connections=connections,
            manufacturer=MANUFACTURER,
            model=(
                "Generation 3 (Wi-Fi)"
                if coordinator.generation == 3
                else "Generation 2 (Ethernet)"
            ),
            name=entry.title,
            serial_number=str(serial),
            configuration_url=f"http://{entry.data[CONF_HOST]}/",
        )


class EsceaWebEntity(EsceaEntity):
    """An entity whose value comes from the fire's web page."""

    @property
    def available(self) -> bool:
        """Unavailable when the web page hasn't been read recently.

        A stale reading (say "pilot valve off" while the fire burns) is
        worse than none.
        """
        data = self.coordinator.data
        return super().available and data.web_fresh and data.home_page is not None
