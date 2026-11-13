"""Периодический опрос счётчика."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_PIN, DEFAULT_SCAN_INTERVAL, DOMAIN, STALE_DATA_TOLERANCE
from .meter import MeterData, async_read_meter
from .pairing import PairingError
from .protocol import MeterProtocolError

_LOGGER = logging.getLogger(__name__)


class EnergomeraCoordinator(DataUpdateCoordinator[MeterData]):
    """Опрашивает счётчик раз в update_interval."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.data[CONF_ADDRESS]}",
            update_interval=timedelta(seconds=interval),
        )
        self.address: str = entry.data[CONF_ADDRESS]
        self.pin: int = int(entry.data[CONF_PIN])
        self.serial: str | None = None
        self.rssi: int | None = None
        self._last_success = 0.0

    async def _async_update_data(self) -> MeterData:
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if ble_device is None:
            return self._fail(f"Счётчик {self.address} сейчас не виден по Bluetooth")

        info = bluetooth.async_last_service_info(self.hass, self.address, connectable=True)
        self.rssi = info.rssi if info else None

        try:
            data = await async_read_meter(ble_device, self.pin, want_serial=self.serial is None)
        except PairingError as err:
            return self._fail(f"Ошибка сопряжения: {err}")
        except (BleakError, MeterProtocolError, TimeoutError, OSError) as err:
            return self._fail(f"Ошибка чтения: {err}")

        if data.serial:
            self.serial = data.serial
        if self.rssi is not None:
            data.values["rssi"] = self.rssi
        self._last_success = time.monotonic()
        return data

    def _fail(self, message: str) -> MeterData:
        # слабый сигнал на столбе — не дёргаем доступность из-за единичных сбоев
        if self.data is not None and time.monotonic() - self._last_success < STALE_DATA_TOLERANCE:
            _LOGGER.warning("%s — оставляю предыдущие показания", message)
            return self.data
        raise UpdateFailed(message)
