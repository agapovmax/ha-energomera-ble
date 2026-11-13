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
from .entity import EnergomeraEntity

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
    coordinator = entry.runtime_data
    present = set(coordinator.data.values)
    async_add_entities(
        EnergomeraBinarySensor(coordinator, d) for d in BINARY_SENSORS if d.key in present
    )


class EnergomeraBinarySensor(EnergomeraEntity, BinarySensorEntity):
    entity_description: BinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.values.get(self.entity_description.key)

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.key in self.coordinator.data.values
