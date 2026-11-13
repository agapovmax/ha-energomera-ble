"""Тесты расчётов по фазам."""

from __future__ import annotations

import math

import pytest


# --- ток в нуле ------------------------------------------------------------


def test_neutral_current_balanced_is_zero(phases):
    assert phases.neutral_current(10, 10, 10) == pytest.approx(0)


def test_neutral_current_single_phase_equals_phase_current(phases):
    assert phases.neutral_current(16, 0, 0) == pytest.approx(16)


def test_neutral_current_two_equal_phases(phases):
    # две одинаково загруженные фазы, третья пустая: ток в нуле равен току фазы
    assert phases.neutral_current(10, 10, 0) == pytest.approx(10)


def test_neutral_current_matches_vector_sum(phases):
    i = (3.41, 0.33, 2.0)
    angles = (0, -2 * math.pi / 3, 2 * math.pi / 3)
    re = sum(a * math.cos(t) for a, t in zip(i, angles))
    im = sum(a * math.sin(t) for a, t in zip(i, angles))
    assert phases.neutral_current(*i) == pytest.approx(math.hypot(re, im))


# --- перекос ---------------------------------------------------------------


def test_spread(phases):
    assert phases.spread([3.41, 0.33, 2.0]) == pytest.approx(3.08)


def test_imbalance_percent(phases):
    # среднее 10, наибольшее отклонение 5 -> 50 %
    assert phases.imbalance_percent([15, 10, 5]) == pytest.approx(50)


def test_imbalance_percent_low_load_is_none(phases):
    assert phases.imbalance_percent([0.4, 0.1, 0.2]) is None


def test_max_min_phase(phases):
    assert phases.max_phase([3.41, 0.33, 2.0]) == "l1"
    assert phases.min_phase([3.41, 0.33, 2.0]) == "l2"


# --- обрыв нуля ------------------------------------------------------------


@pytest.mark.parametrize(
    ("voltages", "expected"),
    [
        ([230, 231, 229], False),
        ([253, 240, 236], False),  # высоко, но нет «провала» на другой фазе
        ([235, 195, 230], False),  # просадка на одной фазе без перекоса вверх
        ([285, 170, 232], True),
        ([251, 230, 199], True),
    ],
)
def test_neutral_break(phases, voltages, expected):
    assert phases.neutral_break_suspected(voltages) is expected


# --- антидребезг -----------------------------------------------------------


def test_debounce_needs_consecutive_polls(phases):
    d = phases.Debounce(polls=2)
    assert d.update(True) is False
    assert d.update(False) is False  # прервалось — счёт сначала
    assert d.update(True) is False
    assert d.update(True) is True
    assert d.update(False) is True
    assert d.update(False) is False


# --- derive ----------------------------------------------------------------


def _three_phase(**over):
    values = {
        "current_l1": 20.0, "current_l2": 2.0, "current_l3": 5.0,
        "power_l1": 4.5, "power_l2": 0.4, "power_l3": 1.1,
        "voltage_l1": 228.0, "voltage_l2": 236.0, "voltage_l3": 233.0,
    }
    values.update(over)
    return values


def test_derive_three_phase(phases):
    d = phases.Debounce(polls=2)
    out = phases.derive(_three_phase(), 10, d)
    assert out["current_spread"] == pytest.approx(18)
    assert out["power_spread"] == pytest.approx(4.1)
    assert out["max_load_phase"] == "l1"
    assert out["min_load_phase"] == "l2"
    assert out["neutral_break"] is False
    assert out["phase_imbalance"] is False  # первый опрос
    assert phases.derive(_three_phase(), 10, d)["phase_imbalance"] is True


def test_derive_low_load_keeps_imbalance_key(phases):
    out = phases.derive(_three_phase(current_l1=0.1, current_l2=0.1, current_l3=0.2), 10, phases.Debounce())
    assert "current_imbalance" in out and out["current_imbalance"] is None


def test_derive_single_phase_is_empty(phases):
    values = {"current_l1": 5.0, "power_l1": 1.1, "voltage_l1": 230.0}
    assert phases.derive(values, 10, phases.Debounce()) == {}
