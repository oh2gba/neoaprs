import json

import pytest

from neoaprs.ax25 import Address, Ax25Error, Frame, decode, encode
from tests.support.files import FIXTURES, fixture_bytes, fixture_text

NAMES = sorted(p.stem for p in (FIXTURES / "ax25").glob("*.bin"))


def raw_address(text: str, flag: bool = False, last: bool = False, ssid: int = 0) -> bytes:
    return bytes(ord(c) << 1 for c in text.ljust(6)) + bytes([0x60 | ssid << 1 | (0x80 if flag else 0) | (1 if last else 0)])


def raw_frame(*addresses: bytes, tail: bytes = b"\x03\xf0hi") -> bytes:
    """Addresses with the last one marked, then the tail."""
    marked = list(addresses)
    marked[-1] = marked[-1][:6] + bytes([marked[-1][6] | 1])
    return b"".join(marked) + tail


# --- Address ---------------------------------------------------------------------------------------------------------------------------------

def test_address_text() -> None:
    assert str(Address("OH2GBA", 7)) == "OH2GBA-7"
    assert str(Address("OH2GBA")) == "OH2GBA"
    assert str(Address("WIDE1", 1, True)) == "WIDE1-1*"
    assert str(Address("RELAY", 0, True)) == "RELAY*"


@pytest.mark.parametrize("text, expected", [
    ("OH2GBA-7", Address("OH2GBA", 7)),
    ("oh2gba", Address("OH2GBA")),
    ("WIDE1-1*", Address("WIDE1", 1, True)),
    ("RELAY*", Address("RELAY", 0, True)),
])
def test_address_parse(text: str, expected: Address) -> None:
    assert Address.parse(text) == expected
    assert Address.parse(str(expected)) == expected


@pytest.mark.parametrize("text", ["", "*", "OH2GBAX", "OH2GBA-16", "OH2GBA**", "OH2*GBA", "a b"])
def test_address_parse_refuses(text: str) -> None:
    with pytest.raises(Ax25Error):
        Address.parse(text)


@pytest.mark.parametrize("args", [("",), ("TOOLONG",), ("OH2GBA", 16), ("OH2GBA", -1), ("A>B",), ("A,B",), ("A:B",), ("A*",), ("A-1",), ("A B",), ("Å",), ("A\x7f",)])
def test_address_refuses_what_cannot_be_on_the_air_or_in_the_text_form(args: tuple[object, ...]) -> None:
    with pytest.raises(Ax25Error):
        Address(*args)  # type: ignore[arg-type]


def test_ax25_error_is_a_value_error() -> None:
    assert issubclass(Ax25Error, ValueError)


# --- Frame -----------------------------------------------------------------------------------------------------------------------------------

def make_frame(*path: str, info: bytes = b"!x") -> Frame:
    return Frame(Address("APRS"), Address("OH2GBA", 7), tuple(Address.parse(p) for p in path), info=info)


def test_frame_defaults_and_is_ui() -> None:
    frame = make_frame()
    assert (frame.control, frame.pid, frame.info.__class__) == (0x03, 0xF0, bytes)
    assert frame.is_ui
    assert Frame(frame.destination, frame.source, control=0x13).is_ui          # poll/final bit set
    assert not Frame(frame.destination, frame.source, control=0x3F).is_ui
    assert not Frame(frame.destination, frame.source, pid=0xCF).is_ui


def test_path_text_marks_the_last_digipeater_passed() -> None:
    assert make_frame().path_text == ""
    assert make_frame("WIDE1-1", "WIDE2-1").path_text == "WIDE1-1,WIDE2-1"
    assert make_frame("WIDE1-1*", "WIDE2-1").path_text == "WIDE1-1*,WIDE2-1"
    assert make_frame("WIDE1-1*", "WIDE2-1*").path_text == "WIDE1-1,WIDE2-1*"
    assert make_frame("OH2RDU*", "WIDE2-1").path_text == "OH2RDU*,WIDE2-1"


def test_tnc2() -> None:
    assert make_frame().tnc2() == "OH2GBA-7>APRS:!x"
    assert make_frame("WIDE1-1*", "WIDE2-1*", info=b">caf\xe9 \xff").tnc2() == "OH2GBA-7>APRS,WIDE1-1,WIDE2-1*:>caf\xe9 \xff"


def test_frame_refuses_nine_digipeaters_and_odd_fields() -> None:
    with pytest.raises(Ax25Error, match="digipeaters"):
        make_frame(*["WIDE1-1"] * 9)
    with pytest.raises(Ax25Error, match="repeated"):
        Frame(Address("APRS"), Address("OH2GBA", 0, True))
    with pytest.raises(Ax25Error, match="repeated"):
        Frame(Address("APRS", 0, True), Address("OH2GBA"))
    with pytest.raises(Ax25Error):
        Frame(Address("APRS"), Address("OH2GBA"), control=256)
    with pytest.raises(Ax25Error):
        Frame(Address("APRS"), Address("OH2GBA"), pid=-1)


# --- decode and encode -----------------------------------------------------------------------------------------------------------------------

def test_decode_by_hand() -> None:
    data = raw_address("APRS", flag=True) + raw_address("OH2GBA", ssid=7) + raw_address("WIDE1", flag=True, last=True, ssid=1) + b"\x03\xf0!6010.50N/02456.25E>"
    assert decode(data) == Frame(Address("APRS"), Address("OH2GBA", 7), (Address("WIDE1", 1, True),), info=b"!6010.50N/02456.25E>")


def test_decode_writes_a_lower_case_letter_in_capitals() -> None:
    data = raw_address("aprs", flag=True) + raw_address("oh2gba", ssid=7) + raw_address("Wide1", flag=True, last=True, ssid=1) + b"\x03\xf0!x"
    frame = decode(data)
    assert (str(frame.destination), str(frame.source), str(frame.path[0])) == ("APRS", "OH2GBA-7", "WIDE1-1*")
    assert frame.tnc2() == "OH2GBA-7>APRS,WIDE1-1*:!x"


def test_decode_reads_the_ssid_from_bits_1_to_4_only() -> None:
    data = raw_address("APRS") + raw_address("OH2GBA", last=True) + b"\x03\xf0"
    patched = data[:13] + bytes([0xFF]) + data[14:]                  # 0xFF: every bit of the source's seventh byte set
    frame = decode(patched)
    assert frame.source == Address("OH2GBA", 15)
    assert not frame.source.repeated                                  # the C bit of the source is not a repeated flag


def test_decode_ignores_the_c_bits() -> None:
    for dest_c in (False, True):
        for source_c in (False, True):
            data = raw_frame(raw_address("APRS", flag=dest_c), raw_address("OH2GBA", flag=source_c))
            assert decode(data) == Frame(Address("APRS"), Address("OH2GBA"), info=b"hi")


def test_decode_an_empty_information_field() -> None:
    frame = decode(raw_frame(raw_address("APRS"), raw_address("OH2GBA"), tail=b"\x03\xf0"))
    assert frame.info == b"" and frame.is_ui


def test_decode_a_poll_bit_ui_frame() -> None:
    frame = decode(raw_frame(raw_address("APRS"), raw_address("OH2GBA"), tail=b"\x13\xf0x"))
    assert (frame.control, frame.pid, frame.info) == (0x13, 0xF0, b"x")


def test_decode_a_ui_frame_with_another_pid() -> None:
    frame = decode(raw_frame(raw_address("APRS"), raw_address("OH2GBA"), tail=b"\x03\xcfdata"))
    assert (frame.pid, frame.info, frame.is_ui) == (0xCF, b"data", False)


def test_decode_a_non_ui_frame_keeps_what_follows_the_control_byte() -> None:
    frame = decode(raw_frame(raw_address("APRS"), raw_address("OH2GBA"), tail=b"\x3f"))
    assert (frame.control, frame.info, frame.is_ui) == (0x3F, b"", False)
    frame = decode(raw_frame(raw_address("APRS"), raw_address("OH2GBA"), tail=b"\x00\xf0abc"))
    assert (frame.control, frame.info, frame.is_ui) == (0x00, b"\xf0abc", False)


def test_a_short_call_is_padded_with_spaces_and_comes_back_without() -> None:
    frame = decode(raw_frame(raw_address("A"), raw_address("OH2GBA")))
    assert frame.destination.call == "A"
    assert encode(frame)[:7] == raw_address("A", flag=True)


@pytest.mark.parametrize("data, reason", [
    (b"", "shorter"),
    (b"\x00" * 14, "shorter"),
    (raw_address("APRS") + raw_address("OH2GBA") + b"\x03", "never ends"),                                          # 15 bytes, no end bit anywhere
    (raw_address("APRS") + raw_address("OH2GBA") + raw_address("WIDE1") + b"\x03\xf0x", "never ends"),
    (raw_address("APRS", last=True) + raw_address("OH2GBA") + b"\x03\xf0hi", "no source"),
    (raw_address("APRS") + raw_address("OH2GBA") + raw_address("WIDE1", last=True), "no control"),
    (raw_address("APRS", ssid=1) + raw_address("OH2GBA", last=True) + b"\x03", "no PID"),
    (b"".join(raw_address(f"D{i}") for i in range(10)) + raw_address("X", last=True) + b"\x03\xf0", "more than 8 digipeaters"),
    (b"".join(raw_address(f"D{i}") for i in range(10)) + b"\x03\xf0hello", "more than 8 digipeaters"),
])
def test_decode_refuses(data: bytes, reason: str) -> None:
    with pytest.raises(Ax25Error, match=reason):
        decode(data)


@pytest.mark.parametrize("bad_byte", [0x00, 0x3E, 0xFE])                                                           # the characters 0x00, 0x1F and 0x7F
def test_decode_refuses_a_character_outside_the_printable_range(bad_byte: int) -> None:
    data = bytearray(raw_frame(raw_address("APRS"), raw_address("OH2GBA")))
    data[2] = bad_byte
    with pytest.raises(Ax25Error, match="printable"):
        decode(bytes(data))


def test_decode_refuses_spaces_inside_a_call_and_empty_calls() -> None:
    with pytest.raises(Ax25Error, match="space"):
        decode(raw_frame(raw_address("AP S"), raw_address("OH2GBA")))
    with pytest.raises(Ax25Error, match="space"):
        decode(raw_frame(raw_address(""), raw_address("OH2GBA")))
    with pytest.raises(Ax25Error, match="space"):
        decode(raw_frame(raw_address(" PRS"), raw_address("OH2GBA")))


def test_decode_refuses_a_call_the_text_form_cannot_hold() -> None:
    with pytest.raises(Ax25Error, match="address 1"):
        decode(raw_frame(raw_address("APRS"), raw_address("OH,GBA")))


def test_eight_digipeaters_are_allowed_and_nine_are_not() -> None:
    eight = [raw_address(f"D{i}") for i in range(8)]
    assert len(decode(raw_frame(raw_address("APRS"), raw_address("OH2GBA"), *eight)).path) == 8
    with pytest.raises(Ax25Error, match="more than 8"):
        decode(raw_frame(raw_address("APRS"), raw_address("OH2GBA"), *eight, raw_address("D8")))


def test_encode_sets_the_c_bits_the_reserved_bits_and_the_end_bit() -> None:
    frame = make_frame("WIDE1-1*", "WIDE2-1", info=b"hi")
    expected = (raw_address("APRS", flag=True) + raw_address("OH2GBA", ssid=7) + raw_address("WIDE1", flag=True, ssid=1)
                + raw_address("WIDE2", last=True, ssid=1) + b"\x03\xf0hi")
    assert encode(frame) == expected


def test_encode_a_non_ui_frame_writes_no_pid() -> None:
    frame = Frame(Address("APRS"), Address("OH2GBA"), control=0x3F)
    assert encode(frame)[-1:] == b"\x3f" and len(encode(frame)) == 15
    assert decode(encode(frame)) == frame


def test_encode_a_ui_frame_with_another_pid() -> None:
    frame = Frame(Address("APRS"), Address("OH2GBA"), pid=0xCF, info=b"x")
    assert encode(frame)[-3:] == b"\x03\xcfx"
    assert decode(encode(frame)) == frame


def test_encode_refuses_an_information_field_over_256_bytes() -> None:
    assert len(encode(Frame(Address("APRS"), Address("OH2GBA"), info=b"x" * 256))) == 14 + 2 + 256
    with pytest.raises(Ax25Error, match="257 bytes, more than the 256"):
        encode(Frame(Address("APRS"), Address("OH2GBA"), info=b"x" * 257))


# --- the fixtures ----------------------------------------------------------------------------------------------------------------------------

def test_the_fixtures_are_there() -> None:
    assert {"position_unrepeated", "position_digipeated", "no_path", "eight_digipeaters", "mic_e", "non_ui"} <= set(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_decode_a_fixture(name: str) -> None:
    expected = json.loads(fixture_text(f"ax25/{name}.json"))
    frame = decode(fixture_bytes(f"ax25/{name}.bin"))
    assert str(frame.destination) == expected["destination"]
    assert str(frame.source) == expected["source"]
    assert [str(a) for a in frame.path] == expected["path"]
    assert frame.info == expected["info"].encode("latin-1")
    assert (frame.control, frame.pid, frame.is_ui) == (expected["control"], expected["pid"], expected["is_ui"])
    if expected["canonical"]:
        assert encode(frame) == fixture_bytes(f"ax25/{name}.bin")
    assert decode(encode(frame)) == frame


def test_fixture_monitor_text() -> None:
    texts = {name: decode(fixture_bytes(f"ax25/{name}.bin")).tnc2() for name in NAMES}
    assert texts["position_unrepeated"] == "OH2GBA-7>APRS,WIDE1-1,WIDE2-1:!6010.50N/02456.25E>NeoAPRS test"
    assert texts["position_digipeated"] == "OH2GBA-7>APRS,WIDE1-1,WIDE2-1*:!6010.50N/02456.25E>NeoAPRS test"
    assert texts["no_path"] == "OH2GBA>APRS:=6010.50N/02456.25E-no path, short"
    assert texts["eight_digipeaters"].startswith("OH2GBA-9>APRS,OH2RDU,OH2RDG,OH3RDX-1*,WIDE1-1,WIDE2-2,TCPIP,N0CALL-15,OH1A:")
    assert texts["mic_e"].startswith("OH2GBA-9>T7SYRS,WIDE1-1*:`c5\x7f\x1c\x9f>")
    assert texts["non_ui"] == "OH2GBA-7>OH2XYZ,OH2RDU:\xf0hello"


def test_the_fixtures_are_not_truncations_of_one_another() -> None:
    assert len({fixture_bytes(f"ax25/{n}.bin") for n in NAMES}) == len(NAMES)
