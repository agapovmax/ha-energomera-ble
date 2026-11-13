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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EnergomeraConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import EnergomeraCoordinator


def _energy(key: str, name: str, enabled: bool = True) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        name=name,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        entity_registry_enabled_default=enabled,
    )


def _phase(key: str, name: str, unit: str, dc: SensorDeviceClass, prec: int) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        name=name,
        native_unit_of_measurement=unit,
        device_class=dc,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=prec,
    )


SENSORS: tuple[SensorEntityDescription, ...] = (
    _energy("energy_total", "Энергия (сумма)"),
    _energy("energy_t1", "Энергия T1"),
    _energy("energy_t2", "Энергия T2"),
    _energy("energy_t3", "Энергия T3", enabled=False),
    _energy("energy_t4", "Энергия T4", enabled=False),
    *(_energy(f"energy_l{i}", f"Энергия L{i}", enabled=False) for i in (1, 2, 3)),
    *(
        SensorEntityDescription(
            key=key,
            name=name,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL,
            suggested_display_precision=2,
            entity_registry_enabled_default=enabled,
        )
        for key, name, enabled in (
            ("energy_today", "Энергия за сегодня", True),
            ("energy_today_t1", "Энергия за сегодня T1", False),
            ("energy_today_t2", "Энергия за сегодня T2", False),
        )
    ),
    _phase("power_total", "Мощность", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, 3),
    *(_phase(f"power_l{i}", f"Мощность L{i}", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, 3) for i in (1, 2, 3)),
    *(
        _phase(f"voltage_l{i}", f"Напряжение L{i}", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, 1)
        for i in (1, 2, 3)
    ),
    *(
        _phase(f"current_l{i}", f"Ток L{i}", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, 2)
        for i in (1, 2, 3)
    ),
    _phase("cos_total", "cos φ", None, SensorDeviceClass.POWER_FACTOR, 2),
    _phase("frequency", "Частота", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY, 2),
    SensorEntityDescription(
        key="temperature",
        name="Температура",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="rssi",
        name="Уровень сигнала",
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


class EnergomeraSensor(CoordinatorEntity[EnergomeraCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EnergomeraCoordinator, description: SensorEntityDescription) -> None:
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

    @property
    def native_value(self):
        return self.coordinator.data.values.get(self.entity_description.key)

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.key in self.coordinator.data.values
