"""Скрытие идентификаторов счётчика в произвольном тексте (без зависимостей от Home Assistant)."""

from __future__ import annotations

import re

REDACTED = "**REDACTED**"

# MAC-адрес в любом написании: AA:BB:CC:DD:EE:FF, aa-bb-..., а также путь BlueZ dev_AA_BB_CC_DD_EE_FF
_MAC = re.compile(r"(?<![0-9A-Fa-f])(?<![0-9A-Fa-f][:_-])(?:[0-9A-Fa-f]{2}[:_-]){5}[0-9A-Fa-f]{2}(?![:_-]?[0-9A-Fa-f])")


def redact_text(text: str | None, *secrets: str | None) -> str | None:
    """Убирает из текста ошибки MAC-адреса и переданные значения (например, серийный номер)."""
    if not text:
        return text
    text = _MAC.sub(REDACTED, text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return text
