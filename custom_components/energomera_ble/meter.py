"""Обмен со счётчиком по BLE (GATT-сервис Энергомеры)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .const import RX_UUIDS, TX_UUID
from .pairing import NotLocalAdapter, async_is_paired, async_pair
from .protocol import (
    MeterProtocolError,
    build_request,
    parse_response,
    split_fragments,
    to_float,
    values_for,
)

_LOGGER = logging.getLogger(__name__)

RESPONSE_TIMEOUT = 6.0


@dataclass
class MeterData:
    """Снимок показаний."""

    serial: str | None = None
    values: dict[str, Any] = field(default_factory=dict)


class EnergomeraSession:
    """Одна BLE-сессия: запрос -> уведомление -> чтение фрагментов ответа."""

    def __init__(self, client: BleakClient) -> None:
        self._client = client
        self._event = asyncio.Event()
        self._fragments = 0
        self._lock = asyncio.Lock()

    def _on_notify(self, _char: Any, data: bytearray) -> None:
        self._fragments = data[0] if data else 0
        self._event.set()

    async def start(self) -> None:
        await self._client.start_notify(TX_UUID, self._on_notify)

    async def request_raw(self, command: str) -> dict[str, list[str]]:
        async with self._lock:
            self._event.clear()
            # MTU 23 — минимально допустимый, длинные кадры режутся на фрагменты
            for packet in split_fragments(build_request(command), 23):
                await self._client.write_gatt_char(TX_UUID, packet, response=False)
            await asyncio.wait_for(self._event.wait(), RESPONSE_TIMEOUT)
            count = min(self._fragments + 1, len(RX_UUIDS))
            raw = bytearray()
            for uuid in RX_UUIDS[:count]:
                raw += await self._client.read_gatt_char(uuid)
            _LOGGER.debug("%s -> %r", command, bytes(b & 0x7F for b in raw))
            return parse_response(bytes(raw))

    async def request(self, command: str) -> list[str]:
        return values_for(command, await self.request_raw(command))


_ = None
# Команда -> ключи значений по порядку (None — пропустить).
# EMD01(i.a): (дата,сумма)(T1)…(T10)(фаза1)(фаза2)(фаза3)
#   a=0 — фиксация "НА" текущие сутки, т.е. текущее показание счётчика
#   a=1 — накопление "ЗА" текущие сутки
GROUPS: list[list[tuple[str, list[str | None]]]] = [
    [
        ("VOLTA()", ["voltage_l1", "voltage_l2", "voltage_l3"]),
        ("CURRE()", ["current_l1", "current_l2", "current_l3"]),
        ("POWEP()", ["power_l1", "power_l2", "power_l3", "power_total"]),
        ("FREQU()", ["frequency"]),
        ("COS_f()", ["cos_l1", "cos_l2", "cos_l3", "cos_total"]),
        ("TERMO()", ["temperature"]),
    ],
    [
        ("EMD01(0.0)", ["energy_total", "energy_t1", "energy_t2", "energy_t3", "energy_t4",
                        _, _, _, _, _, _, "energy_l1", "energy_l2", "energy_l3"]),
        ("EMD01(0.1)", ["energy_today", "energy_today_t1", "energy_today_t2"]),
    ],
]


def _split_blocks(values: list[str]) -> list[list[str]]:
    """Значения одноимённых параметров: новый блок начинается со значения 'дата,число'."""
    if not any("," in v for v in values):
        return [values]
    blocks: list[list[str]] = []
    for v in values:
        if "," in v or not blocks:
            blocks.append([])
        blocks[-1].append(v)
    return blocks


def _store(data: MeterData, keys: list[str | None], values: list[str]) -> None:
    for key, raw in zip(keys, values):
        if key is None:
            continue
        try:
            data.values[key] = to_float(raw)
        except ValueError:
            _LOGGER.debug("%s: не число %r", key, raw)


async def _read_group(session: EnergomeraSession, group, data: MeterData) -> None:
    command = "GRPNM(" + "".join(cmd for cmd, _k in group) + ")"
    try:
        response = await session.request_raw(command)
    except (MeterProtocolError, asyncio.TimeoutError) as err:
        _LOGGER.debug("Групповой запрос не прошёл (%s), читаю по одному", err)
        for cmd, keys in group:
            try:
                _store(data, keys, await session.request(cmd))
            except (MeterProtocolError, asyncio.TimeoutError) as err2:
                _LOGGER.debug("%s: %s", cmd, err2)
        return

    blocks = {name: _split_blocks(vals) for name, vals in response.items()}
    for cmd, keys in group:
        name = cmd.split("(", 1)[0]
        if not blocks.get(name):
            _LOGGER.debug("%s: нет в ответе", cmd)
            continue
        values = blocks[name].pop(0)
        if len(values) == 1 and values[0].startswith("ERR"):
            _LOGGER.debug("%s: %s", cmd, values[0])
            continue
        _store(data, keys, values)


async def _read_all(session: EnergomeraSession, want_serial: bool) -> MeterData:
    data = MeterData()
    if want_serial:
        try:
            data.serial = (await session.request("SNUMB()"))[0]
        except (MeterProtocolError, asyncio.TimeoutError) as err:
            _LOGGER.debug("SNUMB не прочитан: %s", err)

    for group in GROUPS:
        await _read_group(session, group, data)

    if "temperature" in data.values:
        data.values["temperature"] = round(data.values["temperature"] * 0.01, 2)
    if not data.values:
        raise MeterProtocolError("Счётчик не ответил ни на один запрос")
    return data


async def async_ensure_paired(address: str, pin: int) -> None:
    try:
        paired = await async_is_paired(address)
    except Exception as err:  # noqa: BLE001 — D-Bus может быть недоступен
        _LOGGER.debug("Не удалось проверить сопряжение: %s", err)
        return
    if paired is False:
        await async_pair(address, pin)


async def async_read_meter(
    ble_device: BLEDevice, pin: int, want_serial: bool = False
) -> MeterData:
    """Подключиться, при необходимости сопрячься, прочитать всё и отключиться."""
    try:
        await async_ensure_paired(ble_device.address, pin)
    except NotLocalAdapter:
        _LOGGER.debug("%s не на локальном адаптере — сопряжение пропущено", ble_device.address)

    client = await establish_connection(
        BleakClientWithServiceCache,
        ble_device,
        ble_device.name or ble_device.address,
        max_attempts=3,
    )
    try:
        session = EnergomeraSession(client)
        await session.start()
        return await _read_all(session, want_serial)
    finally:
        await client.disconnect()

