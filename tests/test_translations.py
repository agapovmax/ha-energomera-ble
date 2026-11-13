"""Каждый сенсор переведён и описан на обоих языках."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent / "custom_components" / "energomera_ble"


def _descriptions():
    spec = importlib.util.spec_from_file_location("energomera_descriptions", ROOT / "descriptions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _translations(lang: str) -> dict:
    return json.loads((ROOT / "translations" / f"{lang}.json").read_text(encoding="utf-8"))


def test_same_sensor_keys_in_all_languages():
    assert set(_translations("ru")["entity"]["sensor"]) == set(_translations("en")["entity"]["sensor"])


def test_strings_json_matches_english():
    strings = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))
    assert strings == _translations("en")


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("platform", ["sensor", "binary_sensor"])
def test_every_entity_has_description(lang, platform):
    describe = _descriptions().describe
    for key in _translations(lang)["entity"][platform]:
        assert describe(key, lang), key


def test_same_binary_sensor_keys_in_all_languages():
    assert set(_translations("ru")["entity"]["binary_sensor"]) == set(
        _translations("en")["entity"]["binary_sensor"]
    )


def test_unknown_language_falls_back_to_english():
    d = _descriptions()
    assert d.describe("frequency", "de") == d.describe("frequency", "en")
