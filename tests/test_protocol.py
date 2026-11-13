"""Тесты кадров МЭК 61107 поверх BLE."""

from __future__ import annotations

import pytest

STX, ETX, SOH = b"\x02", b"\x03", b"\x01"


def _with_parity(data: bytes) -> bytes:
    """Чётность 7E1, как её передаёт счётчик."""
    return bytes(b | 0x80 if bin(b).count("1") % 2 else b for b in data)


def _bcc(body: bytes) -> int:
    return sum(body) & 0x7F


# --- build_request ---------------------------------------------------------


def test_build_request_frame(protocol):
    frame = protocol.build_request("SNUMB()")
    plain = bytes(b & 0x7F for b in frame)
    payload = b"R1" + STX + b"SNUMB()" + ETX
    assert plain == b"/?!" + SOH + payload + bytes([_bcc(payload)])


def test_build_request_even_parity(protocol):
    frame = protocol.build_request("GRPNM(VOLTA()CURRE())")
    assert all(bin(b).count("1") % 2 == 0 for b in frame)


# --- split_fragments -------------------------------------------------------


def test_split_single_packet(protocol):
    frame = bytes(range(10))
    packets = protocol.split_fragments(frame, 23)
    assert packets == [b"\x80" + frame]


def test_split_single_packet_large_mtu(protocol):
    frame = bytes(range(10))
    assert protocol.split_fragments(frame, 100) == [b"\xc0" + frame]


def test_split_multiple_packets(protocol):
    frame = bytes(range(45))  # 19 + 19 + 7 при MTU 23
    packets = protocol.split_fragments(frame, 23)
    assert [p[0] for p in packets] == [0x00, 0x01, 0x82]
    assert [len(p) - 1 for p in packets] == [19, 19, 7]
    assert b"".join(p[1:] for p in packets) == frame


def test_split_respects_minimum_mtu(protocol):
    frame = bytes(range(30))
    assert protocol.split_fragments(frame, 10) == protocol.split_fragments(frame, 23)


# --- parse_response --------------------------------------------------------


def _response(text: str) -> bytes:
    body = text.encode("ascii") + ETX
    return _with_parity(STX + body + bytes([_bcc(body)]))


def test_parse_single_values(protocol):
    raw = _response("VOLTA(229.93)(230.10)(228.04)\r\nFREQU(50.01)\r\n")
    assert protocol.parse_response(raw) == {
        "VOLTA": ["229.93", "230.10", "228.04"],
        "FREQU": ["50.01"],
    }


def test_parse_group_with_repeated_names(protocol):
    raw = _response("EMD01(12.11.26,42392.68)(30000.1)(12392.5)EMD01(12.11.26,12.34)(10.0)")
    result = protocol.parse_response(raw)
    assert result["EMD01"] == ["12.11.26,42392.68", "30000.1", "12392.5", "12.11.26,12.34", "10.0"]


def test_parse_error_without_name(protocol):
    assert protocol.parse_response(_response("(ERR12)")) == {"": ["ERR12"]}


def test_parse_strips_whitespace(protocol):
    assert protocol.parse_response(_response("SNUMB( 012345678 )")) == {"SNUMB": ["012345678"]}


def test_parse_empty_raises(protocol):
    with pytest.raises(protocol.MeterProtocolError):
        protocol.parse_response(_response("garbage"))


# --- values_for ------------------------------------------------------------


def test_values_for_named(protocol):
    assert protocol.values_for("VOLTA()", {"VOLTA": ["1", "2"]}) == ["1", "2"]


def test_values_for_error(protocol):
    with pytest.raises(protocol.MeterProtocolError, match="ERR12"):
        protocol.values_for("VOLTA()", {"": ["ERR12"]})


def test_values_for_missing(protocol):
    with pytest.raises(protocol.MeterProtocolError):
        protocol.values_for("VOLTA()", {"FREQU": ["50"]})


# --- to_float --------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("228.93", 228.93),
        ("100.0*kWh", 100.0),
        ("12.11.26,42392.68", 42392.68),
        (" 0.5 ", 0.5),
        ("-1.25#x", -1.25),
    ],
)
def test_to_float(protocol, raw, expected):
    assert protocol.to_float(raw) == pytest.approx(expected)


def test_to_float_invalid(protocol):
    with pytest.raises(ValueError):
        protocol.to_float("ERR12")
