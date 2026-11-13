"""protocol.py не зависит от Home Assistant — грузим его напрямую, минуя __init__.py пакета."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

_PATH = Path(__file__).parent.parent / "custom_components" / "energomera_ble" / "protocol.py"


def _load():
    spec = importlib.util.spec_from_file_location("energomera_protocol", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def protocol():
    return _load()
