"""Our own objects and items in the station book (neoaprs/stationbook.py): they are stations of their own marked `own`, reported by us, never pruned or forgotten or made a track of, replaced by what another
station reports under the name, untouched by another station's kill, taken out when killed, and not kept in the station cache."""
from dataclasses import replace
from datetime import timedelta

from neoaprs.ownobject import OwnObject, make_object
from neoaprs.packet import ItemReport, ObjectReport, Packet, Position
from neoaprs.stationbook import StationBook
from tests.support.clock import FixedClock

CLOCK = FixedClock()
T0 = CLOCK()


def ours(name: str = "LEADER", kind: str = "object", **values: object) -> OwnObject:
    fields: dict[str, object] = {"lat": 60.3, "lon": 25.0, "symbol_table": "/", "symbol_code": ">", **values}
    return make_object(T0, name, kind, **fields)              # type: ignore[arg-type]


def heard(name: str, sender: str = "OH2XYZ", alive: bool = True, at: object = T0) -> Packet:
    return Packet(at, "in", b"", sender, "APRS", ("OH2RCH-2*",), b"", ObjectReport(name, alive, Position(60.5, 25.5, "/", "-", "theirs")))    # type: ignore[arg-type]


def book() -> tuple[StationBook, list[str], list[str]]:
    b = StationBook(CLOCK)
    changed: list[str] = []
    removed: list[str] = []
    b.changed.connect(lambda s: changed.append(s.call))
    b.removed.connect(removed.append)
    b.set_me("OH2GBA", 60.17, 24.94)
    changed.clear()
    return b, changed, removed


def test_our_object_is_a_station_of_its_own_marked_ours_with_what_we_send() -> None:
    b, changed, _ = book()
    station = b.own_object(replace(ours(comment="Rescue 1", course_deg=88, speed_kmh=40.0, path="WIDE2-1"), sent=2, last_sent_at=T0 + timedelta(seconds=60)))
    assert station is not None and b.get("LEADER") is station and changed == ["LEADER"]
    assert (station.kind, station.own, station.is_me, station.reported_by) == ("object", True, False, "OH2GBA")
    assert (station.lat, station.lon, station.symbol_table, station.symbol_code, station.last_comment, station.course_deg, station.speed_kmh) == (60.3, 25.0, "/", ">", "Rescue 1", 88, 40.0)
    assert (station.packets, station.last_heard, station.last_position_at, station.last_path, station.track) == (2, T0 + timedelta(seconds=60), T0, ("WIDE2-1",), [])
    assert station.has_position and b.distance_km(station) is not None


def test_an_item_is_one_too() -> None:
    b, _, _ = book()
    station = b.own_object(ours("AID", "item", symbol_table="\\", symbol_code="+"))
    assert station is not None and (station.kind, station.own, station.symbol_table, station.symbol_code) == ("item", True, "\\", "+")


def test_a_change_is_the_same_station_changed_and_told() -> None:
    b, changed, _ = book()
    first = b.own_object(ours())
    second = b.own_object(ours(lat=61.0, comment="moved"))
    assert second is first and first is not None and (first.lat, first.last_comment) == (61.0, "moved") and changed == ["LEADER", "LEADER"]


def test_a_killed_object_is_out_of_the_book_and_told() -> None:
    b, _, removed = book()
    obj = ours()
    b.own_object(obj)
    assert b.own_object(obj.killed(T0)) is None and b.get("LEADER") is None and removed == ["LEADER"]
    b.forget_own(obj)
    assert removed == ["LEADER"], "nothing to forget, nothing told"


def test_forgetting_ours_leaves_a_station_that_took_the_name() -> None:
    b, _, removed = book()
    obj = ours()
    b.own_object(obj)
    taken = b.take(heard("LEADER"))
    assert taken is not None and not taken.own and taken.reported_by == "OH2XYZ" and taken.last_comment == "theirs"
    b.forget_own(obj)
    assert b.get("LEADER") is taken and removed == []


def test_what_is_heard_under_the_name_of_ours_is_replaced_by_ours_and_the_other_way_round() -> None:
    b, _, _ = book()
    b.take(heard("LEADER"))
    first = b.get("LEADER")
    assert first is not None and not first.own
    mine = b.own_object(ours())
    assert mine is not None and mine is not first and mine.own and mine.reported_by == "OH2GBA"
    again = b.take(heard("LEADER", at=T0 + timedelta(minutes=1)))
    assert again is not None and not again.own and again.reported_by == "OH2XYZ" and b.get("LEADER") is again


def test_another_stations_kill_of_the_name_does_not_take_ours_out_and_a_kill_of_a_heard_object_still_does() -> None:
    b, _, removed = book()
    b.own_object(ours())
    assert b.take(heard("LEADER", alive=False)) is None
    assert b.get("LEADER") is not None and b.get("LEADER").own is True and removed == []              # type: ignore[union-attr]
    b.take(heard("STORM"))
    assert b.take(heard("STORM", alive=False)) is None and b.get("STORM") is None and removed == ["STORM"]


def test_a_copy_of_ours_that_comes_back_makes_no_object_and_moves_only_the_time_we_were_heard() -> None:
    b, changed, _ = book()
    b.own_object(ours())
    me = b.me
    assert me is not None
    count = len(b)
    changed.clear()
    later = T0 + timedelta(minutes=5)
    back = Packet(later, "in", b"", "OH2GBA", "APZNEO", ("OH2RCH-2*",), b"", ObjectReport("LEADER", True, Position(60.3, 25.0, "/", ">")))
    assert b.take(back) is me and len(b) == count and me.last_heard == later and changed == ["OH2GBA"]
    item = Packet(later, "in", b"", "OH2GBA", "APZNEO", (), b"", ItemReport("AID", True, Position(60.3, 25.0, "/", "+")))
    b.take(item)
    assert b.get("AID") is None and len(b) == count


def test_ours_is_never_pruned_forgotten_or_given_a_track() -> None:
    b, _, _ = book()
    b.own_object(ours())
    b.take(heard("OTHER", at=T0 - timedelta(days=40)))
    assert sorted(b.prune(T0 + timedelta(days=1))) == ["OH2XYZ", "OTHER"] and b.get("LEADER") is not None
    assert b.forget("LEADER") is False and b.get("LEADER") is not None
    b.seed_tracks([("LEADER", T0, 61.0, 26.0), ("LEADER", T0 + timedelta(minutes=10), 61.1, 26.1)])
    assert b.get("LEADER").track == []                                                                # type: ignore[union-attr]


def test_it_is_reported_by_our_call_even_after_the_call_changes() -> None:
    b, _, _ = book()
    b.own_object(ours())
    b.set_me("OH2GBA-9", 60.17, 24.94)
    assert b.get("LEADER").reported_by == "OH2GBA-9"                                                  # type: ignore[union-attr]
