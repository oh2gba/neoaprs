import pytest

from neoaprs.callsign import CallsignError, format_call, normal_name, parse_call


@pytest.mark.parametrize("text, expected", [
    ("OH2GBA-7", ("OH2GBA", 7)),
    ("OH2GBA", ("OH2GBA", 0)),
    ("oh2gba-7", ("OH2GBA", 7)),
    ("OH2GBA-0", ("OH2GBA", 0)),
    ("OH2GBA-15", ("OH2GBA", 15)),
    ("N0CALL-1", ("N0CALL", 1)),
    ("A", ("A", 0)),
    ("APRS", ("APRS", 0)),
    ("APK102", ("APK102", 0)),
    ("WIDE1-1", ("WIDE1", 1)),
    ("RELAY", ("RELAY", 0)),
    ("TCPIP", ("TCPIP", 0)),
    ("BEACON", ("BEACON", 0)),
])
def test_parse_call(text: str, expected: tuple[str, int]) -> None:
    assert parse_call(text) == expected


@pytest.mark.parametrize("text", [
    "", "-7", "OH2GBA-", "OH2GBA-16", "OH2GBA-99", "OH2GBA-123", "OH2GBA--1", "OH2GBA-x", "OH2GBA-1-2",
    "OH2GBAA", "OH2GBAA-1", "OH 2GBA", "OH2GBA ", " OH2GBA", "OH2GBA\n", "OH2.GBA", "OH2GBA*", "ÅH2GBA", "OH2GBÄ", "ßa", "OH2GBA-٣",
])
def test_parse_call_refuses_and_names_the_text(text: str) -> None:
    with pytest.raises(CallsignError) as caught:
        parse_call(text)
    assert repr(text) in str(caught.value)


def test_callsign_error_is_a_value_error() -> None:
    assert issubclass(CallsignError, ValueError)


def test_format_call() -> None:
    assert format_call("OH2GBA", 7) == "OH2GBA-7"
    assert format_call("OH2GBA", 0) == "OH2GBA"
    assert format_call("WIDE1", 15) == "WIDE1-15"


@pytest.mark.parametrize("text", ["OH2GBA-7", "oh2gba", "APRS", "APK102", "WIDE1-1", "RELAY", "TCPIP", "BEACON"])
def test_valid_calls(text: str) -> None:
    parse_call(text)


def test_a_seventh_character_is_not_valid() -> None:
    with pytest.raises(CallsignError):
        parse_call("OH2GBAX")


def test_parse_and_format_round_trip() -> None:
    for text in ("OH2GBA-7", "OH2GBA", "WIDE2-2"):
        assert format_call(*parse_call(text)) == text


@pytest.mark.parametrize("text, expected", [
    ("oh2gba-0", "OH2GBA"), (" OH2GBA-7 ", "OH2GBA-7"), ("OH2XYZ-L", "OH2XYZ-L"), ("oh2xyz-20", "OH2XYZ-20"), ("WINLINK", "WINLINK"), ("oh2xy-123", "OH2XY-123"), ("A", "A"),
])
def test_a_name_of_a_station_on_the_internet_is_a_call_or_1_to_9_letters_digits_and_hyphens(text: str, expected: str) -> None:
    assert normal_name(text) == expected


@pytest.mark.parametrize("text", ["", "-L", "OH2XYZ-1234", "OH2 XYZ", "OH2XYZ*", "OH2_XYZ", "ÅH2GBA", "ßa"])
def test_a_name_that_aprs_is_does_not_allow_is_refused(text: str) -> None:
    with pytest.raises(CallsignError):
        normal_name(text)


@pytest.mark.parametrize("text", ["OH2XYZ-L", "OH2XYZ-20", "WINLINK"])
def test_such_a_name_is_still_no_ax25_call(text: str) -> None:
    with pytest.raises(CallsignError):
        parse_call(text)
