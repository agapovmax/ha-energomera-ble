"""Сенсоры счётчика."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EnergomeraConfigEntry
from .entity import EnergomeraEntity

# Названия объектов — в translations/*.json (entity.sensor.<key>.name).


def _energy(
    key: str, enabled: bool = True, state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=state_class,
        suggested_display_precision=2,
        entity_registry_enabled_default=enabled,
    )


def _measure(key: str, unit: str | None, dc: SensorDeviceClass, prec: int) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=unit,
        device_class=dc,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=prec,
    )


PHASES = (1, 2, 3)

SENSORS: tuple[SensorEntityDescription, ...] = (
    _energy("energy_total"),
    _energy("energy_t1"),
    _energy("energy_t2"),
    _energy("energy_t3", enabled=False),
    _energy("energy_t4", enabled=False),
    *(_energy(f"energy_l{i}", enabled=False) for i in PHASES),
    _energy("energy_today", state_class=SensorStateClass.TOTAL),
    _energy("energy_today_t1", enabled=False, state_class=SensorStateClass.TOTAL),
    _energy("energy_today_t2", enabled=False, state_class=SensorStateClass.TOTAL),
    _measure("power_total", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, 3),
    *(_measure(f"power_l{i}", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, 3) for i in PHASES),
    *(
        _measure(f"voltage_l{i}", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, 1)
        for i in PHASES
    ),
    *(
        _measure(f"current_l{i}", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, 2)
        for i in PHASES
    ),
    _measure("cos_total", None, SensorDeviceClass.POWER_FACTOR, 2),
    _measure("frequency", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY, 2),
    SensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="rssi",
        translation_key="rssi",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EnergomeraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    present = set(coordinator.data.values) | {"rssi"}
    async_add_entities(EnergomeraSensor(coordinator, d) for d in SENSORS if d.key in present)


class EnergomeraSensor(EnergomeraEntity, SensorEntity):
    entity_description: SensorEntityDescription

    @property
    def native_value(self):
        return self.coordinator.data.values.get(self.entity_description.key)

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.key in self.coordinator.data.values
