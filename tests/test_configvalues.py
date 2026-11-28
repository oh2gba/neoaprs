"""The checks of the settings that are more than a number, word or text (neoaprs/configvalues.py): what
each takes, what it keeps, and the code of each refusal."""

from collections.abc import Callable

import pytest

from neoaprs import configvalues as values
from neoaprs.coded import CodedError
from neoaprs.route import DIRECT_ONLY
from tests.support.english import page_english


def refused(check: Callable[[str], object], text: str) -> CodedError:
    with pytest.raises(CodedError) as caught:
        check(text)
    return caught.value


def refused_as_shown(check: Callable[[str], object], text: str, code: str, **params: object) -> None:
    """The refusal has `code` and `params`, and the log's sentence is the page's."""
    error = refused(check, text)
    assert (error.code, error.params) == (code, params)
    assert str(error) == page_english(error)


def test_device_patterns_are_absolute_paths_kept_with_single_spaces_up_to_500_characters() -> None:
    assert values.device_globs("  /dev/ttyUSB*   /dev/rfcomm0 ") == "/dev/ttyUSB* /dev/rfcomm0"
    for bad in ("", "   ", "dev/ttyUSB*", "/dev/ttyUSB* ttyACM*"):
        refused_as_shown(values.device_globs, bad, "setting.not_globs", value=bad)
    assert values.device_globs("/" + "a" * 499) == "/" + "a" * 499
    assert refused(values.device_globs, "/" + "a" * 500).code == "setting.too_long"


@pytest.mark.parametrize(
    "address", ["/dev/ttyUSB0", "COM3", "socket://h:8001", "TCP://h:8001", "bt://AA:BB", "ble://A"]
)
def test_a_port_is_a_device_or_an_address_of_the_four_schemes_in_any_case(address: str) -> None:
    assert values.port_address(address) == address


@pytest.mark.parametrize("address", ["spy://x", "loop://", "rfc2217://h:1", "hwgrep://x", "alt://x"])
def test_a_port_of_another_scheme_of_pyserial_is_refused(address: str) -> None:
    refused_as_shown(values.port_address, address, "setting.not_host", value=address)


def test_a_port_is_judged_by_its_first_scheme_alone() -> None:
    assert values.port_address("tcp://h:8001/a://b") == "tcp://h:8001/a://b"
    refused_as_shown(values.port_address, "spy://tcp://h:8001", "setting.not_host", value="spy://tcp://h:8001")


def test_a_port_is_at_most_255_characters() -> None:
    assert values.port_address("/" + "a" * 254)
    assert refused(values.port_address, "/" + "a" * 255).code == "setting.too_long"


def test_the_path_is_the_recommended_one_direct_or_the_calls_written_alike() -> None:
    assert values.digipeater_path("") == ""
    assert values.digipeater_path("DIRECT") == DIRECT_ONLY
    assert values.digipeater_path("wide1-1, WIDE2-1") == "WIDE1-1,WIDE2-1"
    assert refused(values.digipeater_path, "bad call!").code == "call.shape"


@pytest.mark.parametrize(
    ("text", "kept"), [("omni", "omni"), (" OMNI ", "omni"), ("Omni", "omni"), ("ne", "NE"), (" n ", "N"), ("sw", "SW")]
)
def test_the_antenna_direction_is_kept_as_omni_or_a_compass_point_in_capitals(text: str, kept: str) -> None:
    assert values.antenna_direction(text) == kept


@pytest.mark.parametrize("text", ["", "x", "NNE", "north", "OMNI1", "0"])
def test_any_other_antenna_direction_is_refused(text: str) -> None:
    refused_as_shown(values.antenna_direction, text, "setting.not_direction", value=text)


def test_every_direction_of_the_specifications_digit_is_taken_back_as_itself() -> None:
    assert [values.antenna_direction(d) for d in values.ANTENNA_DIRECTIONS] == list(values.ANTENNA_DIRECTIONS)


def test_the_symbol_table_is_one_of_the_two_tables_or_an_overlay() -> None:
    for table in ("/", "\\", "A", "Z", "0", "9"):
        assert values.symbol_table(table) == table
    for bad in ("", "a", "//", "#", " "):
        refused_as_shown(values.symbol_table, bad, "setting.not_symbol_table", value=bad)


def test_the_symbol_code_is_one_printable_character_other_than_space() -> None:
    for code in ("!", "-", "~", ">"):
        assert values.symbol_code(code) == code
    for bad in ("", " ", "ab", "ä"):
        refused_as_shown(values.symbol_code, bad, "setting.not_symbol_code", value=bad)
    assert refused(values.symbol_code, "\x7f").code == "setting.not_symbol_code"


def test_a_host_name_is_stripped_and_has_no_space_or_control_inside() -> None:
    assert values.host_name("  aprs.example.org ") == "aprs.example.org"
    for bad in ("", "  ", "a b"):
        refused_as_shown(values.host_name, bad, "setting.not_host", value=bad)
    for bad in ("a\tb", "a\x00"):
        assert refused(values.host_name, bad).code == "setting.not_host"


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "::1",
        "[::1]",
        "[2001:db8::7]",
        "[2001:db8::7:1]",
        "[2001:db8:0:0:0:0:0:1]",
        "localhost",
        "my_pi.lan",
        "a" * 63,
        ".".join(["a" * 63] * 4)[:253],
    ],
)
def test_a_host_is_an_address_an_address_in_brackets_or_a_name(host: str) -> None:
    assert values.is_host(host)


@pytest.mark.parametrize(
    "host",
    [
        "",
        "[::1",
        "fe80::1%eth0",
        "[fe80::1%eth0]",
        "-a.b",
        "a-.b",
        "a..b",
        "a" * 64,
        ".".join(["a" * 63] * 4)[:254],
        "[a.b]",
        "a b",
    ],
)
def test_a_scoped_address_a_bad_label_or_a_name_too_long_is_no_host(host: str) -> None:
    assert not values.is_host(host)


def test_a_list_of_hosts_is_kept_as_given_and_refused_whole_for_one_bad_name() -> None:
    assert values.host_list("") == "" and values.host_list("  ") == ""
    assert values.host_list(" 10.0.0.2, [::1],pi.lan ") == "10.0.0.2, [::1],pi.lan"
    error = refused(values.host_list, "pi.lan, bad name")
    assert (error.code, error.params) == ("setting.not_host", {"value": "pi.lan, bad name"})
    assert str(error) == "'bad name' is not an address or a name", "the log names the name that is wrong"
    assert refused(values.host_list, "a,,b").code == "setting.not_host"


def test_a_list_of_hosts_is_at_most_500_characters() -> None:
    names = ",".join(["h" * 9] * 50)  # 50 names of 9 and 49 commas: 499
    assert values.host_list(names + "x") == names + "x"
    error = refused(values.host_list, names + "xy")
    assert (error.code, error.params) == ("setting.not_host", {"value": names + "xy"})
    assert str(error) == f"{names + 'xy'!r} is not a list of addresses or names"


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("", ""),
        ("   ", ""),
        (" /maps/fi.pmtiles ", "/maps/fi.pmtiles"),
        ("https://t.example/{z}", "https://t.example/{z}"),
    ],
)
def test_the_map_source_is_empty_a_web_address_or_a_file(text: str, kept: str) -> None:
    assert values.map_source(text) == kept


def test_a_map_source_that_reads_as_an_option_or_is_too_long_or_unprintable_is_refused() -> None:
    assert values.map_source("a" * 500) == "a" * 500
    for bad in ("-o/etc/x", "a" * 501):
        refused_as_shown(values.map_source, bad, "setting.not_map_source", value=bad)
    assert refused(values.map_source, "/maps/a\x00b").code == "setting.not_map_source"


def test_a_map_source_with_a_scheme_is_http_or_https_with_no_space() -> None:
    assert values.map_source("HTTP://t.example") == "HTTP://t.example"
    for bad in ("ftp://t.example", "file:///etc/passwd", "http://t.example/a b", "http://[::1/x"):
        refused_as_shown(values.map_source, bad, "setting.not_web_address", value=bad)


def test_the_radio_types_are_their_keys_and_an_unknown_one_is_refused() -> None:
    assert values.tnc_profile("dummy") == "dummy"
    assert refused(values.tnc_profile, "no-such-type").code == "setting.not_profile"
    assert refused(values.hf_profile, "no-such-type").code == "setting.not_hf_profile"


def test_the_keying_is_empty_for_auto_or_one_the_modem_knows() -> None:
    assert values.mercury_keying("  ") == "" and values.mercury_keying("vox") == "vox"
    assert values.mercury_keying("rts:/dev/ttyUSB0") == "rts:/dev/ttyUSB0"
    assert refused(values.mercury_keying, "zz").code == "setting.not_keying"


def test_a_dial_is_empty_or_upper_sideband_from_a_tenth_of_a_megahertz() -> None:
    assert values.dial_or_empty(" ") == ""
    assert values.dial_or_empty(" 28.1800 MHz USB ") == "28.1800 MHz USB"
    assert values.dial_or_empty("0.1000 MHz USB") == "0.1000 MHz USB"
    for bad in ("28.1800 MHz LSB", "0.0900 MHz USB", "28.18", "USB"):
        refused_as_shown(values.dial_or_empty, bad, "setting.not_dial", value=bad.strip())


def test_the_aprs_is_server_is_host_and_port() -> None:
    assert values.aprsis_server(" rotate.aprs2.net:14580 ") == "rotate.aprs2.net:14580"
    for bad in ("rotate.aprs2.net", ":14580", "h:port"):
        refused_as_shown(values.aprsis_server, bad, "setting.not_server", value=bad)


def test_the_passcode_is_a_number_up_to_15_bits_kept_without_leading_zeros() -> None:
    assert values.passcode("") == "" and values.passcode(" 00123 ") == "123"
    assert values.passcode("32767") == "32767" and values.passcode("0") == "0"
    for bad in ("32768", "12a", "１２", "-5", "1.0"):
        refused_as_shown(values.passcode, bad, "setting.not_passcode", max=values.MAX_PASSCODE)


def test_the_passcode_for_reading_only_is_refused_with_its_own_reason() -> None:
    refused_as_shown(values.passcode, " -1 ", "setting.passcode_read_only", value=" -1 ")
