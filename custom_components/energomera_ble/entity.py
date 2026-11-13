"""Общая база объектов счётчика."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .descriptions import describe
from .coordinator import EnergomeraCoordinator


class EnergomeraEntity(CoordinatorEntity[EnergomeraCoordinator]):
    _attr_has_entity_name = True
    # пояснение не меняется — не засоряем им историю
    _unrecorded_attributes = frozenset({"description"})

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

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if text := describe(self.entity_description.key, self.hass.config.language):
            self._attr_extra_state_attributes = {"description": text}
