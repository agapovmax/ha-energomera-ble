"""Модули без зависимостей от Home Assistant грузим напрямую, минуя __init__.py пакета."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parent.parent / "custom_components" / "energomera_ble"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"energomera_{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def protocol():
    return _load("protocol")


@pytest.fixture(scope="session")
def phases():
    return _load("phases")
