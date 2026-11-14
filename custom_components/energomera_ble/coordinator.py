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
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ALLOCATED_POWER,
    CONF_BREAKER_RATING,
    CONF_IMBALANCE_THRESHOLD,
    CONF_PIN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    STALE_DATA_TOLERANCE,
)
from .meter import MeterData, async_read_meter
from .phases import DEFAULT_IMBALANCE_THRESHOLD, Debounce, derive, derive_limits
from .pairing import InvalidPin, PairingError, async_unpair
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
        self.last_error: str | None = None
        self.imbalance_threshold = float(
            entry.options.get(CONF_IMBALANCE_THRESHOLD, DEFAULT_IMBALANCE_THRESHOLD)
        )
        self._imbalance = Debounce()
        self.breaker_rating = float(entry.options.get(CONF_BREAKER_RATING, 0))
        self.allocated_power = float(entry.options.get(CONF_ALLOCATED_POWER, 0))

    async def _async_update_data(self) -> MeterData:
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if ble_device is None:
            return self._fail("Счётчик сейчас не виден по Bluetooth")

        info = bluetooth.async_last_service_info(self.hass, self.address, connectable=True)
        self.rssi = info.rssi if info else None

        try:
            data = await async_read_meter(ble_device, self.pin, want_serial=self.serial is None)
        except InvalidPin as err:
            # PIN сменили на счётчике: сбрасываем неверное сопряжение и просим новый PIN
            self.last_error = f"PIN отвергнут: {err}"
            try:
                await async_unpair(self.address)
            except Exception as unpair_err:  # noqa: BLE001 — D-Bus может быть недоступен
                _LOGGER.debug("Не удалось удалить сопряжение: %s", unpair_err)
            raise ConfigEntryAuthFailed("Счётчик отверг PIN") from err
        except PairingError as err:
            return self._fail(f"Ошибка сопряжения: {err}")
        except (BleakError, MeterProtocolError, TimeoutError, OSError) as err:
            return self._fail(f"Ошибка чтения: {err}")

        if data.serial and data.serial != self.serial:
            self.serial = data.serial
            self._async_update_device_serial()
        if self.rssi is not None:
            data.values["rssi"] = self.rssi
        data.values.update(derive(data.values, self.imbalance_threshold, self._imbalance))
        data.values.update(derive_limits(data.values, self.breaker_rating, self.allocated_power))
        self._last_success = time.monotonic()
        self.last_error = None
        return data

    def _async_update_device_serial(self) -> None:
        """Объекты создаются до первого опроса — серийник дописываем в устройство отдельно."""
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, self.address)})
        if device is not None and device.serial_number != self.serial:
            registry.async_update_device(device.id, serial_number=self.serial)

    def _fail(self, message: str) -> MeterData:
        self.last_error = message
        # слабый сигнал на столбе — не дёргаем доступность из-за единичных сбоев
        if self.data is not None and time.monotonic() - self._last_success < STALE_DATA_TOLERANCE:
            _LOGGER.warning("%s — оставляю предыдущие показания", message)
            return self.data
        raise UpdateFailed(message)
