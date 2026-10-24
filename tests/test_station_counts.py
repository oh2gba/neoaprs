"""What the station book says of what a station runs and of how many packets it sent in the last hour (neoaprs/station.py, stationnotes.py), and what the page is told of both."""
import json
from datetime import UTC, datetime, timedelta

from neoaprs.aprsparse import parse
from neoaprs.packet import Packet
from neoaprs.station import Station
from neoaprs.stationbook import StationBook
from neoaprs.web.stationwire import StationRow
from neoaprs.web.views import station_row
from tests.support.clock import FixedClock

T0 = datetime(2026, 10, 21, 12, 0, 30, tzinfo=UTC)
WORKED = b'(_fn"Oj/'                                      # a Mic-E body for the destination S32UVT


def heard(info: bytes, source: str, destination: str = "APRS", at: datetime = T0, direction: str = "in") -> Packet:
    return Packet(at, direction, b"", source, destination, (), info, parse(info, source, destination, at))  # type: ignore[arg-type]


def row_of(book: StationBook, call: str) -> StationRow:
    station = book.get(call)
    assert station is not None
    return StationRow.model_validate_json(json.dumps(station_row(book, station)))


def test_the_device_comes_from_the_destination_and_stays_when_a_later_packet_says_nothing() -> None:
    book = StationBook()
    book.take(heard(b"!4903.50N/07201.75W-Test", "OH2AAA", "APDR15"))
    assert row_of(book, "OH2AAA").device == "APRSdroid"
    book.take(heard(b">status", "OH2AAA", "APRS"))
    assert row_of(book, "OH2AAA").device == "APRSdroid"
    book.take(heard(b"!4903.50N/07201.75W-Test", "OH2BBB", "APRS"))
    assert row_of(book, "OH2BBB").device == ""


def test_the_device_of_a_mice_station_comes_from_its_comment() -> None:
    book = StationBook()
    book.take(heard(b"`" + WORKED + b">Hello^", "OH2AAA", "S32UVT"))
    assert row_of(book, "OH2AAA").device == "Kenwood TH-D74"


def test_the_device_of_the_reporter_is_not_the_devices_of_its_objects() -> None:
    book = StationBook()
    book.take(heard(b";LEADER   *092345z6012.00N/02456.00E>090/020 convoy", "OH2AAA", "APDR15"))
    assert row_of(book, "OH2AAA").device == "APRSdroid"
    assert row_of(book, "LEADER").device == ""


def test_the_hour_counts_the_packets_of_the_station_and_of_its_objects() -> None:
    book = StationBook(clock=FixedClock(T0))
    for minute in (0, 10, 20):
        book.take(heard(b"!4903.50N/07201.75W-Test", "OH2AAA", at=T0 + timedelta(minutes=minute)))
    assert row_of(book, "OH2AAA").packets == 3 and row_of(book, "OH2AAA").packets_hour == 3
    book.take(heard(b";LEADER   *092345z6012.00N/02456.00E>090/020 convoy", "OH2BBB", at=T0 + timedelta(minutes=20)))
    assert row_of(book, "LEADER").packets_hour == 1 and row_of(book, "OH2BBB").packets_hour == 1


def test_a_packet_of_ours_and_a_killed_object_are_not_counted() -> None:
    book = StationBook(clock=FixedClock(T0))
    book.set_me("OH2GBA-7", 60.2, 24.9)
    book.take(heard(b"!4903.50N/07201.75W-Test", "OH2GBA-7"))
    book.take(heard(b"!4903.50N/07201.75W-Test", "OH2GBA-7", direction="out"))
    book.take(heard(b";LEADER   _092345z6012.00N/02456.00E>090/020", "OH2BBB"))
    assert row_of(book, "OH2GBA-7").packets_hour == 0 and book.get("LEADER") is None


def test_the_row_counts_the_hour_as_of_the_clock_of_the_book() -> None:
    clock = FixedClock(T0)
    book = StationBook(clock=clock)
    book.take(heard(b"!4903.50N/07201.75W-Test", "OH2AAA"))
    clock.advance(59 * 60)
    assert row_of(book, "OH2AAA").packets_hour == 1
    clock.advance(2 * 60)
    assert row_of(book, "OH2AAA").packets_hour == 0 and row_of(book, "OH2AAA").packets == 1


def test_recount_tells_the_stations_whose_hour_became_shorter_and_only_those() -> None:
    clock = FixedClock(T0)
    book = StationBook(clock=clock)
    told: list[tuple[str, int]] = []
    book.recounted.connect(lambda s: told.append((s.call, s.hour.total)))
    book.take(heard(b"!4903.50N/07201.75W-Test", "OH2AAA", at=T0))
    clock.advance(30 * 60)
    book.take(heard(b"!4903.50N/07201.75W-Test", "OH2AAA", at=clock()))
    book.take(heard(b"!4903.50N/07201.75W-Test", "OH2BBB", at=clock()))
    clock.advance(20 * 60)
    assert book.recount() == [] and told == []
    clock.advance(15 * 60)                                      # (the first packet of OH2AAA is an hour old)
    assert [s.call for s in book.recount()] == ["OH2AAA"] and told == [("OH2AAA", 1)]
    assert book.recount() == []


def test_the_book_starts_with_the_packets_of_the_last_hour_the_log_kept() -> None:
    clock = FixedClock(T0)
    book = StationBook(clock=clock)                                                   # (a start: the stations come from the cache, the hour from the log)
    book.seed([Station("OH2AAA", first_heard=T0, last_heard=T0, packets=40), Station("OH2BBB", first_heard=T0, last_heard=T0, packets=7)])
    kept = [heard(b"!4903.50N/07201.75W-Test", "OH2AAA", at=T0 - timedelta(minutes=m)) for m in (50, 30, 5)]
    kept.append(heard(b"!4903.50N/07201.75W-Test", "OH2GONE", at=T0))
    kept.append(heard(b"!4903.50N/07201.75W-Test", "OH2BBB", at=T0, direction="out"))
    kept.append(heard(b";LEADER   *092345z6012.00N/02456.00E>090/020 convoy", "OH2BBB", at=T0))
    book.seed_recent(kept)
    assert (row_of(book, "OH2AAA").packets, row_of(book, "OH2AAA").packets_hour) == (40, 3)
    assert row_of(book, "OH2BBB").packets_hour == 1


def test_the_device_is_read_again_from_the_latest_packets_at_the_start() -> None:
    book = StationBook()
    book.seed([Station("OH2AAA", first_heard=T0, last_heard=T0)])
    book.seed_details([heard(b"!4903.50N/07201.75W-Test", "OH2AAA", "APRS", at=T0), heard(b"!4903.50N/07201.75W-Test", "OH2AAA", "APDR15", at=T0 - timedelta(minutes=1))])
    assert row_of(book, "OH2AAA").device == "APRSdroid"
