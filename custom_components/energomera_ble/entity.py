"""Общая база объектов счётчика."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .descriptions import describe
from .coordinator import EnergomeraCoordinator


@callback
def async_add_meter_entities[D: EntityDescription](
    entry: ConfigEntry,
    coordinator: EnergomeraCoordinator,
    descriptions: Iterable[D],
    factory: Callable[[EnergomeraCoordinator, D], Entity],
    async_add_entities: AddEntitiesCallback,
    always: frozenset[str] = frozenset(),
) -> None:
    """Создать объекты, не дожидаясь первого опроса.

    Набор величин зависит от модели счётчика и известен только из ответа.
    Сразу создаём то, что уже есть в реестре (и `always`), остальное — когда придут данные.
    """
    descriptions = tuple(descriptions)
    prefix = f"{coordinator.address}_"
    registry = er.async_get(coordinator.hass)
    known = {
        reg.unique_id.removeprefix(prefix)
        for reg in er.async_entries_for_config_entry(registry, entry.entry_id)
        if reg.unique_id.startswith(prefix)
    }
    added: set[str] = set()

    @callback
    def _add(keys: set[str]) -> None:
        new = [d for d in descriptions if d.key in keys and d.key not in added]
        if new:
            added.update(d.key for d in new)
            async_add_entities(factory(coordinator, d) for d in new)

    @callback
    def _on_update() -> None:
        if coordinator.data is not None:
            _add(set(coordinator.data.values) | always)

    _add(known | always)
    _on_update()
    entry.async_on_unload(coordinator.async_add_listener(_on_update))


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
        )
        # до первого опроса серийник неизвестен — не затираем сохранённый в реестре
        if coordinator.serial:
            self._attr_device_info["serial_number"] = coordinator.serial

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if text := describe(self.entity_description.key, self.hass.config.language):
            self._attr_extra_state_attributes = {"description": text}
