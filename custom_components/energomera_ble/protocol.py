"""Кадры МЭК-61107 (ГОСТ Р МЭК 61107) поверх BLE для Энергомера CE208/CE308.

Модуль не зависит от Home Assistant / bleak, чтобы его можно было тестировать отдельно.
"""

from __future__ import annotations

import re

SOH = 0x01
STX = 0x02
ETX = 0x03


class MeterProtocolError(Exception):
    """Счётчик вернул ошибку или некорректный ответ."""


def _even_parity(byte: int) -> int:
    byte &= 0x7F
    return byte | 0x80 if bin(byte).count("1") % 2 else byte


def build_request(command: str) -> bytes:
    """Запрос чтения без сеанса: /?!<SOH>R1<STX>CMD()<ETX><BCC>, 7E1."""
    body = bytes([SOH]) + b"R1" + bytes([STX]) + command.encode("ascii") + bytes([ETX])
    bcc = sum(body[1:]) & 0x7F  # от символа после SOH до ETX включительно
    frame = b"/?!" + body + bytes([bcc])
    return bytes(_even_parity(b) for b in frame)


def split_fragments(frame: bytes, mtu: int) -> list[bytes]:
    """Разбивает кадр на BLE-пакеты (1 байт заголовка + данные), как в прошивке модуля."""
    max_payload = max(mtu, 23) - 4
    packets: list[bytes] = []
    pos = 0
    seq = 0
    while pos < len(frame):
        chunk = frame[pos : pos + max_payload]
        pos += len(chunk)
        last = pos >= len(frame)
        if not packets:
            header = (0x80 | (0x40 if mtu > 23 else 0)) if last else 0x00
        else:
            seq = (seq + 1) & 0x7F
            header = seq | (0x80 if last else 0)
        packets.append(bytes([header]) + chunk)
    return packets


_ITEM_RE = re.compile(r"([A-Za-z0-9_]*)\(([^()]*)\)")


def parse_response(raw: bytes) -> dict[str, list[str]]:
    """<STX>NAME(v1)(v2)NAME2(v)<ETX><BCC> -> {"NAME": ["v1","v2"], "NAME2": ["v"]}."""
    text = bytes(b & 0x7F for b in raw).decode("ascii", "replace")
    if "\x02" in text:
        text = text[text.index("\x02") + 1 :]
    if "\x03" in text:
        text = text[: text.index("\x03")]
    text = text.replace("\r", "").replace("\n", "")

    result: dict[str, list[str]] = {}
    current = ""
    for name, value in _ITEM_RE.findall(text):
        if name:
            current = name
        result.setdefault(current, []).append(value.strip())
    if not result:
        raise MeterProtocolError(f"Пустой/непонятный ответ: {text!r}")
    return result


def values_for(command: str, response: dict[str, list[str]]) -> list[str]:
    """Значения из ответа для команды; ошибки ERRnn -> исключение."""
    name = command.split("(", 1)[0]
    values = response.get(name)
    if values is None:
        # ответ без имени параметра — обычно (ERRnn)
        values = response.get("", [])
    if not values:
        raise MeterProtocolError(f"{command}: нет данных в ответе {response}")
    if len(values) == 1 and values[0].startswith("ERR"):
        raise MeterProtocolError(f"{command}: счётчик вернул {values[0]}")
    return values


def to_float(value: str) -> float:
    """'228.93' / '100.0*kWh' / '12.11.26,42392.68' (берётся последнее поле)."""
    value = value.split(",")[-1]
    value = re.split(r"[*#]", value, maxsplit=1)[0].strip()
    return float(value)
