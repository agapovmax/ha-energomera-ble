"""Мастер настройки: обнаружение/выбор счётчика, ввод PIN, повторная аутентификация."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_ALLOCATED_POWER,
    CONF_BREAKER_RATING,
    CONF_DISCOVER_OTHERS,
    CONF_IMBALANCE_THRESHOLD,
    CONF_PIN,
    CONF_SERIAL,
    DEFAULT_DISCOVER_OTHERS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_ALLOCATED_POWER,
    MAX_BREAKER_RATING,
    MAX_IMBALANCE_THRESHOLD,
    MAX_SCAN_INTERVAL,
    MIN_IMBALANCE_THRESHOLD,
    MIN_SCAN_INTERVAL,
    NAME_PREFIXES,
)
from .meter import MeterData, async_read_meter
from .phases import DEFAULT_IMBALANCE_THRESHOLD
from .pairing import InvalidPin, PairingError, async_unpair
from .protocol import MeterProtocolError

_LOGGER = logging.getLogger(__name__)

PIN_SCHEMA = vol.All(vol.Coerce(int), vol.Range(min=0, max=999999))


def _is_meter(info: bluetooth.BluetoothServiceInfoBleak) -> bool:
    return bool(info.name) and info.name.strip().startswith(NAME_PREFIXES)


def _serial_from_name(name: str) -> str:
    # "CE308 #012345678    " -> "012345678"
    return name.split("#", 1)[-1].strip()


@callback
def async_discovery_enabled(hass: HomeAssistant) -> bool:
    """Показывать ли найденные счётчики.

    Пока не добавлено ни одного счётчика — да (так проще начать).
    Потом — только если хотя бы в одном счётчике включён параметр «Искать другие счётчики»:
    на столбе обычно висят счётчики соседей, и без этого они все всплывают как «Обнаружено».
    """
    entries = hass.config_entries.async_entries(DOMAIN, include_ignore=False)
    if not entries:
        return True
    return any(e.options.get(CONF_DISCOVER_OTHERS, DEFAULT_DISCOVER_OTHERS) for e in entries)


def _title(name: str) -> str:
    name = name.strip()
    return name.split(" ")[0] + f" №{_serial_from_name(name)}"


class EnergomeraConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, bluetooth.BluetoothServiceInfoBleak] = {}
        self._discovery_info: bluetooth.BluetoothServiceInfoBleak | None = None

    # --- общая проверка PIN ---------------------------------------------

    async def _validate(self, address: str, pin: int, unpair_first: bool) -> MeterData:
        ble_device = bluetooth.async_ble_device_from_address(self.hass, address, connectable=True)
        if ble_device is None:
            raise BleakError("устройство не видно")
        if unpair_first:
            # при существующем сопряжении новый PIN не проверяется — сбрасываем его
            await async_unpair(address)
        try:
            return await async_read_meter(ble_device, pin, want_serial=True)
        except InvalidPin:
            await async_unpair(address)
            raise

    async def _try_validate(
        self, address: str, pin: int, errors: dict[str, str], unpair_first: bool = False
    ) -> MeterData | None:
        """Проверить PIN чтением; при ошибке заполнить errors и вернуть None."""
        try:
            return await self._validate(address, pin, unpair_first)
        except InvalidPin:
            errors["base"] = "invalid_pin"
        except PairingError as err:
            _LOGGER.warning("Сопряжение не удалось: %s", err)
            errors["base"] = "pairing_failed"
        except (BleakError, MeterProtocolError, TimeoutError, OSError) as err:
            _LOGGER.warning("Чтение не удалось: %s", err)
            errors["base"] = "cannot_connect"
        return None

    def _create(
        self, info: bluetooth.BluetoothServiceInfoBleak, pin: int, data: MeterData
    ) -> ConfigFlowResult:
        return self.async_create_entry(
            title=_title(info.name),
            data={
                CONF_ADDRESS: info.address,
                CONF_PIN: pin,
                CONF_SERIAL: data.serial or _serial_from_name(info.name),
            },
        )

    # --- автообнаружение ------------------------------------------------

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not _is_meter(discovery_info):
            return self.async_abort(reason="not_supported")
        if not async_discovery_enabled(self.hass):
            return self.async_abort(reason="discovery_disabled")
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": _title(discovery_info.name)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery_info is not None
        info = self._discovery_info
        errors: dict[str, str] = {}
        if user_input is not None:
            pin = user_input[CONF_PIN]
            if (data := await self._try_validate(info.address, pin, errors)) is not None:
                return self._create(info, pin, data)

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PIN): PIN_SCHEMA}),
            description_placeholders={"name": _title(info.name)},
            errors=errors,
        )

    # --- ручное добавление ----------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            info = self._discovered[address]
            pin = user_input[CONF_PIN]
            if (data := await self._try_validate(address, pin, errors)) is not None:
                return self._create(info, pin, data)

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

    # --- повторная аутентификация (счётчик отверг PIN) ------------------

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            pin = user_input[CONF_PIN]
            if await self._try_validate(entry.data[CONF_ADDRESS], pin, errors, unpair_first=True):
                return self.async_update_reload_and_abort(entry, data_updates={CONF_PIN: pin})

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PIN): PIN_SCHEMA}),
            description_placeholders={"name": entry.title},
            errors=errors,
        )

    # --- перенастройка (смена PIN вручную) ------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            pin = user_input[CONF_PIN]
            if await self._try_validate(entry.data[CONF_ADDRESS], pin, errors, unpair_first=True):
                return self.async_update_reload_and_abort(entry, data_updates={CONF_PIN: pin})

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_PIN, default=entry.data[CONF_PIN]): PIN_SCHEMA}
            ),
            description_placeholders={"name": entry.title},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EnergomeraOptionsFlow()


class EnergomeraOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                    ),
                    vol.Required(
                        CONF_IMBALANCE_THRESHOLD,
                        default=options.get(CONF_IMBALANCE_THRESHOLD, DEFAULT_IMBALANCE_THRESHOLD),
                    ): vol.All(
                        vol.Coerce(float),
                        vol.Range(min=MIN_IMBALANCE_THRESHOLD, max=MAX_IMBALANCE_THRESHOLD),
                    ),
                    vol.Required(
                        CONF_BREAKER_RATING, default=options.get(CONF_BREAKER_RATING, 0)
                    ): vol.All(vol.Coerce(float), vol.Range(min=0, max=MAX_BREAKER_RATING)),
                    vol.Required(
                        CONF_ALLOCATED_POWER, default=options.get(CONF_ALLOCATED_POWER, 0)
                    ): vol.All(vol.Coerce(float), vol.Range(min=0, max=MAX_ALLOCATED_POWER)),
                    vol.Required(
                        CONF_DISCOVER_OTHERS,
                        default=options.get(CONF_DISCOVER_OTHERS, DEFAULT_DISCOVER_OTHERS),
                    ): bool,
                }
            ),
        )
