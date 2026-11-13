"""Расчёты по фазам: ток в нуле, перекос, обрыв нуля.

Модуль не зависит от Home Assistant, чтобы его можно было тестировать отдельно.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

PHASES = ("l1", "l2", "l3")

# Подозрение на обрыв нуля: одна фаза выше NEUTRAL_HIGH и одновременно другая ниже NEUTRAL_LOW.
# Норма по ГОСТ 32144 — 230 В ±10 % (207–253 В); при обрыве нуля напряжения расходятся
# далеко за эти пределы в разные стороны.
NEUTRAL_HIGH = 250.0
NEUTRAL_LOW = 200.0

# Ниже этого среднего тока перекос в процентах не считается (ночью он скачет бессмысленно).
MIN_AVG_CURRENT = 0.5

DEFAULT_IMBALANCE_THRESHOLD = 10.0  # А
IMBALANCE_DEBOUNCE = 2  # опросов подряд


def neutral_current(i1: float, i2: float, i3: float) -> float:
    """Ток в нулевом проводе при сдвиге фаз 120° и близком cos φ (приближённо)."""
    return math.sqrt(max(0.0, i1 * i1 + i2 * i2 + i3 * i3 - i1 * i2 - i2 * i3 - i3 * i1))


def spread(values: list[float]) -> float:
    """Разница между наибольшим и наименьшим значением."""
    return max(values) - min(values)


def imbalance_percent(values: list[float]) -> float | None:
    """Наибольшее отклонение от среднего в % от среднего (определение NEMA)."""
    avg = sum(values) / len(values)
    if avg < MIN_AVG_CURRENT:
        return None
    return max(abs(v - avg) for v in values) / avg * 100


def max_phase(values: list[float]) -> str:
    return PHASES[max(range(3), key=lambda i: values[i])]


def min_phase(values: list[float]) -> str:
    return PHASES[min(range(3), key=lambda i: values[i])]


def neutral_break_suspected(voltages: list[float]) -> bool:
    return max(voltages) > NEUTRAL_HIGH and min(voltages) < NEUTRAL_LOW


@dataclass
class Debounce:
    """Включается/выключается, только если условие держится `polls` опросов подряд."""

    polls: int = IMBALANCE_DEBOUNCE
    state: bool = False
    _count: int = 0

    def update(self, condition: bool) -> bool:
        if condition == self.state:
            self._count = 0
        else:
            self._count += 1
            if self._count >= self.polls:
                self.state = condition
                self._count = 0
        return self.state


def _phase_values(values: dict[str, Any], prefix: str) -> list[float] | None:
    keys = [f"{prefix}_{p}" for p in PHASES]
    if not all(isinstance(values.get(k), (int, float)) for k in keys):
        return None
    return [float(values[k]) for k in keys]


def derive(values: dict[str, Any], threshold: float, imbalance: Debounce) -> dict[str, Any]:
    """Производные величины по трём фазам. Для однофазного счётчика — пусто."""
    out: dict[str, Any] = {}

    if (currents := _phase_values(values, "current")) is not None:
        out["neutral_current"] = round(neutral_current(*currents), 2)
        out["current_spread"] = round(spread(currents), 2)
        pct = imbalance_percent(currents)
        # ключ есть всегда, иначе при малой нагрузке сенсор не создастся
        out["current_imbalance"] = round(pct, 1) if pct is not None else None
        out["max_load_phase"] = max_phase(currents)
        out["min_load_phase"] = min_phase(currents)
        out["phase_imbalance"] = imbalance.update(out["current_spread"] >= threshold)

    if (powers := _phase_values(values, "power")) is not None:
        out["power_spread"] = round(spread(powers), 3)

    if (voltages := _phase_values(values, "voltage")) is not None:
        out["neutral_break"] = neutral_break_suspected(voltages)

    return out


def _percent(value: float, limit: float) -> float:
    return round(value / limit * 100, 1)


def derive_limits(values: dict[str, Any], breaker_rating: float, allocated_power: float) -> dict[str, Any]:
    """Загрузка относительно вводного автомата (А) и выделенной мощности (кВт).

    Параметр, равный 0, выключает соответствующие сенсоры.
    """
    out: dict[str, Any] = {}

    if breaker_rating > 0:
        for p in PHASES:
            current = values.get(f"current_{p}")
            if isinstance(current, (int, float)):
                out[f"phase_load_{p}"] = _percent(current, breaker_rating)

    if allocated_power > 0:
        power = values.get("power_total")
        if not isinstance(power, (int, float)):
            # однофазный счётчик может не отдавать сумму — складываем фазы
            phase_powers = [values[k] for k in (f"power_{p}" for p in PHASES) if isinstance(values.get(k), (int, float))]
            power = sum(phase_powers) if phase_powers else None
        if power is not None:
            out["power_load"] = _percent(power, allocated_power)

    return out
