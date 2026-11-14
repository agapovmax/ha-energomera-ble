"""Сенсоры счётчика."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
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
from .entity import EnergomeraEntity, async_add_meter_entities

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
    # --- расчётные по фазам (только трёхфазный счётчик) ---
    _measure("neutral_current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, 2),
    _measure("current_spread", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, 2),
    SensorEntityDescription(
        key="current_imbalance",
        translation_key="current_imbalance",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    _measure("power_spread", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, 3),
    # --- загрузка относительно автомата и выделенной мощности (если заданы в параметрах) ---
    *(
        SensorEntityDescription(
            key=key,
            translation_key=key,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
        )
        for key in ("phase_load_l1", "phase_load_l2", "phase_load_l3", "power_load")
    ),
    *(
        SensorEntityDescription(
            key=key,
            translation_key=key,
            device_class=SensorDeviceClass.ENUM,
            options=["l1", "l2", "l3"],
        )
        for key in ("max_load_phase", "min_load_phase")
    ),
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
    async_add_meter_entities(
        entry, entry.runtime_data, SENSORS, EnergomeraSensor, async_add_entities, frozenset({"rssi"})
    )


class EnergomeraSensor(EnergomeraEntity, SensorEntity):
    entity_description: SensorEntityDescription

    @property
    def native_value(self):
        if (data := self.coordinator.data) is None:
            return None
        return data.values.get(self.entity_description.key)

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return (
            super().available and data is not None and self.entity_description.key in data.values
        )
