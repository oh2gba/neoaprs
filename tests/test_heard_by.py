"""What each radio heard of a station (`Station.heard_by`, rule 3.3): the stored field, counted by the id of the radio a packet came on, any number of radios; the old names of radios 1 and 2 (`heard_fm`,
`heard_hf`, `last_fm_at`, `last_hf_at`) and the one path of the latest packet (`last_path`) as its views, which are read, set and taken by the constructor as before, until W3; and the station book that
counts and seeds by radio (neoaprs/station.py, stationnotes.py, stationbook.py)."""
import json
from dataclasses import fields, replace
from datetime import datetime, timedelta
from pathlib import Path

from neoaprs import ax25
from neoaprs.clock import utc
from neoaprs.messagerule import message_radio
from neoaprs.ownobject import OwnObject
from neoaprs.packetcodec import parse_stamp
from neoaprs.packetlog import PacketLog
from neoaprs.packetsql import heard_routes, radio_routes
from neoaprs.packet import IS, ObjectReport, Packet, Position, Status
from neoaprs.radiospec import FM_ID, HF_ID, NOT_HEARD, RadioHeard, RadioSpec
from neoaprs.station import OLD_NAMES, Station
from neoaprs.stationbook import StationBook, carries_path, route_groups
from neoaprs.store import DB_NAME
from neoaprs.web.stationwire import StationRow
from neoaprs.web.views import station_row
from tests.support.clock import FixedClock
from tests.support.migrated32 import shaped
from tests.support.storedb import store_at

T0 = utc(2026, 11, 14, 12, 0, 0)
LORA_ID = 3                                   # a third radio: it has no old word and no old name
DIGI = ("OH2RCH-2*",)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def packet(radio_id: int | None, minutes: float = 0, path: tuple[str, ...] = (), source: str = "OH2AAA", decoded: object = None, via: str = "rf") -> Packet:
    return Packet(heard_at=at(minutes), direction="in", raw=b"", source=source, destination="APRS", path=path, info=b"", decoded=decoded or Status("x"), via=via, radio_id=radio_id)  # type: ignore[arg-type]


def station(**values: object) -> Station:
    return Station("OH2AAA", first_heard=T0, last_heard=T0, **values)  # type: ignore[arg-type]


def heard(book: StationBook, call: str = "OH2AAA") -> Station:
    found = book.get(call)
    assert found is not None
    return found


# ---- the field, counted by the radio's id

def test_a_packet_is_counted_for_the_radio_it_came_on_with_its_time_and_its_path() -> None:
    book = StationBook()
    for radio_id, minutes, path in ((FM_ID, 0, DIGI), (HF_ID, 1, ()), (LORA_ID, 2, ("OH2LGW*",)), (FM_ID, 3, ("OH2RDG*",)), (LORA_ID, 4, ())):
        book.take(packet(radio_id, minutes, path))
    s = heard(book)
    assert s.heard_by == {FM_ID: RadioHeard(2, at(3), ("OH2RDG*",)), HF_ID: RadioHeard(1, at(1), ()), LORA_ID: RadioHeard(2, at(4), ())}
    assert s.heard_on(LORA_ID) == RadioHeard(2, at(4), ()) and s.heard_on(7) == NOT_HEARD, "a radio that never heard it has no entry"
    assert (s.packets, s.heard_rf) == (5, 5), "the counts by channel are what they were"


def test_a_packet_made_without_a_radio_counts_as_radio_1s_and_one_from_the_internet_for_no_radio() -> None:
    book = StationBook()
    book.take(packet(None, 0, DIGI))
    book.take(packet(None, 1, ("TCPIP*", "qAC", "T2FINLAND"), via=IS))
    s = heard(book)
    assert s.heard_by == {FM_ID: RadioHeard(1, at(0), DIGI)} and (s.packets, s.heard_is) == (2, 1)


def test_the_report_of_an_object_is_counted_for_the_object_on_the_radio_it_came_on() -> None:
    book = StationBook()
    book.take(packet(LORA_ID, 0, DIGI, source="OH2CLB", decoded=ObjectReport("LEADER", True, Position(60.0, 24.0, "/", ">"))))
    assert heard(book, "LEADER").heard_by == {LORA_ID: RadioHeard(1, at(0), DIGI)} == heard(book, "OH2CLB").heard_by


def test_every_radio_counts_its_own_routes_and_the_station_as_a_whole_those_of_the_radios_that_may_carry_a_path() -> None:
    """Rule 3.3: the route is kept per radio, HF's too. The station's routes as a whole (`deliveries`, what the page and the automatic path read) are those of the radios that may carry a path: by the radios'
    types where the book is told them, else every radio but radio 2 (the HF radio of before)."""
    book = StationBook()
    for radio_id in (FM_ID, HF_ID, LORA_ID):
        book.take(packet(radio_id, radio_id, ()))
    s = heard(book)
    assert s.deliveries.direct == 2, "the direct packets of radios 1 and 3 are the station's, the one over HF is not"
    assert {radio: d.direct for radio, d in s.routes.items()} == {FM_ID: 1, HF_ID: 1, LORA_ID: 1}, "each radio counts its own, HF's too"
    assert s.routes_on(HF_ID) is s.routes[HF_ID] and s.routes_on(7) is None
    specs = (RadioSpec(FM_ID, "fm", "kiss", "", True, 1), RadioSpec(HF_ID, "hf", "mercury", "", True, 2), RadioSpec(LORA_ID, "hf", "dummy-hf", "", True, 3), RadioSpec(4, "fm", "no-such-type", "", True, 4))
    typed = StationBook(carries_path=lambda radio: carries_path(specs, radio))
    for radio_id in (FM_ID, HF_ID, LORA_ID, 4, 9):
        typed.take(packet(radio_id, radio_id, ()))
    t = heard(typed)
    assert t.deliveries.direct == 2 and set(t.routes) == {FM_ID, HF_ID, LORA_ID, 4, 9}, "radio 1 and a radio the settings do not have; not the two of the kind hf, nor one of a type not known"


# ---- the old names: views of radios 1 and 2

def test_the_old_names_read_what_radios_1_and_2_heard_and_nothing_of_another_radio() -> None:
    book = StationBook()
    for radio_id, minutes in ((FM_ID, 0), (HF_ID, 1), (HF_ID, 2), (LORA_ID, 3)):
        book.take(packet(radio_id, minutes))
    s = heard(book)
    assert (s.heard_fm, s.last_fm_at, s.heard_hf, s.last_hf_at) == (1, at(0), 2, at(2))
    never = station()
    assert (never.heard_fm, never.last_fm_at, never.heard_hf, never.last_hf_at, never.last_path) == (0, None, 0, None, ()) and never.heard_by == {}


def test_the_old_names_are_no_fields_and_the_field_is_heard_by() -> None:
    names = {f.name for f in fields(Station)}
    assert "heard_by" in names and not names & set(OLD_NAMES)
    assert all(isinstance(getattr(Station, name), property) for name in OLD_NAMES)


def test_the_path_of_the_latest_packet_is_the_path_of_the_radio_that_heard_last() -> None:
    book = StationBook()
    book.take(packet(FM_ID, 0, DIGI))
    s = heard(book)
    assert (s.last_radio, s.last_path) == (FM_ID, DIGI)
    book.take(packet(HF_ID, 1, ()))
    assert (s.last_radio, s.last_path) == (HF_ID, ()), "the latest packet came over HF, by no digipeater"
    assert s.heard_on(FM_ID).last_path == DIGI, "what radio 1 heard it by is still radio 1's"
    book.take(packet(LORA_ID, 2, ("OH2LGW*",)))
    assert (s.last_radio, s.last_path) == (LORA_ID, ("OH2LGW*",))
    book.take(packet(FM_ID, 3, ("OH2RDG*",)))
    assert (s.last_radio, s.last_path) == (FM_ID, ("OH2RDG*",))


def test_radio_1_heard_last_on_a_tie_and_the_lowest_id_among_any_others() -> None:
    both = station(heard_by={HF_ID: RadioHeard(1, T0, ()), FM_ID: RadioHeard(1, T0, DIGI)})
    assert (both.last_radio, both.last_path) == (FM_ID, DIGI), "the migration's rule: FM on a tie"
    others = station(heard_by={5: RadioHeard(1, at(1), ("A*",)), LORA_ID: RadioHeard(1, at(1), ("B*",)), FM_ID: RadioHeard(4, T0, DIGI)})
    assert (others.last_radio, others.last_path) == (LORA_ID, ("B*",))
    untimed = station(heard_by={HF_ID: RadioHeard(1, None), LORA_ID: RadioHeard(1, T0, ("B*",))})
    assert untimed.last_radio == LORA_ID, "an entry without a time is before any time"
    assert station().last_radio is None


def test_the_constructor_still_takes_the_old_names_as_the_station_cache_gives_them() -> None:
    """neoaprs/packetlog.py builds a station from its row with the five old names: the same station as one built with the field."""
    fm_last = station(heard_fm=3, last_fm_at=at(2), heard_hf=1, last_hf_at=at(1), last_path=DIGI)
    assert fm_last.heard_by == {FM_ID: RadioHeard(3, at(2), DIGI), HF_ID: RadioHeard(1, at(1))}
    assert fm_last == station(heard_by={FM_ID: RadioHeard(3, at(2), DIGI), HF_ID: RadioHeard(1, at(1))})
    hf_last = station(heard_fm=3, last_fm_at=at(1), heard_hf=1, last_hf_at=at(2), last_path=())
    assert hf_last.heard_by == {FM_ID: RadioHeard(3, at(1)), HF_ID: RadioHeard(1, at(2))}
    tie = station(heard_fm=1, last_fm_at=T0, heard_hf=1, last_hf_at=T0, last_path=DIGI)
    assert tie.heard_by[FM_ID].last_path == DIGI and tie.heard_by[HF_ID].last_path == (), "the path goes with radio 1 on a tie, as the migration puts it"
    for made in (fm_last, hf_last, tie):
        assert (made.heard_fm, made.heard_hf) == (made.heard_by[FM_ID].count, made.heard_by[HF_ID].count)
    assert station(heard_fm=0, heard_hf=0, last_fm_at=None, last_hf_at=None, last_path=()) == station() and station(heard_fm=0).heard_by == {}, "a row that says nothing makes no entry"
    assert station(heard_fm=0, last_fm_at=T0, heard_hf=0, last_hf_at=T0).heard_by == {}, "a radio counted 0 heard nothing, whatever time is with it"
    assert station(heard_by={FM_ID: RadioHeard(0, T0, DIGI), HF_ID: RadioHeard(1, T0)}).heard_by == {HF_ID: RadioHeard(1, T0)}


def test_every_old_name_given_to_the_constructor_is_read_back_as_it_was_given() -> None:
    cases: list[dict[str, object]] = [
        {"heard_fm": 2, "last_fm_at": at(5), "last_path": DIGI},
        {"heard_hf": 4, "last_hf_at": at(5), "last_path": ()},
        {"heard_fm": 2, "last_fm_at": at(1), "heard_hf": 4, "last_hf_at": at(5), "last_path": ("OH2RDG*", "WIDE2-1")},
        {"heard_fm": 2, "heard_hf": 1, "last_path": DIGI},                      # (counts without times: a test's station)
        {"last_path": DIGI},                                                    # (a path and no radio)
        {"heard_fm": 7},
    ]
    for case in cases:
        made = station(**case)
        assert {name: getattr(made, name) for name in case} == case, case


def test_a_path_given_with_no_radio_that_heard_is_kept_beside_the_radios() -> None:
    lone = station(last_path=DIGI)
    assert lone.heard_by == {} and lone.own_path == DIGI and lone.last_path == DIGI
    lone.note_on(HF_ID, at(1), ())
    assert lone.last_path == (), "once a radio heard the station, the path is that radio's"


def test_the_old_names_are_still_set_and_each_changes_its_radio_alone() -> None:
    s = station(heard_by={LORA_ID: RadioHeard(2, T0, ("B*",))})
    s.heard_fm += 1
    s.last_fm_at = at(1)
    s.heard_hf, s.last_hf_at = s.heard_hf + 2, at(2)
    assert s.heard_by == {LORA_ID: RadioHeard(2, T0, ("B*",)), FM_ID: RadioHeard(1, at(1)), HF_ID: RadioHeard(2, at(2))}
    s.last_path = DIGI
    assert s.heard_by[HF_ID] == RadioHeard(2, at(2), DIGI) and s.last_path == DIGI, "the path that is set is the path of the radio that heard last"
    s.heard_fm, s.last_fm_at = 0, None
    assert FM_ID not in s.heard_by and set(s.heard_by) == {LORA_ID, HF_ID}, "a radio that is set to have heard nothing has no entry"
    s.heard_hf = 0
    assert set(s.heard_by) == {LORA_ID} and s.last_hf_at is None, "a count of 0 takes the time with it"


def test_replace_takes_the_field_and_the_old_names_and_the_copy_counts_for_itself() -> None:
    s = station(heard_fm=3, last_fm_at=T0, last_path=DIGI)
    more = replace(s, heard_fm=5)
    assert (more.heard_fm, more.last_fm_at, more.last_path, s.heard_fm) == (5, T0, DIGI, 3)
    given = replace(s, heard_by={LORA_ID: RadioHeard(1, at(1))})
    assert given.heard_by == {LORA_ID: RadioHeard(1, at(1))} and given.heard_fm == 0
    copy = replace(s, packets=9)
    copy.note_on(FM_ID, at(1), ())
    assert (copy.heard_fm, s.heard_fm) == (4, 3) and copy.heard_by is not s.heard_by, "a copy does not count into the station it was made from"
    mine: dict[int, RadioHeard] = {FM_ID: RadioHeard(1, T0)}
    made = station(heard_by=mine)
    made.note_on(FM_ID, at(1), ())
    assert mine == {FM_ID: RadioHeard(1, T0)}, "nor into the dict it was given"


def test_the_station_without_the_internet_has_what_every_radio_heard() -> None:
    book = StationBook()
    book.take(packet(LORA_ID, 0, DIGI))
    book.take(packet(None, 1, ("TCPIP*",), via=IS))
    view = heard(book).radio_view()
    assert view is not None and view is not heard(book) and view.heard_by == {LORA_ID: RadioHeard(1, at(0), DIGI)} and view.packets == 1


# ---- the book seeds by radio

def test_a_station_seeded_with_what_three_radios_heard_keeps_it_and_goes_on_counting() -> None:
    book = StationBook()
    book.seed([station(packets=6, heard_rf=6, heard_by={FM_ID: RadioHeard(3, at(-9), DIGI), HF_ID: RadioHeard(1, at(-20)), LORA_ID: RadioHeard(2, at(-5), ("OH2LGW*",))})])
    s = heard(book)
    assert (s.last_radio, s.last_path, s.heard_fm, s.heard_hf) == (LORA_ID, ("OH2LGW*",), 3, 1)
    book.take(packet(HF_ID, 0))
    assert s.heard_by == {FM_ID: RadioHeard(3, at(-9), DIGI), HF_ID: RadioHeard(2, at(0), ()), LORA_ID: RadioHeard(2, at(-5), ("OH2LGW*",))} and s.packets == 7


def test_the_path_of_the_routes_the_database_kept_is_the_path_of_the_radio_that_heard_last() -> None:
    book = StationBook()
    book.seed([station(heard_by={FM_ID: RadioHeard(3, at(-9), ("OLD*",)), LORA_ID: RadioHeard(1, at(-30), ("OH2LGW*",))}), Station("OH2BBB", first_heard=T0, last_heard=T0)])
    book.seed_deliveries([("OH2AAA", DIGI, "", 2, at(-9), None), ("OH2BBB", ("OH2RDG*",), "", 1, at(-3), None)])
    a, b = heard(book), heard(book, "OH2BBB")
    assert a.last_path == DIGI and a.heard_by == {FM_ID: RadioHeard(3, at(-9), DIGI), LORA_ID: RadioHeard(1, at(-30), ("OH2LGW*",))}, "a route of the old shape (no radio) is radio 1's"
    assert b.last_path == ("OH2RDG*",) and b.heard_by == {}, "a station the cache has no radio for keeps the path as before"


def test_each_radio_takes_the_path_of_its_own_latest_route_and_the_station_shows_the_one_of_the_radio_that_heard_it_last() -> None:
    """Every radio's routes are kept (HF's too): each radio's entry gets the path of its own latest packet, and `last_path` is the radio's that heard the station last, HF's when HF did (by no digipeater)."""
    book = StationBook()
    book.seed([station(heard_by={FM_ID: RadioHeard(3, at(0)), HF_ID: RadioHeard(1, at(5), ("OLD*",))}), Station("OH2BBB", first_heard=T0, last_heard=T0, heard_by={HF_ID: RadioHeard(2, at(5))})])
    book.seed_deliveries([("OH2AAA", DIGI, "", 3, at(0), None, FM_ID), ("OH2BBB", ("OH2RDG*",), "", 1, at(1), None, FM_ID), ("OH2AAA", (), "", 1, at(5), None, HF_ID)])
    a, b = heard(book), heard(book, "OH2BBB")
    assert a.heard_by == {FM_ID: RadioHeard(3, at(0), DIGI), HF_ID: RadioHeard(1, at(5), ())} and a.last_path == (), "HF heard it last, by no digipeater"
    assert (a.deliveries.by_route, a.deliveries.direct, a.routes[HF_ID].direct) == ({("OH2RCH-2",): 3}, 0, 1), "radio 2's direct packet is its own route, not the station's"
    assert b.last_path == () and b.heard_by == {HF_ID: RadioHeard(2, at(5), ())} and b.routes[FM_ID].by_route == {("OH2RDG",): 1}, "a radio the cache has no entry for gives no path"
    book.take(packet(FM_ID, 6, ("OH2RDG*",)))
    assert a.last_path == ("OH2RDG*",) and a.heard_by[HF_ID].last_path == (), "the next packet's path is the latest"


def test_the_book_takes_the_routes_of_every_radio_from_the_packets_kept() -> None:
    """stationbook.route_groups: the rows of packetsql.radio_routes grouped by sender, path, gate and radio, the group of the oldest latest packet first; a third-party packet is the station inside it."""
    def frame(source: str, info: bytes, path: tuple[str, ...] = ()) -> bytes:
        return ax25.encode(ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse(source), tuple(ax25.Address.parse(a) for a in path), info=info))
    rows = [("OH2AAA", "OH2RCH-2*", frame("OH2AAA", b">a", ("OH2RCH-2*",)), at(0), FM_ID), ("OH2AAA", "", frame("OH2AAA", b">b"), at(1), HF_ID),
            ("OH2AAA", "OH2RCH-2*", frame("OH2AAA", b">c", ("OH2RCH-2*",)), at(2), FM_ID), ("OH7JHF-1", "", frame("OH7JHF-1", b"}OH2DPN>APRS,TCPIP,OH7JHF-1*:>d"), at(3), None),
            ("OH2BAD", "", b"\x00", at(4), FM_ID)]
    assert route_groups(rows) == [("OH2AAA", (), "", 1, at(1), None, HF_ID), ("OH2AAA", ("OH2RCH-2*",), "", 2, at(2), at(0), FM_ID), ("OH2DPN", (), "OH7JHF-1", 1, at(3), None, None)]


async def test_the_routes_of_every_radio_hfs_too_are_read_from_the_packets_the_database_kept(tmp_path: Path) -> None:
    """packetsql.radio_routes: the packets heard on any radio, with the radio, the internet's left out; what the packet log reads before it is by radio (`heard_routes`) still leaves HF's out."""
    store = await store_at(shaped(tmp_path / DB_NAME))
    assert store.db is not None
    log = PacketLog(store.db, FixedClock())
    def kept(radio_id: int | None, minutes: float, path: tuple[str, ...], via: str = "rf") -> Packet:
        frame = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2AAA"), tuple(ax25.Address.parse(a) for a in path), info=b">x")
        return Packet(at(minutes), "in", ax25.encode(frame), "OH2AAA", "APRS", path, b">x", Status("x"), via=via, radio_id=radio_id)      # type: ignore[arg-type]
    for packet_kept in (kept(FM_ID, 0, DIGI), kept(HF_ID, 1, ()), kept(None, 2, ("TCPIP*",), via=IS), kept(FM_ID, 3, DIGI)):
        assert log.append(packet_kept)
    await store.db.barrier()
    rows = await store.db.read(lambda conn: radio_routes(conn, 10))
    assert [(r[0], r[1], r[4]) for r in rows] == [("OH2AAA", "OH2RCH-2*", FM_ID), ("OH2AAA", "", HF_ID), ("OH2AAA", "OH2RCH-2*", FM_ID)]
    assert route_groups((str(s), str(p), bytes(r), parse_stamp(str(a)), radio) for s, p, r, a, radio in rows) == [("OH2AAA", (), "", 1, at(1), None, HF_ID), ("OH2AAA", DIGI, "", 2, at(3), at(0), FM_ID)]
    assert [r[1] for r in await store.db.read(lambda conn: heard_routes(conn, 10))] == ["OH2RCH-2*", "OH2RCH-2*"], "the shape of before: no HF"


def test_the_path_of_the_packet_noted_last_is_the_latest_on_one_radio_and_with_two_the_radio_heard_last_says_it() -> None:
    """A clock that stepped back (an NTP correction, a computer without a clock of its own that starts behind the times it kept): on one radio the packet taken last says the path, whatever its time, as
    before; with two radios the one that heard the station last by the time says it (the rule after a restart too, migration 33's)."""
    one = StationBook()
    one.take(packet(FM_ID, 0, DIGI))
    one.take(packet(FM_ID, -0.5, ()))
    assert heard(one).last_path == (), "one radio: the packet taken last"
    book = StationBook()
    book.take(packet(FM_ID, 0, DIGI))
    book.take(packet(HF_ID, -0.5, ()))
    s = heard(book)
    assert (s.last_radio, s.last_path) == (FM_ID, DIGI), "the latest by time is radio 1's"
    book.take(packet(HF_ID, 1, ("OH2RDG*",)))
    book.take(packet(FM_ID, 1, DIGI))
    assert (s.last_radio, s.last_path) == (FM_ID, DIGI), "radio 1 on a tie"
    s.last_path = ("OH2LGW*",)
    assert s.last_path == ("OH2LGW*",) == s.heard_by[FM_ID].last_path, "a path that is set is the path of the radio that heard last by time"
    copy = replace(s, packets=9)
    copy.note_on(HF_ID, at(5), ("A*",))
    assert (copy.last_path, s.last_path) == (("A*",), ("OH2LGW*",))


def test_an_object_of_ours_has_the_path_we_send_it_by_and_no_radio_heard_it() -> None:
    book = StationBook()
    book.set_me("OH2GBA", 60.0, 24.0)
    mine = book.own_object(OwnObject("LEADER", "object", 60.2, 24.9, "/", ">", T0, T0, path="WIDE1-1,WIDE2-1", radios=(FM_ID, LORA_ID)))
    assert mine is not None and mine.heard_by == {} and mine.last_path == ("WIDE1-1", "WIDE2-1") == mine.own_path
    direct = book.own_object(OwnObject("LEADER", "object", 60.2, 24.9, "/", ">", T0, T0, path="DIRECT"))
    assert direct is not None and direct.last_path == ()


# ---- what reads the field

def test_the_radio_of_a_message_is_chosen_from_the_field() -> None:
    book = StationBook()
    book.take(packet(HF_ID, 0))
    specs = (RadioSpec(FM_ID, "fm", "kiss", "", True, 1), RadioSpec(HF_ID, "hf", "mercury", "", True, 2))
    assert message_radio(None, heard(book).heard_by, specs, FM_ID, T0) == HF_ID, "heard on HF alone"
    book.take(packet(FM_ID, 1))
    assert message_radio(None, heard(book).heard_by, specs, FM_ID, T0) == FM_ID


def test_the_page_is_told_of_radios_1_and_2_as_before_whatever_else_heard_the_station() -> None:
    book = StationBook()
    for radio_id, minutes, path in ((FM_ID, 0, DIGI), (HF_ID, 1, ()), (LORA_ID, 2, ("OH2LGW*",))):
        book.take(packet(radio_id, minutes, path))
    row = station_row(book, heard(book))
    StationRow.model_validate_json(json.dumps(row))
    assert (row["heard_fm"], row["heard_hf"], row["last_fm_at"], row["last_hf_at"], row["last_path"]) == (1, 1, "2026-11-14T12:00:00Z", "2026-11-14T12:01:00Z", ["OH2LGW*"])
    assert "heard_by" not in row and "own_path" not in row, "the wire is what it was"
