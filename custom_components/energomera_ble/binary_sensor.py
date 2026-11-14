"""Тревоги по фазам: перекос нагрузки и подозрение на обрыв нуля."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EnergomeraConfigEntry
from .entity import EnergomeraEntity, async_add_meter_entities

BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="phase_imbalance",
        translation_key="phase_imbalance",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    BinarySensorEntityDescription(
        key="neutral_break",
        translation_key="neutral_break",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EnergomeraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_meter_entities(
        entry, entry.runtime_data, BINARY_SENSORS, EnergomeraBinarySensor, async_add_entities
    )


class EnergomeraBinarySensor(EnergomeraEntity, BinarySensorEntity):
    entity_description: BinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        if (data := self.coordinator.data) is None:
            return None
        return data.values.get(self.entity_description.key)

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return (
            super().available and data is not None and self.entity_description.key in data.values
        )
