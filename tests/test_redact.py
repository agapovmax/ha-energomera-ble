"""Тесты скрытия адреса и серийного номера в тексте ошибок для диагностики."""

from __future__ import annotations


def test_none_and_empty_pass_through(redact):
    assert redact.redact_text(None) is None
    assert redact.redact_text("") == ""


def test_mac_with_colons(redact):
    text = "Device with address AA:BB:CC:DD:EE:0F was not found"
    assert "AA:BB" not in redact.redact_text(text)
    assert redact.redact_text(text) == "Device with address **REDACTED** was not found"


def test_lowercase_and_dashes(redact):
    assert redact.redact_text("aa-bb-cc-dd-ee-ff timeout") == "**REDACTED** timeout"


def test_bluez_object_path(redact):
    text = "[org.bluez.Error.Failed] /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF: le-connection-abort-by-local"
    result = redact.redact_text(text)
    assert "AA_BB" not in result
    assert result.startswith("[org.bluez.Error.Failed] /org/bluez/hci0/dev_**REDACTED**")


def test_explicit_secrets(redact):
    text = "Ошибка чтения: CE308 #012345678 не ответил"
    assert redact.redact_text(text, None, "012345678") == "Ошибка чтения: CE308 #**REDACTED** не ответил"


def test_plain_text_untouched(redact):
    text = "Счётчик сейчас не виден по Bluetooth"
    assert redact.redact_text(text, "AA:BB:CC:DD:EE:FF", None) == text


def test_longer_hex_is_not_a_mac(redact):
    text = "frame 0A:1B:2C:3D:4E:5F:60 bad"
    assert redact.redact_text(text) == text
