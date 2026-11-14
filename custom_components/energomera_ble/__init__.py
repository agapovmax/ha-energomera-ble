"""Энергомера CE208/CE308 по Bluetooth LE."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_BLUETOOTH, ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback

from .config_flow import async_discovery_enabled
from .const import DOMAIN
from .coordinator import EnergomeraCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

type EnergomeraConfigEntry = ConfigEntry[EnergomeraCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EnergomeraConfigEntry) -> bool:
    # до первого опроса: счётчик может быть недоступен, а карточки соседей убрать нужно
    _async_dismiss_discoveries(hass)
    coordinator = EnergomeraCoordinator(hass, entry)
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # опрос по Bluetooth идёт до полуминуты — не держим им запуск Home Assistant;
    # объекты из реестра уже созданы, новые добавятся, когда придут данные
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), f"{DOMAIN} first refresh {coordinator.address}"
    )
    return True


@callback
def _async_dismiss_discoveries(hass: HomeAssistant) -> None:
    """Убрать карточки «Обнаружено», если поиск других счётчиков выключен."""
    if async_discovery_enabled(hass):
        return
    for flow in hass.config_entries.flow.async_progress_by_handler(
        DOMAIN, match_context={"source": SOURCE_BLUETOOTH}
    ):
        hass.config_entries.flow.async_abort(flow["flow_id"])


async def async_unload_entry(hass: HomeAssistant, entry: EnergomeraConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: EnergomeraConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
