"""Пояснения к сенсорам: показываются в атрибуте «Описание» окна объекта.

Значения атрибутов Home Assistant не переводит, поэтому язык выбирается по
языку системы при создании объекта (русский, иначе английский).
"""

from __future__ import annotations

_RU: dict[str, str] = {
    "energy_total": "Показание счётчика: вся учтённая электроэнергия с начала эксплуатации, сумма по всем тарифам.",
    "energy_t1": "Энергия по тарифу T1 с начала эксплуатации. При двухтарифном учёте T1 обычно — дневная зона (7:00–23:00).",
    "energy_t2": "Энергия по тарифу T2 с начала эксплуатации. При двухтарифном учёте T2 обычно — ночная зона (23:00–7:00).",
    "energy_t3": "Энергия по тарифу T3 с начала эксплуатации. Используется при трёхзонном учёте (обычно полупиковая зона).",
    "energy_t4": "Энергия по тарифу T4 с начала эксплуатации. Используется редко, при четырёхзонном тарифном расписании.",
    "energy_today": "Потреблено с начала текущих суток (по часам счётчика). В полночь обнуляется.",
    "energy_today_t1": "Потреблено с начала текущих суток по тарифу T1. В полночь обнуляется.",
    "energy_today_t2": "Потреблено с начала текущих суток по тарифу T2. В полночь обнуляется.",
    "power_total": "Активная мощность, которую дом потребляет прямо сейчас, сумма по всем фазам.",
    "cos_total": "Коэффициент мощности (cos φ): доля полезной (активной) мощности в полной. 1 — чисто активная нагрузка "
    "(обогреватели, чайник); ниже — двигатели, компрессоры, импульсные блоки питания.",
    "frequency": "Частота сети. Норма — 50 Гц, допустимо ±0,2 Гц.",
    "temperature": "Температура внутри корпуса счётчика.",
    "rssi": "Уровень Bluetooth-сигнала от счётчика до адаптера Home Assistant. Чем ближе к 0, тем лучше; "
    "ниже −90 дБм связь неустойчива.",
}

_EN: dict[str, str] = {
    "energy_total": "Meter reading: all energy recorded since commissioning, summed over all tariffs.",
    "energy_t1": "Energy on tariff T1 since commissioning. With a two-rate tariff T1 is usually the day rate.",
    "energy_t2": "Energy on tariff T2 since commissioning. With a two-rate tariff T2 is usually the night rate.",
    "energy_t3": "Energy on tariff T3 since commissioning. Used with three-rate tariffs (usually the shoulder rate).",
    "energy_t4": "Energy on tariff T4 since commissioning. Rarely used, only with four-rate schedules.",
    "energy_today": "Energy used since the start of the current day (meter clock). Resets at midnight.",
    "energy_today_t1": "Energy used today on tariff T1. Resets at midnight.",
    "energy_today_t2": "Energy used today on tariff T2. Resets at midnight.",
    "power_total": "Active power the house is drawing right now, summed over all phases.",
    "cos_total": "Power factor (cos φ): share of useful (active) power in apparent power. 1 means purely resistive "
    "load (heaters, kettle); lower values come from motors, compressors, switching power supplies.",
    "frequency": "Grid frequency. Nominal 50 Hz, ±0.2 Hz is acceptable.",
    "temperature": "Temperature inside the meter case.",
    "rssi": "Bluetooth signal strength from the meter to the Home Assistant adapter. Closer to 0 is better; "
    "below −90 dBm the link is unreliable.",
}

for _i in (1, 2, 3):
    _RU[f"energy_l{_i}"] = f"Энергия, учтённая по фазе L{_i} с начала эксплуатации."
    _EN[f"energy_l{_i}"] = f"Energy recorded on phase L{_i} since commissioning."
    _RU[f"power_l{_i}"] = (
        f"Активная мощность на фазе L{_i} прямо сейчас. Помогает увидеть перекос нагрузки между фазами."
    )
    _EN[f"power_l{_i}"] = f"Active power on phase L{_i} right now. Helps to spot phase imbalance."
    _RU[f"voltage_l{_i}"] = (
        f"Напряжение фазы L{_i} относительно нуля. Норма — 230 В ±10 % (207–253 В)."
    )
    _EN[f"voltage_l{_i}"] = f"Voltage of phase L{_i} to neutral. Nominal 230 V ±10 % (207–253 V)."
    _RU[f"current_l{_i}"] = (
        f"Ток в фазе L{_i}. Сравните с номиналом вводного автомата, чтобы понять запас по нагрузке."
    )
    _EN[f"current_l{_i}"] = (
        f"Current on phase L{_i}. Compare with the main breaker rating to see the load headroom."
    )


def describe(key: str, language: str) -> str | None:
    table = _RU if language.lower().startswith("ru") else _EN
    return table.get(key)


ALL_KEYS = frozenset(_RU) | frozenset(_EN)
