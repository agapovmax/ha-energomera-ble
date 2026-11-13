"""Кнопка внеочередного опроса счётчика."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EnergomeraConfigEntry
from .entity import EnergomeraEntity

REFRESH = ButtonEntityDescription(
    key="refresh",
    translation_key="refresh",
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EnergomeraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([EnergomeraRefreshButton(entry.runtime_data, REFRESH)])


class EnergomeraRefreshButton(EnergomeraEntity, ButtonEntity):
    @property
    def available(self) -> bool:
        # опросить можно и тогда, когда прошлый опрос не удался
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
