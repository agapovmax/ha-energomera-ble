"""Диагностика для сообщений об ошибках (PIN, адрес и серийный номер скрыты)."""

from __future__ import annotations

from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from . import EnergomeraConfigEntry
from .const import CONF_PIN, CONF_SERIAL
from .redact import redact_text

TO_REDACT = {CONF_PIN, CONF_ADDRESS, CONF_SERIAL, "serial", "title", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EnergomeraConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    info = bluetooth.async_last_service_info(hass, coordinator.address, connectable=True)
    data = coordinator.data

    return {
        "entry": async_redact_data(
            {
                "title": entry.title,
                "unique_id": entry.unique_id,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            TO_REDACT,
        ),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_error": redact_text(
                coordinator.last_error,
                coordinator.address,
                coordinator.serial,
                coordinator.config_entry.data.get(CONF_SERIAL),
            ),
            "update_interval": str(coordinator.update_interval),
            "serial_known": coordinator.serial is not None,
        },
        "bluetooth": {
            "visible": info is not None,
            "name_prefix": info.name.split("#", 1)[0].strip() if info and info.name else None,
            "rssi": info.rssi if info else None,
            "connectable": info.connectable if info else None,
        },
        "values": dict(data.values) if data else None,
    }
