"""Сопряжение (bonding) со счётчиком по PIN через BlueZ D-Bus.

Счётчик требует LE Secure Connections с вводом passkey (PIN из формуляра,
"BLE-пароль радиоинтерфейса"). Штатный bluetooth HA не умеет отвечать на запрос
passkey, поэтому регистрируем свой BlueZ-агент на время вызова Device1.Pair().
После успешного сопряжения BlueZ хранит ключи и сам шифрует последующие соединения.

Работает только с локальным адаптером (hci) хоста HA, не через ESPHome-прокси.
"""

from __future__ import annotations

import asyncio
import logging

from dbus_fast import BusType, DBusError, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

_LOGGER = logging.getLogger(__name__)

BLUEZ = "org.bluez"
AGENT_PATH = "/org/homeassistant/energomera_ble/agent"
PAIR_TIMEOUT = 40


class PairingError(Exception):
    """Ошибка сопряжения."""


class InvalidPin(PairingError):
    """Счётчик отверг PIN."""


class NotLocalAdapter(PairingError):
    """Устройство не видно локальному BlueZ (например, только через прокси)."""


class _Agent(ServiceInterface):
    def __init__(self, pin: int) -> None:
        super().__init__("org.bluez.Agent1")
        self._pin = pin
        self.requested = False

    @method()
    def Release(self):  # noqa: N802
        pass

    @method()
    def RequestPasskey(self, device: "o") -> "u":  # noqa: N802,F821
        _LOGGER.debug("BlueZ запросил passkey для %s", device)
        self.requested = True
        return self._pin

    @method()
    def RequestPinCode(self, device: "o") -> "s":  # noqa: N802,F821
        self.requested = True
        return f"{self._pin:06d}"

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):  # noqa: N802,F821
        pass

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s"):  # noqa: N802,F821
        pass

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"):  # noqa: N802,F821
        pass

    @method()
    def RequestAuthorization(self, device: "o"):  # noqa: N802,F821
        pass

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"):  # noqa: N802,F821
        pass

    @method()
    def Cancel(self):  # noqa: N802
        _LOGGER.debug("BlueZ отменил запрос агенту")


async def _call(bus: MessageBus, path: str, interface: str, member: str, signature: str = "", body=None):
    reply = await bus.call(
        Message(
            destination=BLUEZ,
            path=path,
            interface=interface,
            member=member,
            signature=signature,
            body=body or [],
        )
    )
    if reply.message_type == MessageType.ERROR:
        raise DBusError(reply.error_name, reply.body[0] if reply.body else "")
    return reply.body


async def _find_device(bus: MessageBus, address: str) -> tuple[str, bool] | None:
    """Путь объекта устройства в BlueZ и признак Paired."""
    (objects,) = await _call(bus, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    address = address.upper()
    for path, ifaces in objects.items():
        dev = ifaces.get("org.bluez.Device1")
        if dev and dev["Address"].value.upper() == address:
            return path, bool(dev["Paired"].value)
    return None


async def _connect_bus() -> MessageBus:
    return await MessageBus(bus_type=BusType.SYSTEM, negotiate_unix_fd=False).connect()


async def async_is_paired(address: str) -> bool | None:
    """True/False — сопряжён ли; None — устройство не видно локальному BlueZ."""
    bus = await _connect_bus()
    try:
        found = await _find_device(bus, address)
        return None if found is None else found[1]
    finally:
        bus.disconnect()


async def async_pair(address: str, pin: int) -> None:
    """Сопрячься с устройством, если ещё не сопряжено."""
    bus = await _connect_bus()
    agent = _Agent(pin)
    registered = False
    try:
        found = await _find_device(bus, address)
        if found is None:
            raise NotLocalAdapter(f"{address} не найден в BlueZ")
        path, paired = found
        if paired:
            return

        bus.export(AGENT_PATH, agent)
        await _call(bus, "/org/bluez", "org.bluez.AgentManager1", "RegisterAgent", "os", [AGENT_PATH, "KeyboardOnly"])
        registered = True

        _LOGGER.info("Сопряжение с %s (%s)", address, path)
        try:
            await asyncio.wait_for(_call(bus, path, "org.bluez.Device1", "Pair"), PAIR_TIMEOUT)
        except DBusError as err:
            if err.type == "org.bluez.Error.AlreadyExists":
                return
            if err.type in ("org.bluez.Error.AuthenticationFailed", "org.bluez.Error.AuthenticationRejected"):
                raise InvalidPin(f"{err.type}: {err.text}") from err
            raise PairingError(f"{err.type}: {err.text}") from err
        except asyncio.TimeoutError as err:
            try:
                await _call(bus, path, "org.bluez.Device1", "CancelPairing")
            except DBusError:
                pass
            raise PairingError("Таймаут сопряжения") from err

        # доверенное устройство — чтобы BlueZ не спрашивал авторизацию
        await _call(
            bus, path, "org.freedesktop.DBus.Properties", "Set", "ssv",
            ["org.bluez.Device1", "Trusted", Variant("b", True)],
        )
        # Pair() сам устанавливает соединение — освобождаем его для HA
        try:
            await _call(bus, path, "org.bluez.Device1", "Disconnect")
        except DBusError:
            pass
        _LOGGER.info("Сопряжение с %s выполнено", address)
    finally:
        if registered:
            try:
                await _call(bus, "/org/bluez", "org.bluez.AgentManager1", "UnregisterAgent", "o", [AGENT_PATH])
            except DBusError:
                pass
        bus.disconnect()


async def async_unpair(address: str) -> None:
    """Удалить сопряжение (например, при смене PIN)."""
    bus = await _connect_bus()
    try:
        found = await _find_device(bus, address)
        if found is None or not found[1]:
            return
        path = found[0]
        adapter = path.rsplit("/", 1)[0]
        await _call(bus, adapter, "org.bluez.Adapter1", "RemoveDevice", "o", [path])
    finally:
        bus.disconnect()
