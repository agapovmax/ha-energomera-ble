"""Общая база объектов счётчика."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import EnergomeraCoordinator


class EnergomeraEntity(CoordinatorEntity[EnergomeraCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EnergomeraCoordinator, description: EntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        address = coordinator.address
        self._attr_unique_id = f"{address}_{description.key}"
        title = coordinator.config_entry.title
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            manufacturer=MANUFACTURER,
            model=title.split(" ")[0] if title else "CE308",
            name=title,
            serial_number=coordinator.serial,
        )
