"""What each radio heard of a station (`Station.heard_by`, rule 3.3): the stored field, counted by the id of the radio a packet came on, any number of radios; the old names of radios 1 and 2 (`heard_fm`,
`heard_hf`, `last_fm_at`, `last_hf_at`) and the one path of the latest packet (`last_path`) as its views, which are read, set and taken by the constructor as before, until W3; and the station book that
counts and seeds by radio (neoaprs/station.py, stationnotes.py, stationbook.py)."""
import json
from dataclasses import fields, replace
from datetime import datetime, timedelta

from neoaprs.clock import utc
from neoaprs.messagerule import message_radio
from neoaprs.ownobject import OwnObject
from neoaprs.packet import IS, ObjectReport, Packet, Position, Status
from neoaprs.radiospec import FM_ID, HF_ID, NOT_HEARD, RadioHeard, RadioSpec
from neoaprs.station import OLD_NAMES, Station
from neoaprs.stationbook import StationBook
from neoaprs.web.stationwire import StationRow
from neoaprs.web.views import station_row

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


def test_a_packet_of_radio_2_is_no_route_for_a_message_and_one_of_any_other_radio_is() -> None:
    """The HF exception of the routes, kept as it was for R2 to delete: by the HF radio of today, radio 2."""
    book = StationBook()
    for radio_id in (FM_ID, HF_ID, LORA_ID):
        book.take(packet(radio_id, radio_id, ()))
    assert heard(book).deliveries.direct == 2, "the direct packets of radios 1 and 3 are counted for the route, the one over HF is not"


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
    assert a.last_path == DIGI and a.heard_by == {FM_ID: RadioHeard(3, at(-9), DIGI), LORA_ID: RadioHeard(1, at(-30), ("OH2LGW*",))}
    assert b.last_path == ("OH2RDG*",) and b.heard_by == {}, "a station the cache has no radio for keeps the path as before"


def test_the_path_of_an_older_route_is_radio_1s_not_radio_2s_when_radio_2_heard_the_station_last() -> None:
    """The routes leave out radio 2's packets: the latest route of a station heard last over HF is the path of radio 1's latest packet. It goes into radio 1's entry, radio 2's keeps what radio 2 heard,
    and `last_path` says the route's path until the next packet, as it did after a restart before the radios were by id."""
    book = StationBook()
    book.seed([station(heard_by={FM_ID: RadioHeard(3, at(0)), HF_ID: RadioHeard(1, at(5))}), Station("OH2BBB", first_heard=T0, last_heard=T0, heard_by={HF_ID: RadioHeard(2, at(5))})])
    book.seed_deliveries([("OH2AAA", DIGI, "", 3, at(0), None), ("OH2BBB", ("OH2RDG*",), "", 1, at(1), None)])
    a, b = heard(book), heard(book, "OH2BBB")
    assert a.heard_by == {FM_ID: RadioHeard(3, at(0), DIGI), HF_ID: RadioHeard(1, at(5), ())}, "radio 2 heard it by no digipeater"
    assert a.last_path == DIGI and b.last_path == ("OH2RDG*",) and b.heard_by == {HF_ID: RadioHeard(2, at(5), ())}
    book.take(packet(HF_ID, 6))
    assert a.last_path == () and a.heard_by[FM_ID].last_path == DIGI, "the next packet's path is the latest"


def test_the_path_of_the_packet_noted_last_is_the_latest_whatever_its_time() -> None:
    """A clock that stepped back (an NTP correction, a computer without a clock of its own that starts behind the times it kept) or two radios at one reading: the packet taken last says the path, as before."""
    book = StationBook()
    book.take(packet(FM_ID, 0, DIGI))
    book.take(packet(HF_ID, -0.5, ()))
    s = heard(book)
    assert (s.last_radio, s.last_path) == (FM_ID, ()), "the latest by time is radio 1's, the latest taken came over HF"
    book.take(packet(HF_ID, 1, ("OH2RDG*",)))
    book.take(packet(FM_ID, 1, DIGI))
    assert (s.last_radio, s.last_path) == (FM_ID, DIGI)
    s.last_path = ("OH2LGW*",)
    assert s.last_path == ("OH2LGW*",) == s.heard_by[FM_ID].last_path, "a path that is set is the path of the radio that heard last by time"
    copy = replace(s, packets=9)
    copy.note_on(HF_ID, at(-5), ("A*",))
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
