"""Мастер настройки: выбор счётчика по серийному номеру и ввод PIN."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS, CONF_SCAN_INTERVAL
from homeassistant.core import callback

from .const import (
    CONF_PIN,
    CONF_SERIAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    NAME_PREFIXES,
)
from .meter import async_read_meter
from .pairing import InvalidPin, PairingError, async_unpair
from .protocol import MeterProtocolError

_LOGGER = logging.getLogger(__name__)

PIN_SCHEMA = vol.All(vol.Coerce(int), vol.Range(min=0, max=999999))


def _is_meter(info: bluetooth.BluetoothServiceInfoBleak) -> bool:
    return bool(info.name) and info.name.strip().startswith(NAME_PREFIXES)


def _serial_from_name(name: str) -> str:
    # "CE308 #012345678    " -> "012345678"
    return name.split("#", 1)[-1].strip()


class EnergomeraConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, bluetooth.BluetoothServiceInfoBleak] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            info = self._discovered[address]
            pin = user_input[CONF_PIN]
            try:
                data = await self._validate(address, pin)
            except InvalidPin:
                errors["base"] = "invalid_pin"
            except PairingError as err:
                _LOGGER.warning("Сопряжение не удалось: %s", err)
                errors["base"] = "pairing_failed"
            except (BleakError, MeterProtocolError, TimeoutError, OSError) as err:
                _LOGGER.warning("Чтение не удалось: %s", err)
                errors["base"] = "cannot_connect"
            else:
                name = info.name.strip()
                return self.async_create_entry(
                    title=name.split(" ")[0] + f" №{_serial_from_name(name)}",
                    data={
                        CONF_ADDRESS: address,
                        CONF_PIN: pin,
                        CONF_SERIAL: data.serial or _serial_from_name(name),
                    },
                )

        configured = self._async_current_ids(include_ignore=False)
        for info in bluetooth.async_discovered_service_info(self.hass, connectable=True):
            if _is_meter(info) and info.address not in configured:
                self._discovered[info.address] = info
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        options = {
            addr: f"№ {_serial_from_name(i.name)}  ({addr}, {i.rssi} dBm)"
            for addr, i in sorted(self._discovered.items(), key=lambda kv: -(kv[1].rssi or -200))
        }
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(options),
                    vol.Required(CONF_PIN): PIN_SCHEMA,
                }
            ),
            errors=errors,
        )

    async def _validate(self, address: str, pin: int):
        ble_device = bluetooth.async_ble_device_from_address(self.hass, address, connectable=True)
        if ble_device is None:
            raise BleakError("устройство не видно")
        try:
            return await async_read_meter(ble_device, pin, want_serial=True)
        except InvalidPin:
            await async_unpair(address)
            raise

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EnergomeraOptionsFlow()


class EnergomeraOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                    )
                }
            ),
        )
