"""The symbol tables: names for the primary and alternate tables, overlays."""
import pytest

from neoaprs import symbols
from neoaprs.symbols import overlay, symbol_name, table_of, tracker_symbol


def test_the_tables_have_94_names_each() -> None:
    assert len(symbols._PRIMARY) == len(symbols._ALTERNATE) == 94


@pytest.mark.parametrize(("table", "code", "name"), [
    ("/", "-", "House"), ("/", ">", "Car"), ("/", "j", "Jeep"), ("/", "_", "Weather station"), ("/", "!", "Police"), ("/", "~", "TNC stream switch"),
    ("/", "0", "Circle"), ("/", "9", "Circle"), ("/", "#", "Digipeater"), ("/", "O", "Balloon"), ("/", "[", "Jogger"), ("/", "\\", "Triangle (DF)"),
    ("\\", "#", "Digipeater"), ("\\", "_", "Weather station (green)"), ("\\", "&", "Gateway"), ("\\", ">", "Car"), ("\\", "0", "Circle (IRLP, Echolink, WIRES)"),
    ("\\", "!", "Emergency"), ("\\", "~", "TNC stream switch"),
    ("D", "#", "Digipeater"), ("1", "&", "Gateway"), ("a", "&", "Gateway"),
])
def test_names(table: str, code: str, name: str) -> None:
    assert symbol_name(table, code) == name


@pytest.mark.parametrize(("table", "code"), [("/", " "), ("/", "\x7f"), ("/", ""), ("/", "ab"), ("?", "-"), ("", "-"), ("//", "-"), ("k", "-"), ("/", "é")])
def test_unknown(table: str, code: str) -> None:
    assert symbol_name(table, code) == "unknown"


def test_every_code_of_both_tables_has_a_name() -> None:
    for table in ("/", "\\"):
        names = [symbol_name(table, chr(c)) for c in range(33, 127)]
        assert "unknown" not in names
        assert all(names)


def test_overlay() -> None:
    assert [overlay(t) for t in ("/", "\\", "D", "5", "a", "j", "?")] == [None, None, "D", "5", "0", "9", None]


def test_compressed_overlay_letters_are_digits() -> None:
    assert [table_of(c) for c in "abcdefghij"] == list("0123456789")
    assert table_of("k") is None


# ---- the symbol of a tracker that sends raw GPS data
@pytest.mark.parametrize(("source", "destination", "want"), [
    ("OH2XYZ", "GPSMVV", ("/", ">")),                         # the specification's example: a car
    ("OH2XYZ", "GPSNV3", ("3", ">")),                         # a car with the overlay 3
    ("OH2XYZ", "GPSNVV", ("\\", ">")),                        # no overlay
    ("OH2XYZ", "GPSPR", ("/", "R")),                          # (the specification's own five character example)
    ("OH2XYZ", "GPSC30", ("/", ">")), ("OH2XYZ", "GPSE30", ("\\", ">")), ("OH2XYZ", "GPSC01", ("/", "!")),
    ("OH2XYZ", "SPCMVV", ("/", ">")), ("OH2XYZ", "GPSBBV-3", ("/", "!")), ("OH2XYZ", "gpslav", ("/", "a")),
    ("OH2XYZ-9", "APRS", ("/", ">")), ("OH2XYZ-8", "GPS", ("/", "s")), ("OH2XYZ-13", "GPSZZZ", ("/", "R")),
    ("OH2XYZ", "APRS", ("\\", ".")), ("OH2XYZ-0", "APRS", ("\\", ".")), ("OH2XYZ-16", "APRS", ("\\", ".")), ("OH2XYZ", "GPSC00", ("\\", ".")), ("OH2XYZ", "GPSC95", ("\\", ".")),
])
def test_the_symbol_of_a_gps_tracker(source: str, destination: str, want: tuple[str, str]) -> None:
    assert tracker_symbol(source, destination) == want


@pytest.mark.parametrize(("table", "code", "xy"), [
    ("/", "!", "BB"), ("/", "/", "BP"), ("/", "0", "P0"), ("/", "9", "P9"), ("/", ":", "MR"), ("/", "@", "MX"), ("/", "A", "PA"), ("/", "Z", "PZ"), ("/", "[", "HS"), ("/", "_", "HW"), ("/", "`", "HX"),
    ("/", "a", "LA"), ("/", "z", "LZ"), ("/", "{", "J1"), ("/", "|", "J2"), ("/", "}", "J3"), ("/", "~", "J4"),
    ("\\", "!", "OB"), ("\\", "0", "A0"), ("\\", "9", "A9"), ("\\", ":", "NR"), ("\\", ">", "NV"), ("\\", "A", "AA"), ("\\", "[", "DS"), ("\\", "a", "SA"), ("\\", "z", "SZ"), ("\\", "{", "Q1"), ("\\", "~", "Q4"),
])
def test_the_codes_of_the_appendix(table: str, code: str, xy: str) -> None:
    """Samples of the appendix of the specification (its column "GPS xyz": the xy of GPSxyV)."""
    assert tracker_symbol("A", f"GPS{xy}V") == (table, code)


def test_every_symbol_of_both_tables_has_a_destination_of_its_own() -> None:
    assert len(symbols._GPS_SYMBOLS) == 188 and set(symbols._GPS_SYMBOLS.values()) == {(t, chr(c)) for t in "/\\" for c in range(33, 127)}


@pytest.mark.parametrize(("table", "code"), [
    ("/", ">"), ("/", "k"), ("/", "v"), ("/", "u"), ("/", "b"), ("/", "<"), ("/", "["), ("/", "'"), ("/", "^"), ("/", "O"), ("/", "Y"), ("/", "s"), ("/", "C"), ("/", "R"), ("/", "j"), ("/", "U"), ("/", "F"),
    ("/", "e"), ("/", "*"), ("/", ")"), ("/", "a"), ("/", "f"), ("/", "P"), ("/", "X"), ("/", "g"), ("/", "="),
    ("\\", ">"), ("\\", "s"), ("\\", "u"), ("\\", "v"), ("\\", "^"), ("\\", "k"),
    ("E", ">"), ("5", "s"), ("e", ">"), ("A", "v"),
])
def test_the_symbol_of_a_station_that_moves_is_mobile(table: str, code: str) -> None:
    assert symbols.is_mobile(table, code), symbol_name(table, code)


@pytest.mark.parametrize(("table", "code"), [
    ("/", "-"), ("/", "#"), ("/", "_"), ("/", "r"), ("/", "h"), ("/", "y"), ("/", "&"), ("/", "I"), ("/", "!"), ("/", "-"), ("/", "l"), ("/", "0"),
    ("\\", "-"), ("\\", "#"), ("\\", "&"), ("\\", "_"), ("\\", "+"), ("\\", "0"),
    ("D", "#"), ("1", "&"), ("a", "&"), ("S", "-"),
    ("?", ">"), ("", ">"), ("/", ""), ("/", ">>"), ("/", " "), ("/", "é"),
])
def test_any_other_symbol_is_fixed(table: str, code: str) -> None:
    assert not symbols.is_mobile(table, code)


def test_the_mobile_list_names_only_symbols_that_exist_and_the_codes_are_what_the_names_say() -> None:
    for table, names in symbols.MOBILE_NAMES.items():
        assert names and set(names) <= set(symbols.SYMBOL_NAMES[table]) and "reserved" not in names and len(set(names)) == len(names)
        assert [symbol_name("/" if table == "primary" else "\\", code) for code in symbols.MOBILE_CODES[table]] == [n for n in symbols.SYMBOL_NAMES[table] if n in names]
