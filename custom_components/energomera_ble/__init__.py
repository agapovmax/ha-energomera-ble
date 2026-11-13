"""Энергомера CE208/CE308 по Bluetooth LE."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import EnergomeraCoordinator

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]

type EnergomeraConfigEntry = ConfigEntry[EnergomeraCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EnergomeraConfigEntry) -> bool:
    coordinator = EnergomeraCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EnergomeraConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: EnergomeraConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
