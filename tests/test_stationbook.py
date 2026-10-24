"""The station book (neoaprs/stationbook.py): what a packet does to it, the track, objects and items, us, pruning, and the signals; with the packets of the live capture and made-up ones."""
from datetime import datetime, timedelta

import pytest

from neoaprs import aprsparse, ax25
from neoaprs.aprsextension import Extensions
from neoaprs.aprslocator import Locator
from neoaprs.aprstelemetry import Telemetry
from neoaprs.aprsweather import Weather
from neoaprs.clock import utc
from neoaprs.kiss import KissDecoder
from neoaprs.packet import ItemReport, Message, ObjectReport, Other, Packet, Position, Status, ThirdParty, Undecoded
from neoaprs.station import Station
from neoaprs.stationbook import DEFINITIONS_MAX, TRACK_MAX, StationBook
from tests.support.files import fixture_bytes

T0 = utc(2026, 10, 21, 12, 0, 0)


def position(lat: float = 60.17, lon: float = 24.94, **kw: object) -> Position:
    return Position(lat=lat, lon=lon, symbol_table=str(kw.pop("symbol_table", "/")), symbol_code=str(kw.pop("symbol_code", ">")), **kw)  # type: ignore[arg-type]


def packet(decoded: object, source: str = "OH2AAA", at: datetime = T0, direction: str = "in", path: tuple[str, ...] = ("OH2RCH-2*",)) -> Packet:
    return Packet(heard_at=at, direction=direction, raw=b"", source=source, destination="APRS", path=path, info=b"", decoded=decoded)  # type: ignore[arg-type]


def capture() -> list[Packet]:
    out = []
    for frame in KissDecoder().feed(fixture_bytes("kiss/thd7-2026-10-21.bin")):
        f = ax25.decode(frame.payload)
        source, destination = str(f.source), str(f.destination)
        out.append(Packet(T0, "in", frame.payload, source, destination, tuple(str(a) for a in f.path), f.info, aprsparse.parse(f.info, source, destination, T0)))
    return out


class Heard:
    def __init__(self, book: StationBook) -> None:
        self.changed: list[tuple[str, int]] = []
        self.removed: list[str] = []
        book.changed.connect(lambda s: self.changed.append((s.call, s.packets)))
        book.removed.connect(self.removed.append)


def test_the_live_capture_gives_four_stations_with_positions() -> None:
    book = StationBook()
    for p in capture():
        assert book.take(p) is not None
    assert sorted(s.call for s in book.stations()) == ["OH2PU-9", "OH2RDG", "OH2RDK-7", "OH2RDS"]
    rdk = book.get("OH2RDK-7")
    assert rdk is not None and rdk.has_position and (rdk.lat, rdk.lon) == (pytest.approx(60.165), pytest.approx(24.946667)) and (rdk.symbol_table, rdk.symbol_code) == ("T", "&")
    assert rdk.last_comment == "432.500 MHz" and rdk.packets == 1 and rdk.last_path == ("OH2RCH-2*", "TRACE2-1") and rdk.kind == "station" and rdk.first_heard == T0
    pu = book.get("OH2PU-9")
    assert pu is not None and pu.course_deg == 356 and pu.speed_kmh == 0.0 and len(pu.track) == 1


def test_a_position_updates_the_sender_and_counts() -> None:
    book, heard = StationBook(), None
    heard = Heard(book)
    book.take(packet(position(60.0, 24.0, comment="first", altitude_m=12.0, course_deg=90, speed_kmh=40.0)))
    later = book.take(packet(position(60.5, 24.5, comment="second"), at=T0 + timedelta(minutes=10), path=("WIDE1-1*", "OH2RCH-2")))
    assert later is book.get("OH2AAA") and later is not None
    assert (later.lat, later.lon, later.last_comment, later.packets) == (60.5, 24.5, "second", 2)
    assert (later.altitude_m, later.course_deg, later.speed_kmh) == (None, None, None), "a position without them says the station has none"
    assert later.first_heard == T0 and later.last_heard == T0 + timedelta(minutes=10) and later.last_position_at == T0 + timedelta(minutes=10) and later.last_path == ("WIDE1-1*", "OH2RCH-2")
    assert heard.changed == [("OH2AAA", 1), ("OH2AAA", 2)]


def test_a_message_a_status_and_the_rest_count_the_sender_as_heard_without_a_position() -> None:
    book = StationBook()
    book.take(packet(Message(addressee="OH2BBB", text="hi"), source="OH2MSG", at=T0))
    book.take(packet(Status("on the road"), source="OH2STA", at=T0 + timedelta(seconds=1)))
    book.take(packet(Other("telemetry", "T#001"), source="OH2OTH", at=T0 + timedelta(seconds=2)))
    book.take(packet(Undecoded("too short", "!60"), source="OH2UND", at=T0 + timedelta(seconds=3)))
    assert [s.call for s in book.stations()] == ["OH2UND", "OH2OTH", "OH2STA", "OH2MSG"], "the latest heard first"
    assert all(not s.has_position and s.packets == 1 and s.last_path == ("OH2RCH-2*",) for s in book.stations())
    assert book.get("OH2STA").last_status == "on the road"  # type: ignore[union-attr]


def test_a_status_keeps_the_position_the_station_had() -> None:
    book = StationBook()
    book.take(packet(position(60.2, 24.9)))
    s = book.take(packet(Status("QRV"), at=T0 + timedelta(minutes=1)))
    assert s is not None and (s.lat, s.lon, s.last_status, s.packets) == (60.2, 24.9, "QRV", 2)


def test_packets_we_sent_are_not_taken() -> None:
    book = StationBook()
    assert book.take(packet(position(), source="OH2GBA", direction="out")) is None
    assert len(book) == 0


def test_the_track_takes_a_position_that_moved_or_one_after_five_minutes() -> None:
    book = StationBook()
    book.take(packet(position(60.0, 24.0), at=T0))
    book.take(packet(position(60.00005, 24.0), at=T0 + timedelta(seconds=30)))              # 5.6 m: not moved
    s = book.get("OH2AAA")
    assert s is not None and len(s.track) == 1
    book.take(packet(position(60.0002, 24.0), at=T0 + timedelta(seconds=60)))               # 22 m: moved
    assert len(s.track) == 2
    book.take(packet(position(60.0002, 24.0), at=T0 + timedelta(seconds=60 + 299)))         # the same place, not yet five minutes
    assert len(s.track) == 2
    book.take(packet(position(60.0002, 24.0), at=T0 + timedelta(seconds=60 + 300)))         # the same place, five minutes
    assert len(s.track) == 3
    assert s.track[-1] == (T0 + timedelta(seconds=360), 60.0002, 24.0)


def test_the_track_keeps_the_latest_fifty() -> None:
    book = StationBook()
    for n in range(TRACK_MAX + 20):
        book.take(packet(position(60.0 + n * 0.001, 24.0), at=T0 + timedelta(minutes=n)))
    s = book.get("OH2AAA")
    assert s is not None and len(s.track) == TRACK_MAX and s.track[0][1] == pytest.approx(60.0 + 20 * 0.001) and s.packets == TRACK_MAX + 20


def test_an_object_is_a_station_of_its_own_and_the_sender_is_heard_too() -> None:
    book, heard = StationBook(), None
    heard = Heard(book)
    about = book.take(packet(ObjectReport("FIRE", True, position(60.3, 25.0, comment="smoke", symbol_code="f")), source="OH2OBJ"))
    assert about is not None and about.call == "FIRE" and about.kind == "object" and about.reported_by == "OH2OBJ" and (about.lat, about.lon) == (60.3, 25.0)
    assert about.last_comment == "smoke" and about.packets == 1 and about.symbol_code == "f"
    sender = book.get("OH2OBJ")
    assert sender is not None and sender.kind == "station" and not sender.has_position and sender.packets == 1
    assert heard.changed == [("OH2OBJ", 1), ("FIRE", 1)]


def test_an_item_is_a_station_of_kind_item_and_a_new_report_moves_it() -> None:
    book = StationBook()
    book.take(packet(ItemReport("BUOY1", True, position(59.9, 24.0)), source="OH2OBJ"))
    again = book.take(packet(ItemReport("BUOY1", True, position(59.95, 24.0)), source="OH2OTH", at=T0 + timedelta(minutes=1)))
    assert again is not None and again.kind == "item" and again.reported_by == "OH2OTH" and again.lat == 59.95 and again.packets == 2 and len(again.track) == 2


def test_a_killed_object_or_item_is_removed_and_told() -> None:
    book, heard = StationBook(), None
    heard = Heard(book)
    book.take(packet(ObjectReport("FIRE", True, position()), source="OH2OBJ"))
    book.take(packet(ItemReport("BUOY1", True, position()), source="OH2OBJ"))
    assert book.take(packet(ObjectReport("FIRE", False, position()), source="OH2OBJ", at=T0 + timedelta(minutes=1))) is None
    assert book.take(packet(ItemReport("BUOY1", False, position()), source="OH2OBJ", at=T0 + timedelta(minutes=1))) is None
    assert book.take(packet(ObjectReport("NEVER", False, position()), source="OH2OBJ")) is None
    assert sorted(s.call for s in book.stations()) == ["OH2OBJ"] and heard.removed == ["FIRE", "BUOY1"]


def test_set_me_puts_our_station_in_the_book_and_gives_distance_and_bearing() -> None:
    book = StationBook(lambda: T0)
    heard = Heard(book)
    me = book.set_me("OH2GBA", 60.17, 24.94)
    assert me.is_me and me is book.me and (me.lat, me.lon) == (60.17, 24.94) and book.get("OH2GBA") is me and heard.changed == [("OH2GBA", 0)]
    book.set_me("OH2GBA", 60.17, 24.94)
    assert len(heard.changed) == 1, "nothing changed, nothing told"
    book.take(packet(position(60.17, 25.94), source="OH2EAS"))                          # one degree of longitude east, 55.4 km at this latitude
    east = book.get("OH2EAS")
    assert east is not None
    distance, bearing = book.distance_km(east), book.bearing_deg(east)
    assert distance == pytest.approx(55.6, abs=0.5) and bearing == pytest.approx(90.0, abs=0.5)
    assert book.distance_km(me) == pytest.approx(0.0, abs=1e-6)
    book.take(packet(Message("X", "y"), source="OH2NOPOS"))
    assert book.distance_km(book.get("OH2NOPOS")) is None and book.bearing_deg(book.get("OH2NOPOS")) is None  # type: ignore[arg-type]


def test_there_is_no_distance_before_we_know_where_we_are() -> None:
    book = StationBook()
    book.take(packet(position()))
    s = book.get("OH2AAA")
    assert s is not None and book.distance_km(s) is None and book.bearing_deg(s) is None and book.me is None


def test_a_new_call_makes_the_old_one_an_ordinary_station_and_a_packet_from_us_keeps_the_flag() -> None:
    book = StationBook(lambda: T0)
    old = book.set_me("OH2OLD", 60.0, 24.0)
    book.set_me("OH2GBA", 60.1, 24.1)
    assert not old.is_me and book.me is not old and book.me is not None and book.me.call == "OH2GBA"
    book.take(packet(position(60.1, 24.1), source="OH2GBA", path=("WIDE1-1*",)))        # our beacon, digipeated and heard
    assert book.me is not None and book.me.is_me and book.me.packets == 0, "heard, but not counted as a packet of a station we hear"


def test_set_me_gives_our_row_the_symbol_and_the_comment_of_the_settings_and_tells_when_they_change() -> None:
    book = StationBook(lambda: T0)
    heard = Heard(book)
    me = book.set_me("OH2GBA", 60.17, 24.94, "/", "-", "NeoAPRS")
    assert (me.symbol_table, me.symbol_code, me.last_comment) == ("/", "-", "NeoAPRS") and len(heard.changed) == 1
    book.set_me("OH2GBA", 60.17, 24.94, "/", "-", "NeoAPRS")
    assert len(heard.changed) == 1, "nothing changed, nothing told"
    book.set_me("OH2GBA", 60.17, 24.94, "\\", ">", "mobile")
    assert len(heard.changed) == 2 and (me.symbol_table, me.symbol_code, me.last_comment) == ("\\", ">", "mobile")


def test_a_packet_from_our_own_call_heard_on_the_air_moves_only_the_time_we_were_last_heard() -> None:
    book = StationBook(lambda: T0)
    heard = Heard(book)
    me = book.set_me("OH2GBA", 60.17, 24.94, "/", "-", "NeoAPRS")
    del heard.changed[:]
    later = T0 + timedelta(minutes=5)
    taken = book.take(packet(position(61.0, 25.0), source="OH2GBA", path=("OH2RCH-2*",), at=later))       # (an echo of the TNC or a digipeater's copy, with another position)
    assert taken is me and me.last_heard == later
    assert (me.lat, me.lon, me.symbol_table, me.symbol_code, me.last_comment, me.packets, me.last_path, me.track) == (60.17, 24.94, "/", "-", "NeoAPRS", 0, (), [])
    assert heard.changed == [("OH2GBA", 0)]
    assert book.take(packet(position(), source="OH2GBA", direction="out")) is None, "what we send is not heard"


def test_forget_removes_a_station_and_tells_but_not_ours() -> None:
    book = StationBook(lambda: T0)
    heard = Heard(book)
    book.set_me("OH2GBA", 60.1, 24.1)
    book.take(packet(position()))
    assert book.forget("OH2AAA") and not book.forget("OH2AAA") and not book.forget("OH2GBA") and book.get("OH2GBA") is not None
    assert heard.removed == ["OH2AAA"]


def test_prune_removes_the_stations_not_heard_since_and_not_ours() -> None:
    book = StationBook(lambda: T0 - timedelta(days=100))
    heard = Heard(book)
    book.set_me("OH2GBA", 60.1, 24.1)
    book.take(packet(position(), source="OH2OLD", at=T0 - timedelta(days=40)))
    book.take(packet(position(), source="OH2NEW", at=T0 - timedelta(days=1)))
    assert book.prune(T0 - timedelta(days=30)) == ["OH2OLD"]
    assert sorted(s.call for s in book.stations()) == ["OH2GBA", "OH2NEW"] and heard.removed == ["OH2OLD"]
    assert book.prune(T0 - timedelta(days=30)) == []


def test_prune_keeps_the_stations_it_is_told_to_keep() -> None:
    book = StationBook(lambda: T0 - timedelta(days=100))
    heard = Heard(book)
    book.set_me("OH2GBA", 60.1, 24.1)
    for call in ("OH2OLD", "OH2KEPT", "OH2ALSO"):
        book.take(packet(position(), source=call, at=T0 - timedelta(days=40)))
    assert book.prune(T0 - timedelta(days=30), {"OH2KEPT", "NOT-HERE"}) == ["OH2OLD", "OH2ALSO"]
    assert sorted(s.call for s in book.stations()) == ["OH2GBA", "OH2KEPT"] and heard.removed == ["OH2OLD", "OH2ALSO"]
    assert book.prune(T0 - timedelta(days=30), frozenset({"OH2KEPT"})) == []
    assert book.prune(T0 - timedelta(days=30)) == ["OH2KEPT"], "without the list it goes like any other"


def test_seed_fills_the_book_without_a_word_and_gives_each_position_a_track() -> None:
    book = StationBook()
    heard = Heard(book)
    book.set_me("OH2GBA", 60.1, 24.1)
    del heard.changed[:]
    book.seed([Station("OH2OLD", first_heard=T0, last_heard=T0, lat=60.0, lon=24.0, last_position_at=T0, packets=7), Station("OH2GBA", first_heard=T0, last_heard=T0),
               Station("OH2NOPOS", first_heard=T0, last_heard=T0)])
    assert heard.changed == [] and len(book) == 3
    old = book.get("OH2OLD")
    assert old is not None and old.track == [(T0, 60.0, 24.0)] and not old.is_me
    me = book.get("OH2GBA")
    assert me is not None and me.is_me, "seeding does not undo who we are"
    book.take(packet(position(60.00001, 24.0), source="OH2OLD", at=T0 + timedelta(seconds=10)))
    assert len(old.track) == 1 and old.packets == 8


# ---- how the packets reached us (neoaprs/route.py)

def test_every_packet_of_a_station_counts_the_route_it_came_by() -> None:
    book = StationBook()
    for path in [(), ("OH2RCH-2*",), ("OH2RCH-2*", "WIDE2-1"), ("OH2RCH-3*",), ("WIDE1*", "OH2RCH-2*")]:
        book.take(packet(Status("x"), path=path))
    station = book.get("OH2AAA")
    assert station is not None and station.deliveries.direct == 1
    assert station.deliveries.heard_via() == [("OH2RCH-2", 3), ("OH2RCH-3", 1)]
    best = station.best_route
    assert best is not None and best.hops == ("OH2RCH-2",) and station.last_path == ("WIDE1*", "OH2RCH-2*")


def test_a_packet_of_ours_and_a_packet_from_our_own_call_count_no_route() -> None:
    book = StationBook()
    book.set_me("OH2GBA", 60.0, 24.0)
    book.take(packet(Status("x"), source="OH2GBA", path=("OH2RCH-2*",)))
    book.take(packet(Status("x"), source="OH2AAA", direction="out"))
    me = book.me
    assert me is not None and me.deliveries.best() is None and book.get("OH2AAA") is None


def test_an_object_counts_its_route_for_the_station_that_reported_it_not_for_the_object() -> None:
    book = StationBook()
    book.take(packet(ObjectReport("FIRE", True, position()), source="OH2REP", path=("OH2RCH-2*",)))
    reporter, thing = book.get("OH2REP"), book.get("FIRE")
    assert reporter is not None and thing is not None and reporter.deliveries.heard_via() == [("OH2RCH-2", 1)] and thing.best_route is None


def test_the_routes_of_the_packets_the_database_kept_are_counted_for_the_stations_in_the_book() -> None:
    book = StationBook()
    book.seed([Station("OH2AAA", first_heard=T0, last_heard=T0), Station("OH2BBB", first_heard=T0, last_heard=T0)])
    later = T0 + timedelta(minutes=5)
    book.seed_deliveries([("OH2AAA", ("OH2RCH-3*",), "", 2, T0, None), ("OH2GONE", ("OH2RCH-2*",), "", 5, T0, None), ("OH2AAA", ("OH2RCH-2*",), "", 4, T0, None), ("OH2BBB", (), "", 1, later, None),
                           ("OH2BBB", ("OH2RCH-2*",), "OH7JHF-1", 3, later, None)])
    a, b = book.get("OH2AAA"), book.get("OH2BBB")
    assert a is not None and b is not None and book.get("OH2GONE") is None
    best = a.best_route
    assert best is not None and best.hops == ("OH2RCH-2",) and a.deliveries.heard_via() == [("OH2RCH-2", 4), ("OH2RCH-3", 2)]
    assert a.last_path == ("OH2RCH-2*",)
    assert (b.deliveries.direct, b.deliveries.gated, b.last_via) == (1, 3, "OH7JHF-1")
    assert (a.last_direct_at, b.last_direct_at) == (None, later), "only a direct group gives the time of the last direct packet"


def test_a_packet_heard_direct_gives_the_time_of_the_last_direct_packet_and_no_other_packet_does() -> None:
    book = StationBook()
    book.take(packet(Status("far"), source="OH2AAA", path=("OH2RCH-2*",)))
    station = book.get("OH2AAA")
    assert station is not None and station.last_direct_at is None
    book.take(packet(Status("near"), source="OH2AAA", path=(), at=T0 + timedelta(minutes=2)))
    assert station.last_direct_at == T0 + timedelta(minutes=2)
    book.take(packet(Status("far"), source="OH2AAA", path=("OH2RCH-2*",), at=T0 + timedelta(minutes=9)))
    assert station.last_direct_at == T0 + timedelta(minutes=2) and station.deliveries.direct == 1, "a packet by a digipeater is not direct"
    book.take(packet(Status("not repeated yet"), source="OH2AAA", path=("WIDE1-1",), at=T0 + timedelta(minutes=10)))
    assert station.last_direct_at == T0 + timedelta(minutes=10), "a path with no star is a packet that came straight from the sender"


def test_an_object_has_no_direct_time_and_neither_has_a_packet_from_an_igate() -> None:
    book = StationBook()
    book.take(packet(ObjectReport("FIRE", True, position()), source="OH2REP", path=()))
    thing, reporter = book.get("FIRE"), book.get("OH2REP")
    assert thing is not None and reporter is not None and thing.last_direct_at is None and reporter.last_direct_at == T0
    book.take(Packet(heard_at=T0, direction="in", raw=b"", source="OH7JHF-1", destination="APRS", path=(), info=b"", decoded=Status("x"), third_party=ThirdParty("OH2DPN", "APRS", ("TCPIP",))))
    gated = book.get("OH2DPN")
    assert gated is not None and gated.last_direct_at is None and gated.deliveries.gated == 1


# ---- third-party packets: the station is the sender inside

def gated(decoded: object, inner: str = "OH2DPN", gate: str = "OH7JHF-1", at: datetime = T0, path: tuple[str, ...] = ("OH2RCH-3*",)) -> Packet:
    return Packet(heard_at=at, direction="in", raw=b"", source=gate, destination="APRS", path=path, info=b"", decoded=decoded, third_party=ThirdParty(inner, "APJYC1", ("TCPIP", gate + "*")))  # type: ignore[arg-type]


def test_a_third_party_position_moves_the_station_inside_and_not_the_igate() -> None:
    book = StationBook()
    taken = book.take(gated(position(61.0, 25.0, comment="from the net")))
    assert taken is book.get("OH2DPN") and taken is not None
    assert (taken.lat, taken.lon, taken.last_comment, taken.packets, taken.last_via, taken.last_path) == (61.0, 25.0, "from the net", 1, "OH7JHF-1", ("OH2RCH-3*",))
    assert book.get("OH7JHF-1") is None, "the iGate heard nothing at that position"
    assert taken.deliveries.gated == 1 and taken.deliveries.best() is None, "it is no route to send by"


def test_a_third_party_object_is_reported_by_the_station_inside() -> None:
    book = StationBook()
    book.take(gated(ObjectReport("FIRE", True, position())))
    thing = book.get("FIRE")
    assert thing is not None and thing.reported_by == "OH2DPN" and thing.last_via == "OH7JHF-1" and book.get("OH7JHF-1") is None


def test_our_own_packet_gated_back_to_us_moves_only_our_last_heard() -> None:
    book = StationBook()
    me = book.set_me("OH2GBA", 60.0, 24.0)
    before = me.last_heard
    book.take(gated(position(61.0, 25.0), inner="OH2GBA", at=T0 + timedelta(hours=1)))
    assert (me.lat, me.lon, me.packets, me.last_heard) == (60.0, 24.0, 0, T0 + timedelta(hours=1)) and me.last_heard != before and book.get("OH7JHF-1") is None


# ---- weather

WX = Weather(wind_dir=107, wind_kmh=1.6, temp_c=10.0, humidity=85, pressure_hpa=1028.4)


def test_a_weather_position_keeps_the_latest_observation_and_when_it_was_heard() -> None:
    book = StationBook()
    book.take(packet(position(symbol_code="_", weather=WX), "OH2MUI"))
    later = Weather(temp_c=11.0)
    book.take(packet(position(symbol_code="_", weather=later), "OH2MUI", at=T0 + timedelta(minutes=10)))
    station = book.get("OH2MUI")
    assert station is not None and (station.weather, station.weather_at) == (later, T0 + timedelta(minutes=10))
    book.take(packet(position(symbol_code="_"), "OH2MUI", at=T0 + timedelta(minutes=20)))
    assert (station.weather, station.weather_at) == (later, T0 + timedelta(minutes=10)), "a position with no weather leaves the last observation where it was"


def test_a_positionless_weather_report_gives_the_sender_its_weather_and_no_position() -> None:
    book = StationBook()
    heard = Heard(book)
    book.take(packet(Other("weather", "_10090556t050", WX), "OH2MUI"))
    station = book.get("OH2MUI")
    assert station is not None and station.weather == WX and station.weather_at == T0 and not station.has_position
    assert heard.changed == [("OH2MUI", 1)]
    book.take(packet(Other("weather", "!!0000"), "OH2OLD"))
    old = book.get("OH2OLD")
    assert old is not None and old.weather is None


def test_the_weather_of_an_object_is_the_objects_and_a_station_without_it_has_none() -> None:
    book = StationBook()
    book.take(packet(ObjectReport("WXPOST", True, position(symbol_code="_", weather=WX)), "OH2AAA"))
    post, reporter = book.get("WXPOST"), book.get("OH2AAA")
    assert post is not None and post.weather == WX and reporter is not None and reporter.weather is None


def test_the_weather_log_seeds_the_stations_in_the_book_and_leaves_the_others_out() -> None:
    book = StationBook()
    book.seed([Station("OH2MUI", first_heard=T0, last_heard=T0)])
    book.seed_weather({"OH2MUI": (T0, WX), "OH2GONE": (T0, WX)})
    station = book.get("OH2MUI")
    assert station is not None and (station.weather, station.weather_at) == (WX, T0) and book.get("OH2GONE") is None


# ---- the tracks the database kept

def moved(n: int, minutes: int = 1) -> tuple[str, datetime, float, float]:
    return ("OH2GAX-9", T0 + timedelta(minutes=minutes * n), 60.0 + n * 0.001, 24.0)


def test_the_tracks_are_made_from_the_positions_kept_by_the_rule_of_a_live_one_the_latest_50_oldest_first() -> None:
    book = StationBook()
    book.seed([Station("OH2GAX-9", first_heard=T0, last_heard=T0, lat=60.0, lon=24.0, last_position_at=T0)])
    book.seed_tracks([moved(n) for n in range(60)])
    station = book.get("OH2GAX-9")
    assert station is not None and len(station.track) == TRACK_MAX
    times = [t for t, _, _ in station.track]
    assert times == sorted(times) and times[-1] == T0 + timedelta(minutes=59) and times[0] == T0 + timedelta(minutes=10)


def test_a_position_that_did_not_move_joins_the_track_only_after_five_minutes() -> None:
    book = StationBook()
    book.seed([Station("OH2AAA", first_heard=T0, last_heard=T0)])
    book.seed_tracks([("OH2AAA", T0 + timedelta(minutes=m), 60.0, 24.0) for m in (0, 1, 2, 3, 5, 6, 10)])
    assert [t for t, _, _ in book.get("OH2AAA").track] == [T0, T0 + timedelta(minutes=5), T0 + timedelta(minutes=10)]    # type: ignore[union-attr]


def test_the_tracks_replace_the_one_point_a_station_was_seeded_with_and_leave_the_others_and_us_alone() -> None:
    book = StationBook()
    book.set_me("OH2GBA", 60.17, 24.94)
    book.seed([Station("OH2AAA", first_heard=T0, last_heard=T0, lat=1.0, lon=1.0, last_position_at=T0), Station("OH2BBB", first_heard=T0, last_heard=T0, lat=2.0, lon=2.0, last_position_at=T0)])
    book.seed_tracks([("OH2AAA", T0, 60.0, 24.0), ("OH2AAA", T0 + timedelta(minutes=1), 60.01, 24.0), ("OH2GBA", T0, 61.0, 25.0), ("OH2NONE", T0, 1.0, 1.0)])
    aaa, bbb, me = book.get("OH2AAA"), book.get("OH2BBB"), book.me
    assert aaa is not None and [(lat, lon) for _, lat, lon in aaa.track] == [(60.0, 24.0), (60.01, 24.0)]
    assert bbb is not None and bbb.track == [(T0, 2.0, 2.0)], "a station with no position kept has the one point it was seeded with"
    assert me is not None and me.track == [] and book.get("OH2NONE") is None


# ---- telemetry, locators and data extensions
DEFINITIONS = ("PARM.Battery,Btemp,ATemp,Pres,Alt,Camra", "UNIT.v/100,deg.F,deg.F,Mbar,Kft,Click", "EQNS.0,5.2,0,0,.53,-32,3,4.39,49,-32,3,18,1,2,3", "BITS.10110000,N0QBF's Big Balloon")
REPORT = Telemetry(5, [199, 0, 255, 73, 123], "01101001")


def test_a_telemetry_report_is_the_latest_of_its_sender() -> None:
    book = StationBook()
    book.take(packet(REPORT, source="N0QBF-11"))
    later = Telemetry(6, [1, 2, 3, 4, 5], "00000000")
    station = book.take(packet(later, source="N0QBF-11", at=T0 + timedelta(minutes=10)))
    assert station is not None and (station.telemetry, station.telemetry_at, station.packets) == (later, T0 + timedelta(minutes=10), 2)
    assert book.get("N0QBF-11") is station and book.get("OH2AAA") is None


def test_the_base91_telemetry_in_the_comment_of_a_position_is_the_latest_report_of_its_sender() -> None:
    book = StationBook()
    book.take(packet(REPORT, source="N0QBF-11"))
    position = aprsparse.parse(b"!4903.50N/07201.75W-Balloon|ss11|!W12!", "N0QBF-11", "APRS", T0)
    assert isinstance(position, Position) and position.comment == "Balloon" and position.telemetry == Telemetry(7544, [1472], "")
    station = book.take(packet(position, source="N0QBF-11", at=T0 + timedelta(minutes=1)))
    assert station is not None and (station.telemetry, station.telemetry_at) == (Telemetry(7544, [1472], ""), T0 + timedelta(minutes=1))
    book.take(packet(aprsparse.parse(b"!4903.50N/07201.75W-no telemetry", "N0QBF-11", "APRS", T0), source="N0QBF-11", at=T0 + timedelta(minutes=2)))
    assert station.telemetry == Telemetry(7544, [1472], ""), "a position without it leaves the latest report"


def test_the_base91_telemetry_of_a_mic_e_packet_comes_before_its_dao_and_type_code() -> None:
    position = aprsparse.parse(b'`(_fn"Oj/`Hi|ss1122|!w5L!_%', "OH2AAA", "S32UVT", T0)
    assert isinstance(position, Position) and position.comment == "Mic-E: Returning - Hi" and position.telemetry == Telemetry(7544, [1472, 1564], "")


def test_the_definitions_are_the_addressees_and_a_message_to_another_station_is_not_one() -> None:
    book = StationBook()
    for text in DEFINITIONS:
        book.take(packet(Message("N0QBF-11", text), source="N0QBF-11"))
    book.take(packet(Message("OH2GBA", "PARM.nothing")))
    definition = book.telemetry_definition("N0QBF-11")
    assert definition is not None and definition.names[0] == "Battery" and definition.sense == "10110000" and definition.project == "N0QBF's Big Balloon"
    assert book.telemetry_definition("OH2GBA") is not None and book.telemetry_definition("OH2AAA") is None
    book.take(packet(Message("N0QBF-11", "just text", "12"), source="N0QBF-11"))
    book.take(packet(Message("N0QBF-11", "", ack_id="3"), source="OH2AAA"))
    assert book.telemetry_definition("N0QBF-11") == definition


def test_a_definition_that_arrives_after_the_report_signals_the_station() -> None:
    book, heard = StationBook(), []
    book.take(packet(REPORT, source="N0QBF-11"))
    book.changed.connect(lambda s: heard.append(s.call))
    book.take(packet(Message("N0QBF-11", DEFINITIONS[0]), source="OH2AAA"))              # (another station sent it)
    assert heard == ["N0QBF-11", "OH2AAA"]


def test_the_table_of_definitions_keeps_the_latest_stations() -> None:
    book = StationBook()
    for i in range(DEFINITIONS_MAX + 5):
        book.take(packet(Message(f"S{i}", "PARM.x"), source="OH2AAA"))
    assert book.telemetry_definition("S0") is None and book.telemetry_definition(f"S{DEFINITIONS_MAX + 4}") is not None


def test_our_own_telemetry_is_not_taken_from_the_air() -> None:
    book = StationBook()
    book.set_me("OH2GBA", 60.0, 24.0)
    book.take(packet(REPORT, source="OH2GBA"))
    me = book.get("OH2GBA")
    assert me is not None and me.telemetry is None


def test_status_and_position_details_follow_the_latest_packet() -> None:
    book = StationBook()
    locator = Locator("IO91sx", 51.97917, -0.45833, "/", "-")
    ext = Extensions(range_km=80.5)
    book.take(packet(Status("my house", locator=locator)))
    book.take(packet(Status("moved"), at=T0 + timedelta(minutes=1)))
    station = book.get("OH2AAA")
    assert station is not None and station.locator == locator and station.last_status == "moved"           # (a status without a locator keeps the last one)
    book.take(packet(position(extensions=ext), at=T0 + timedelta(minutes=2)))
    assert station.extensions == ext
    book.take(packet(position(), at=T0 + timedelta(minutes=3)))
    assert station.extensions is None                                                                     # (a position without them has none)
    book.take(packet(position(locator=Locator("KP20", 60.5, 25.0, "/", "G")), at=T0 + timedelta(minutes=4)))
    assert station.locator is not None and station.locator.grid == "KP20"


def test_the_details_are_read_again_from_the_latest_packets_at_the_start() -> None:
    book = StationBook()
    book.seed([Station("N0QBF-11", first_heard=T0, last_heard=T0), Station("OH2AAA", first_heard=T0, last_heard=T0)])
    newest_first = [packet(Telemetry(6, [1, 2, 3, 4, 5], "00000000"), source="N0QBF-11", at=T0 + timedelta(minutes=2)), packet(Message("N0QBF-11", "PARM.Second"), source="N0QBF-11", at=T0 + timedelta(minutes=2)),
                    packet(Status("x", locator=Locator("IO91", 51.5, -1.0, "/", "-")), at=T0 + timedelta(minutes=1)), packet(position(extensions=Extensions(range_km=10.0))),
                    packet(REPORT, source="N0QBF-11"), packet(Message("N0QBF-11", "PARM.First,Second"), source="N0QBF-11"), packet(REPORT, source="NOBODY"),
                    packet(Telemetry(9, [9, 9, 9, 9, 9], "11111111"), source="N0QBF-11", direction="out")]
    heard = Heard(book)
    book.seed_details(newest_first)
    telemetry = book.get("N0QBF-11")
    assert telemetry is not None and telemetry.telemetry is not None and telemetry.telemetry.sequence == 6 and telemetry.telemetry_at == T0 + timedelta(minutes=2)
    definition = book.telemetry_definition("N0QBF-11")
    assert definition is not None and definition.names == ("Second",)                                    # (the later message wins)
    station = book.get("OH2AAA")
    assert station is not None and station.extensions == Extensions(range_km=10.0) and station.locator is not None and station.locator.grid == "IO91"
    assert book.get("NOBODY") is None and heard.changed == []
