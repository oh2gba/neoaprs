"""Properties of the lines packets arrive in: raw NMEA, third-party headers, APRS-IS lines, TNC2 text
of a LoRa board and the monitor text of a TNC. Each refuses a damaged line only with its own error
(or None, or a rejected line), a TNC2 frame round-trips, and the monitor text gives the same frames
in any pieces.
"""

import math
from datetime import UTC, datetime

import pytest

from hypothesis import given
from hypothesis import strategies as st

from neoaprs import ax25
from neoaprs.aprsisline import PATH_MAX, IsLineError, parse_is_line
from neoaprs.aprsnmea import NmeaError, parse_nmea
from neoaprs.aprsthirdparty import header_of, parse_packet
from neoaprs.callsign import normal_name
from neoaprs.packet import IS, Position
from neoaprs.tnc2line import MAX_TEXT, LineReader, Tnc2Error, air_of, frame_of, from_air, text_of
from neoaprs.tnc2text import PENDING_SEC, Rejected, TextReader
from neoaprs.tnctextreader import accepts
from neoaprs.tncprofile import KISS, TNC_TEXT
from tests.support.files import FIXTURES
from tests.support.damaged import aprs_cases, mutated

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
CASES = aprs_cases()
NMEA = [c["info"].encode("latin-1") for c in CASES if c["info"][:1] == "$"]
THIRD_PARTY = [c["info"].encode("latin-1") for c in CASES if c["info"][:1] == "}"]
IS_LINES = [
    f"{c['source']}>{c['destination']},TCPIP*,qAC,T2FINLAND:{c['info']}".encode() for c in CASES if c["info"]
] + [
    b"OH2RDG-7>APRX29,WIDE1*,OH2RCH-2*,WIDE2-1,qAR,OH2RDK-1:!6010.00N/02456.00E>mobile",
    b"OH2XYZ>APRS,qAO,OH2RDK-1::OH2GBA   :Hello{12",
    b"# aprsc 2.1.15",
]
TNC2 = [f"{c['source']}>{c['destination']},WIDE1-1*,WIDE2-1:{c['info']}".encode("latin-1") for c in CASES[:60]]
MONITOR = [p.read_bytes() for p in sorted((FIXTURES / "text").iterdir()) if p.suffix in (".txt", ".bin")]
CALLS = st.from_regex(r"[A-Z0-9]{1,6}", fullmatch=True)
ADDRESSES = st.builds(ax25.Address, CALLS, st.integers(min_value=0, max_value=15))


def assert_on_earth(p: Position) -> None:
    assert -90 <= p.lat <= 90 and -180 <= p.lon <= 180
    assert p.speed_kmh is None or (math.isfinite(p.speed_kmh) and p.speed_kmh >= 0)
    assert p.course_deg is None or 0 <= p.course_deg < 360
    assert p.altitude_m is None or math.isfinite(p.altitude_m)


@given(st.binary(max_size=80).map(lambda b: b"$GP" + b) | mutated(NMEA))
def test_a_damaged_nmea_sentence_is_refused_with_nmea_error_or_is_on_earth(info: bytes) -> None:
    """parse_nmea of a damaged sentence gives None, NmeaError or a position on the Earth."""
    try:
        p = parse_nmea(info, "OH2XYZ", "GPS", NOW)
    except NmeaError:
        return
    if p is not None:
        assert_on_earth(p)


def test_a_superscript_digit_in_nmea_is_no_number() -> None:
    """A Latin-1 superscript two is isdigit() but no int: as a fix quality it is no fix, as a date no date."""
    gga = b"$GPGGA,123519,4807.038,N,01131.000,E,\xb2,08,0.9,545.4,M,46.9,M,,"
    assert parse_nmea(gga, "OH2XYZ", "GPS", NOW) is None
    rmc = b"$GPRMC,113519,A,4807.038,N,01131.000,E,022.4,084.4,\xb2\xb2\xb2\xb2\xb2\xb2,003.1,W"
    p = parse_nmea(rmc, "OH2XYZ", "GPS", NOW)
    assert p is not None and p.timestamp == datetime(2026, 10, 21, 11, 35, 19, tzinfo=UTC)


def test_a_negative_speed_in_nmea_is_a_damaged_field() -> None:
    """An RMC sentence with a negative speed is refused, not a position going backwards."""
    with pytest.raises(NmeaError):
        parse_nmea(b"$GPRMC,123519,A,4807.038,N,01131.000,E,-022.4,084.4,230394,003.1,W", "OH2XYZ", "GPS", NOW)


@given(st.binary(max_size=60).map(lambda b: b"}" + b) | mutated(THIRD_PARTY))
def test_a_third_party_header_names_stations_in_normal_form(info: bytes) -> None:
    """header_of of any field gives None or names in normal form; parse_packet never raises."""
    opened = header_of(info)
    if opened is not None:
        third, inner = opened
        assert inner and normal_name(third.source) == third.source
        assert normal_name(third.destination) == third.destination
    parse_packet(info, "OH2XYZ", "APRS", NOW)


@given(st.binary(max_size=100) | mutated(IS_LINES))
def test_a_damaged_is_line_is_refused_with_is_line_error_or_is_sound(line: bytes) -> None:
    """parse_is_line of any bytes raises only IsLineError, else a packet with sound names and path."""
    try:
        packet = parse_is_line(line, NOW)
    except IsLineError:
        return
    assert packet.via == IS and packet.info and packet.raw == line.rstrip(b"\r\n")
    assert normal_name(packet.source) == packet.source and normal_name(packet.destination) == packet.destination
    assert len(packet.path) <= PATH_MAX
    if isinstance(packet.decoded, Position):
        assert_on_earth(packet.decoded)


@given(
    ADDRESSES,
    ADDRESSES,
    st.lists(ADDRESSES, max_size=ax25.MAX_PATH),
    st.integers(min_value=0, max_value=ax25.MAX_PATH),
    st.binary(max_size=60),
)
def test_a_tnc2_frame_round_trips(
    source: ax25.Address, destination: ax25.Address, digis: list[ax25.Address], used: int, info: bytes
) -> None:
    """frame_of of text_of a frame, and from_air of air_of it, give the frame back."""
    path = tuple(ax25.Address(d.call, d.ssid, i < used) for i, d in enumerate(digis))
    frame = ax25.Frame(destination, source, path, info=info)
    assert frame_of(text_of(frame)) == frame
    assert from_air(air_of(frame)) == frame


@given(st.binary(max_size=80) | mutated(TNC2))
def test_damaged_tnc2_text_is_refused_with_tnc2_error(text: bytes) -> None:
    """frame_of of any bytes raises only Tnc2Error."""
    try:
        frame_of(text)
    except Tnc2Error:
        pass


@given(st.lists(st.binary(max_size=40) | mutated(TNC2).map(lambda t: t + b"\r\n"), max_size=6))
def test_a_board_line_reader_never_raises(chunks: list[bytes]) -> None:
    """LineReader of any bytes gives lines whose frame, if any, fits a LoRa packet."""
    reader = LineReader()
    for chunk in chunks:
        for line in reader.feed(chunk):
            assert line.frame is None or len(line.text) <= MAX_TEXT


def _read(reader: TextReader, chunks: list[bytes]) -> list[ax25.Frame | Rejected]:
    return [item for chunk in chunks for item in reader.feed(chunk, 0.0)] + reader.feed(b"", PENDING_SEC + 1.0)


@given(mutated(MONITOR, max_edits=6), st.lists(st.integers(min_value=0, max_value=4000), max_size=8))
def test_damaged_monitor_text_gives_the_same_frames_in_any_pieces(data: bytes, cuts: list[int]) -> None:
    """TextReader of damaged monitor text never raises, and the same bytes in pieces give the same."""
    whole = _read(TextReader(), [data])
    edges = [0, *sorted(c % (len(data) + 1) for c in cuts), len(data)]
    assert _read(TextReader(), [data[a:b] for a, b in zip(edges, edges[1:])]) == whole
    for item in whole:
        if isinstance(item, ax25.Frame):
            assert len(item.info) <= ax25.MAX_INFO and len(item.path) <= ax25.MAX_PATH


@given(st.binary(max_size=200) | mutated(MONITOR))
def test_what_a_port_says_is_judged_without_raising(heard: bytes) -> None:
    """accepts of any bytes gives a yes or a no for a text and a KISS profile."""
    assert accepts(TNC_TEXT, heard) in (True, False)
    assert accepts(KISS, heard) in (True, False)
