"""The packet log and the station cache (neoaprs/packetlog.py, packetcodec.py, packetsql.py) on a real database thread: what goes in comes out equal, the order, the care, and the rows the
tables refuse."""
import json
import logging
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs import aprsparse, ax25
from neoaprs.aprsisline import parse_is_line
from neoaprs.aprsextension import Area, DfBearing, Dfs, Extensions, Phg
from neoaprs.aprsfreq import Frequency
from neoaprs.aprsstorm import Storm
from neoaprs.aprslocator import Locator
from neoaprs.aprstelemetry import Telemetry
from neoaprs.clock import utc
from neoaprs.kiss import KissDecoder
from neoaprs.aprsthirdparty import parse_packet
from neoaprs.packet import ItemReport, Message, ObjectReport, Other, Packet, Position, Status, ThirdParty, Undecoded
from neoaprs.packetcodec import decode_decoded, encode_decoded, packet_of, packet_row, parse_stamp, stamp, tnc2
from neoaprs.packetlog import PacketLog
from neoaprs.station import Station
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.files import fixture_bytes
from tests.support.storedb import sql, store_at

T0 = utc(2026, 10, 21, 12, 0, 0)


def capture(at: object = T0) -> list[Packet]:
    out = []
    for frame in KissDecoder().feed(fixture_bytes("kiss/thd7-2026-10-21.bin")):
        f = ax25.decode(frame.payload)
        source, destination = str(f.source), str(f.destination)
        out.append(Packet(at, "in", frame.payload, source, destination, tuple(str(a) for a in f.path), f.info, aprsparse.parse(f.info, source, destination, at)))  # type: ignore[arg-type]
    return out


def made(decoded: object, at: object = T0, direction: str = "in") -> Packet:
    frame = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2AAA-3"), (ax25.Address.parse("WIDE1-1"),), info=b"!6010.00N/02456.00E>x")
    return Packet(at, direction, ax25.encode(frame), "OH2AAA-3", "APRS", ("WIDE1-1",), frame.info, decoded)  # type: ignore[arg-type]


POSITION = Position(60.1, 24.9, "/", ">", comment="åäö", course_deg=12, speed_kmh=3.5, altitude_m=44.0, timestamp=utc(2026, 10, 21, 11, 59, 0), messaging=True, compressed=True, ambiguity=1)
DETAILED = Position(60.1, 24.9, "\\", "l", "x", timestamp=utc(2026, 10, 21, 11, 59, 0), timestamp_local=True, locator=Locator("IO91sx", 51.97917, -0.45833, "/", "-"),
                    extensions=Extensions(phg=Phg(25, 6.1, 3, 90, 12.8), range_km=80.5, dfs=Dfs(2, 24.4, 6, None), df_bearing=DfBearing(270, 7, 6.4, 9), area=Area("filled ellipse", "cyan", 1.0, 1.0)))
LOCAL = Position(60.1, 24.9, "\\", "@", "x", frequency=Frequency(145.775, tone_hz=118, offset_khz=-600, range_km=40.2), storm=Storm("HC", 277.8, 370.4, 980, 166.7, 55.6, 74.1), sign="55")
DECODED = [POSITION, DETAILED, LOCAL, Status("on air", frequency=Frequency(145.5)), Telemetry(5, [199.0, 0.0, 255.0, 73.0, 123.5], "01101001", "x"), Telemetry(None, [1.0, 2.0, 3.0, 4.0, 5.0], "00000000"),
           Status("IO91 house", None, Locator("IO91", 51.5, -1.0, "/", "-")), Other("capabilities", "<IGATE,MSG_CNT=2", items={"IGATE": "", "MSG_CNT": "2"}), Other("weather", "_10090556c220", timestamp=utc(2026, 10, 9, 5, 56, 0)), Message("OH2BBB", "hello {7", "7"), Message("OH2BBB", "", ack_id="7"), ObjectReport("FIRE", True, POSITION, utc(2026, 10, 21, 11, 0, 0)), ItemReport("BUOY", False, POSITION),
           Status("on the road", utc(2026, 10, 21, 11, 0, 0)), Status("no time"), Other("telemetry", "T#001,1,2"), Undecoded("too short", "!60\xe4")]


@pytest.mark.parametrize("decoded", DECODED, ids=lambda d: type(d).__name__)
def test_the_json_of_what_the_parser_made_gives_it_back_equal(decoded: object) -> None:
    assert decode_decoded(encode_decoded(decoded)) == decoded  # type: ignore[arg-type]


def test_the_capture_decodes_the_same_from_the_json() -> None:
    for p in capture():
        assert decode_decoded(encode_decoded(p.decoded)) == p.decoded


def test_a_row_kept_before_the_details_were_decoded_is_read_with_their_defaults() -> None:
    """The JSON of a packet kept without the details has none of those fields: they take their defaults."""
    old = decode_decoded('{"type":"position","lat":60.1,"lon":24.9,"symbol_table":"/","symbol_code":">","comment":"x","course_deg":null,"speed_kmh":null,"altitude_m":null,"timestamp":null,"messaging":false,"compressed":false,"ambiguity":0,"weather":null}')
    assert old == Position(60.1, 24.9, "/", ">", "x") and decode_decoded('{"type":"status","text":"a","timestamp":null}') == Status("a")
    assert decode_decoded('{"type":"other","kind":"weather","text":"_1","weather":null}') == Other("weather", "_1")


def test_a_telemetry_report_is_a_packet_of_kind_other_with_a_type_of_its_own() -> None:
    p = made(Telemetry(5, [1.0, 2.0, 3.0, 4.0, 5.0], "01101001"))
    assert p.kind == "other" and packet_row(p).kind == "other" and json.loads(packet_row(p).decoded)["type"] == "telemetry" and packet_of(packet_row(p)) == p


def test_a_json_that_is_not_ours_is_refused() -> None:
    for text in ["{}", '{"kind": "weather"}', "[1]", "nonsense"]:
        with pytest.raises((ValueError, TypeError, KeyError, AttributeError)):
            decode_decoded(text)


def test_a_row_gives_the_packet_back_equal_and_a_stamp_sorts_as_the_time_does() -> None:
    for p in [*capture(), made(POSITION, direction="out"), made(Undecoded("why", "text"))]:
        assert packet_of(packet_row(p)) == p
    assert packet_row(made(Undecoded("why", "x"))).error == "why" and packet_row(made(POSITION)).error is None
    earlier, later = utc(2026, 10, 21, 9, 0, 0), utc(2026, 10, 21, 10, 0, 0) + timedelta(microseconds=5)
    assert stamp(earlier) == "2026-10-21T09:00:00.000000Z" and stamp(earlier) < stamp(later) and parse_stamp(stamp(later)) == later
    with pytest.raises(ValueError):
        stamp(later.replace(tzinfo=None))


def test_tnc2_is_the_monitor_line_with_the_unprintable_shown_as_a_question_mark() -> None:
    assert tnc2(capture()[1]) == "OH2RDK-7>APRX29,OH2RCH-2*,TRACE2-1:!6009.90NT02456.80E&432.500 MHz"
    odd = Packet(T0, "in", b"", "OH2AAA", "APRS", ("WIDE1-1",), b"a\x01b", Other("x", "y"))
    assert tnc2(odd) == "OH2AAA>APRS,WIDE1-1:a?b"


async def test_every_packet_is_kept_and_read_back_the_newest_first(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    packets = capture()
    for n, p in enumerate(packets):
        assert log.append(Packet(T0 + timedelta(seconds=n), p.direction, p.raw, p.source, p.destination, p.path, p.info, p.decoded))
    assert log.append(made(POSITION, T0 + timedelta(seconds=9), "out"))
    assert await log.count() == 5
    recent = await log.recent(3)
    assert [(p.source, p.direction) for p in recent] == [("OH2AAA-3", "out"), ("OH2PU-9", "in"), ("OH2RDS", "in")]
    assert recent[0] == made(POSITION, T0 + timedelta(seconds=9), "out")
    everything = await log.recent()
    assert [p.source for p in everything] == ["OH2AAA-3", "OH2PU-9", "OH2RDS", "OH2RDK-7", "OH2RDG"] and everything[-1].decoded == packets[0].decoded
    assert await log.recent(0) == []
    assert [p.source for p in await log.since(T0 + timedelta(seconds=2))] == ["OH2RDS", "OH2PU-9", "OH2AAA-3"], "the oldest first"
    assert await log.since(T0 + timedelta(days=1)) == []
    assert log.dropped == 0


async def test_the_rows_are_what_the_columns_say(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    log.append(capture()[3])
    log.append(made(Undecoded("too short", "!60")))
    await log.count()
    rows = await sql(store, "SELECT heard_at, direction, source, destination, path, kind, summary, error FROM packet ORDER BY id")
    assert rows[0] == ("2026-10-21T12:00:00.000000Z", "in", "OH2PU-9", "APOTC1", "OH2RCH-2*", "position", capture()[3].summary, None)
    assert rows[1][5:] == ("undecoded", "undecoded (too short): !60", "too short")
    assert [r[0] for r in await sql(store, "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'packet' ORDER BY name")] == ["packet_heard_at", "packet_source"]


async def test_prune_removes_the_packets_older_than_the_days_and_keeps_the_rest(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    clock = FixedClock()
    log = PacketLog(store.db, clock)
    for days_ago in (45, 31, 29, 1, 0):
        log.append(made(POSITION, T0 - timedelta(days=days_ago, seconds=-1 if days_ago == 31 else 0)))
    assert await log.prune(30) == 2
    assert [p.heard_at for p in await log.recent()] == [T0, T0 - timedelta(days=1), T0 - timedelta(days=29)]
    assert await log.prune(30) == 0 and await log.prune(1) == 1


async def test_a_station_is_kept_replaced_and_deleted_and_comes_back_without_its_track(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    a = Station("OH2AAA-3", first_heard=T0, last_heard=T0 + timedelta(minutes=5), kind="station", symbol_table="/", symbol_code=">", lat=60.1, lon=24.9, altitude_m=44.0, course_deg=12,
                speed_kmh=3.5, last_position_at=T0, last_status="QRV", last_comment="åäö", packets=3, last_path=("WIDE1-1*", "OH2RCH-2"), track=[(T0, 60.1, 24.9)], is_me=True)
    b = Station("FIRE", first_heard=T0, last_heard=T0 + timedelta(minutes=9), kind="object", reported_by="OH2AAA-3", packets=1)
    log.save_station(a)
    log.save_station(b)
    a.packets = 4
    log.save_station(a)
    stations = await log.stations()
    assert [s.call for s in stations] == ["FIRE", "OH2AAA-3"], "the latest heard first"
    back = stations[1]
    assert back == Station("OH2AAA-3", first_heard=T0, last_heard=T0 + timedelta(minutes=5), symbol_table="/", symbol_code=">", lat=60.1, lon=24.9, altitude_m=44.0, course_deg=12,
                           speed_kmh=3.5, last_position_at=T0, last_status="QRV", last_comment="åäö", packets=4, last_path=("WIDE1-1*", "OH2RCH-2"))
    assert stations[0].kind == "object" and stations[0].reported_by == "OH2AAA-3" and stations[0].lat is None and stations[0].last_path == ()
    assert log.delete_station("FIRE") and [s.call for s in await log.stations()] == ["OH2AAA-3"]


async def test_a_log_whose_database_is_not_open_says_no_and_reads_nothing(tmp_path: Path) -> None:
    log = PacketLog(None, FixedClock())
    assert not log.append(made(POSITION)) and not log.save_station(Station("X", first_heard=T0, last_heard=T0)) and not log.delete_station("X") and log.dropped == 3
    assert await log.recent() == [] and await log.count() == 0 and await log.stations() == [] and await log.prune(30) == 0 and not log.is_open()
    store = await store_at(tmp_path / DB_NAME)
    log.use(store.db)  # type: ignore[arg-type]
    assert log.is_open() and log.append(made(POSITION))
    assert store.db is not None
    await store.db.close()
    assert not log.append(made(POSITION)) and await log.recent() == [] and not log.is_open()


async def test_a_row_that_is_not_ours_is_left_out_and_told(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    log.append(made(POSITION))
    await sql(store, "INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded) VALUES (?, 'in', x'00', 'OH2X', 'APRS', '', 'other', 's', '{\"kind\":\"weather\"}')", stamp(T0))
    await sql(store, "INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, first_heard, last_heard, last_status, last_comment, packets, last_path) "
                     "VALUES ('BAD', 'station', '', '', '', 'yesterday', 'today', '', '', 1, '')")
    caplog.set_level(logging.WARNING, "neoaprs.packetlog")
    assert len(await log.recent()) == 1 and await log.stations() == []
    assert any("packet table" in r.getMessage() for r in caplog.records) and any("station table" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("statement, name", [
    ("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded) VALUES ('2026-10-21 12:00', 'in', x'00', 'A', 'B', '', 'other', 's', '{}')", "packet_heard_at_form"),
    ("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded) VALUES ('2026-10-21T12:00:00.000000Z', 'sideways', x'00', 'A', 'B', '', 'other', 's', '{}')", "packet_direction"),
    ("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded) VALUES ('2026-10-21T12:00:00.000000Z', 'in', x'00', '', 'B', '', 'other', 's', '{}')", "packet_source_present"),
    ("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded) VALUES ('2026-10-21T12:00:00.000000Z', 'in', x'00', 'A', 'B', '', 'weather', 's', '{}')", "packet_kind"),
    ("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded) VALUES ('2026-10-21T12:00:00.000000Z', 'in', x'00', 'A', 'B', '', 'other', 's', '{broken')", "packet_decoded_json"),
    ("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded, error) VALUES ('2026-10-21T12:00:00.000000Z', 'in', x'00', 'A', 'B', '', 'other', 's', '{}', 'e')", "packet_error_when_undecoded"),
    ("INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, first_heard, last_heard, last_status, last_comment, packets, last_path) VALUES ('', 'station', '', '', '', 'a', 'b', '', '', 0, '')", "station_call_present"),
    ("INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, first_heard, last_heard, last_status, last_comment, packets, last_path) VALUES ('X', 'thing', '', '', '', 'a', 'b', '', '', 0, '')", "station_kind"),
    ("INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, lat, lon, first_heard, last_heard, last_status, last_comment, packets, last_path) VALUES ('X', 'station', '', '', '', 91, 0, 'a', 'b', '', '', 0, '')", "station_lat_range"),
    ("INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, lat, lon, first_heard, last_heard, last_status, last_comment, packets, last_path) VALUES ('X', 'station', '', '', '', 0, 181, 'a', 'b', '', '', 0, '')", "station_lon_range"),
    ("INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, lat, first_heard, last_heard, last_status, last_comment, packets, last_path) VALUES ('X', 'station', '', '', '', 5, 'a', 'b', '', '', 0, '')", "station_position_together"),
    ("INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, first_heard, last_heard, last_status, last_comment, packets, last_path) VALUES ('X', 'station', '', '', '', 'a', 'b', '', '', -1, '')", "station_packets_count"),
])
async def test_the_tables_refuse_what_the_program_cannot_produce_and_say_which_check(tmp_path: Path, statement: str, name: str) -> None:
    store = await store_at(tmp_path / DB_NAME)
    with pytest.raises(sqlite3.IntegrityError, match=name):
        await sql(store, statement)


# ---- how the packets reached us

def heard(source: str, path: tuple[str, ...], at: object = T0, info: bytes = b"!6010.00N/02456.00E>x") -> Packet:
    frame = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse(source), tuple(ax25.Address.parse(p) for p in path), info=info)
    return Packet(at, "in", ax25.encode(frame), source, "APRS", path, info, Status("x"))  # type: ignore[arg-type]


def test_a_third_party_packet_comes_back_from_its_row_with_its_header_and_what_is_inside() -> None:
    p = aprsthirdparty_packet(b"}OH2DPN>APJYC1,TCPIP,OH7JHF-1*::OH2GBA   :ack10")
    again = packet_of(packet_row(p))
    assert again == p and again.third_party == ThirdParty("OH2DPN", "APJYC1", ("TCPIP", "OH7JHF-1*")) and again.sender == "OH2DPN" and again.gate == "OH7JHF-1"
    assert packet_row(p).summary == "ack 10 to OH2GBA via OH7JHF-1 (third-party)" and again.decoded == Message("OH2GBA", "", ack_id="10")


def test_a_row_written_before_third_party_packets_were_opened_reads_back_as_the_wrapper_it_was() -> None:
    old = packet_row(aprsthirdparty_packet(b"}N0CALL>APRS,TCPIP:!4903.50N/07201.75W-"))._replace(decoded=encode_decoded(Other("third-party", "}N0CALL>APRS,TCPIP:!4903.50N/07201.75W-")))
    again = packet_of(old)
    assert again.decoded == Other("third-party", "}N0CALL>APRS,TCPIP:!4903.50N/07201.75W-") and again.sender == "N0CALL" and again.gate == "OH7JHF-1"


def aprsthirdparty_packet(info: bytes) -> Packet:
    frame = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH7JHF-1"), (ax25.Address.parse("OH2RCH-3*"),), info=info)
    decoded, third = parse_packet(info, "OH7JHF-1", "APRS", T0)
    return Packet(T0, "in", ax25.encode(frame), "OH7JHF-1", "APRS", ("OH2RCH-3*",), info, decoded, third, "rf-gated" if third else "rf")


async def test_the_deliveries_are_the_routes_of_the_latest_packets_heard_by_sender_and_a_third_party_packet_is_its_inner_sender_with_the_gate(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    for n, p in enumerate([heard("OH2AAA", ("OH2RCH-2*",)), heard("OH2AAA", ("OH2RCH-2*",)), heard("OH2BBB", ()), aprsthirdparty_packet(b"}OH2DPN>APRS,TCPIP:>x"), heard("OH2AAA", ("OH2RCH-3*", "TRACE2-1"))]):
        log.append(Packet(T0 + timedelta(seconds=n), p.direction, p.raw, p.source, p.destination, p.path, p.info, p.decoded, p.third_party, p.via))
    log.append(made(POSITION, T0 + timedelta(seconds=9), "out"))
    assert await log.deliveries() == [("OH2AAA", ("OH2RCH-2*",), "", 2, T0 + timedelta(seconds=1), T0), ("OH2BBB", (), "", 1, T0 + timedelta(seconds=2), None),
                                      ("OH2DPN", ("OH2RCH-3*",), "OH7JHF-1", 1, T0 + timedelta(seconds=3), None), ("OH2AAA", ("OH2RCH-3*", "TRACE2-1"), "", 1, T0 + timedelta(seconds=4), None)], \
        "with when the latest of each was heard, and the one before it"
    assert await log.deliveries(2) == [("OH2DPN", ("OH2RCH-3*",), "OH7JHF-1", 1, T0 + timedelta(seconds=3), None), ("OH2AAA", ("OH2RCH-3*", "TRACE2-1"), "", 1, T0 + timedelta(seconds=4), None)], "only the latest packets are looked at"
    assert await log.deliveries(0) == []


# ---- the channel of a packet

def from_the_internet(info: bytes = b"=6012.34N/02456.78E-hi", source: str = "OH2AAA", at: object = T0) -> Packet:
    return parse_is_line(f"{source}>APRS,TCPIP*,qAC,T2FINLAND:".encode() + info, at)  # type: ignore[arg-type]


def test_a_packet_from_the_internet_is_a_row_with_its_channel_the_line_as_raw_and_comes_back_equal() -> None:
    packet = from_the_internet()
    row = packet_row(packet)
    assert (row.via, row.raw, row.path, row.source, row.kind) == ("is", b"OH2AAA>APRS,TCPIP*,qAC,T2FINLAND:=6012.34N/02456.78E-hi", "TCPIP*,qAC,T2FINLAND", "OH2AAA", "position")
    assert packet_of(row) == packet and packet_of(row).via == "is" and packet_of(row).info == packet.info
    assert tnc2(packet) == "OH2AAA>APRS,TCPIP*,qAC,T2FINLAND:=6012.34N/02456.78E-hi"
    wrapped = parse_is_line("OH7JHF-1>APRS,TCPIP*,qAC,T2FINLAND:}OH2DPN>APJYC1,TCPIP,OH7JHF-1*::OH2GBA   :ack10", T0)
    assert packet_of(packet_row(wrapped)) == wrapped and packet_of(packet_row(wrapped)).via == "is"


def test_a_packet_of_the_dummy_radio_is_kept_as_such_and_comes_back_equal() -> None:
    from dataclasses import replace
    made_up = replace(heard("QDUMMY-1", ("WIDE1*",)), via="dummy")
    assert packet_row(made_up).via == "dummy" and packet_of(packet_row(made_up)) == made_up
    gated = replace(aprsthirdparty_packet(b"}OH2DPN>APJYC1,TCPIP,OH7JHF-1*::OH2GBA   :ack10"), via="dummy")
    assert packet_of(packet_row(gated)).via == "dummy" and packet_of(packet_row(gated)).third_party is not None


def test_the_channel_of_a_packet_of_the_radio_is_kept_and_a_row_that_says_otherwise_is_made_right_from_the_frame() -> None:
    plain, gated = heard("OH2AAA", ("OH2RCH-2*",)), aprsthirdparty_packet(b"}OH2DPN>APJYC1,TCPIP,OH7JHF-1*::OH2GBA   :ack10")
    assert (packet_row(plain).via, packet_row(gated).via) == ("rf", "rf-gated")
    assert packet_of(packet_row(plain)).via == "rf" and packet_of(packet_row(gated)).via == "rf-gated"
    assert packet_of(packet_row(gated)._replace(via="rf")) == gated, "a row from before the channel was kept, or marked by the migration with less care"
    assert packet_of(packet_row(plain)._replace(via="rf-gated")) == plain
    with pytest.raises(ValueError, match="no channel"):
        packet_of(packet_row(plain)._replace(via="tcp"))


async def test_the_log_keeps_packets_from_the_internet_with_the_others_and_the_statements_of_the_radio_leave_them_out(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    log.append(heard("OH2AAA", ("OH2RCH-2*",), T0))
    log.append(from_the_internet(source="OH2AAA", at=T0 + timedelta(seconds=1)))
    log.append(from_the_internet(source="OH2NET", at=T0 + timedelta(seconds=2)))
    log.append(from_the_internet(b">just a status", "OH2AAA", T0 + timedelta(seconds=3)))
    assert [(p.source, p.via) for p in await log.recent()] == [("OH2AAA", "is"), ("OH2NET", "is"), ("OH2AAA", "is"), ("OH2AAA", "rf")]
    assert [p.via for p in await log.since(T0)] == ["rf", "is", "is", "is"]
    assert await log.heard_since("OH2AAA", T0) == [T0], "heard on the radio: the internet is not the air (?APRSH)"
    assert await log.heard_since("OH2NET", T0) == []
    assert await log.deliveries() == [("OH2AAA", ("OH2RCH-2*",), "", 1, T0, None)], "the routes are those of the radio"
    assert [w[0] for w in await log.positions(30)] == ["OH2AAA", "OH2NET"], "the tracks take the positions of the internet too"
    assert await log.count() == 4
    assert (await sql(store, "SELECT via, COUNT(*) FROM packet GROUP BY via ORDER BY via")) == [("is", 3), ("rf", 1)]


async def test_a_station_keeps_its_channels_in_the_cache(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log = PacketLog(store.db, FixedClock())
    station = Station("OH2AAA", first_heard=T0, last_heard=T0 + timedelta(minutes=5), lat=60.1, lon=24.9, packets=6, heard_rf=3, heard_rf_gated=1, heard_is=2, last_rf_at=T0 + timedelta(minutes=1),
                      last_rf_gated_at=T0 + timedelta(minutes=2), last_is_at=T0 + timedelta(minutes=5), position_via="is", last_position_at=T0)
    log.save_station(station)
    log.save_station(Station("OH2NONE", first_heard=T0, last_heard=T0))
    [first, second] = sorted(await log.stations(), key=lambda s: s.call)
    assert first == station
    assert (second.heard_rf, second.heard_rf_gated, second.heard_is, second.last_rf_at, second.last_rf_gated_at, second.last_is_at, second.position_via) == (0, 0, 0, None, None, None, None)
