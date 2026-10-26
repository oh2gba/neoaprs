"""A station as it is without the internet (`Station.radio_view`): none for a station known only from APRS-IS, the station itself when it never came from there, and for one heard both ways a copy with the radio's side only (the counts,
the times, the last hour, the place and the track the packets that were not from the internet gave), however the packets came and after a restart (`StationBook.seed_radio`)."""
from datetime import datetime, timedelta

from neoaprs.clock import utc
from neoaprs.hourcount import HourCount
from neoaprs.packet import Packet, Position, Status, Via
from neoaprs.station import Station
from neoaprs.stationbook import StationBook

T0 = utc(2026, 10, 21, 12, 0, 0)


def heard(book: StationBook, lat: float | None, lon: float = 25.0, via: Via = "rf", at: datetime = T0, source: str = "OH2AAA", comment: str = "") -> Packet:
    decoded = Status("hello") if lat is None else Position(lat=lat, lon=lon, symbol_table="/", symbol_code=">", comment=comment)
    packet = Packet(heard_at=at, direction="in", raw=b"", source=source, destination="APRS", path=() if via == "is" else ("OH2RCH-2*",), info=b"", decoded=decoded, via=via)
    book.take(packet)
    return packet


def station(book: StationBook) -> Station:
    found = book.get("OH2AAA")
    assert found is not None
    return found


def test_a_station_known_only_from_the_internet_is_none_and_one_never_heard_from_it_is_itself() -> None:
    book = StationBook()
    heard(book, 60.0, via="is", source="OH2NET")
    heard(book, 61.0)
    net, air = book.get("OH2NET"), station(book)
    assert net is not None and net.internet_only and net.radio_view() is None
    assert air.radio_view() is air and air.radio is None, "a station never heard from the internet keeps no second place"


def test_the_radio_side_of_a_station_that_the_internet_moved_is_where_the_radio_put_it() -> None:
    book = StationBook()
    heard(book, 61.0, 25.0, comment="radio")
    heard(book, 60.0, 24.0, via="is", at=T0 + timedelta(minutes=30), comment="net")
    both = station(book)
    assert (both.lat, both.position_via, both.last_comment, both.packets) == (60.0, "is", "net", 2)
    view = both.radio_view()
    assert view is not None and view is not both
    assert (view.lat, view.lon, view.position_via, view.last_comment, view.packets, view.heard_is, view.last_is_at, view.last_heard, view.last_position_at, view.heard_rf) == (61.0, 25.0, "rf", "radio", 1, 0, None, T0, T0, 1)
    assert view.track == [(T0, 61.0, 25.0)] and both.track == [(T0, 61.0, 25.0), (T0 + timedelta(minutes=30), 60.0, 24.0)]
    heard(book, 61.5, 25.5, at=T0 + timedelta(minutes=40))
    again = both.radio_view()
    assert again is not None and (again.lat, again.last_heard, again.packets, len(again.track)) == (61.5, T0 + timedelta(minutes=40), 2, 2)
    assert both.lat == 61.5, "the station's own place follows the latest packet of any channel"


def test_a_station_whose_radio_packets_had_no_position_has_none_without_the_internet() -> None:
    book = StationBook()
    heard(book, None)                                   # (a status from the radio)
    heard(book, 60.0, 24.0, via="is", at=T0 + timedelta(minutes=1))
    view = station(book).radio_view()
    assert view is not None and (view.lat, view.lon, view.position_via, view.last_position_at, view.track, view.has_position, view.packets) == (None, None, None, None, [], False, 1)


def test_a_station_the_internet_knew_first_gets_the_radios_place_when_the_radio_hears_it() -> None:
    book = StationBook()
    heard(book, 60.0, 24.0, via="is")
    heard(book, 61.0, 25.0, at=T0 + timedelta(minutes=1))
    view = station(book).radio_view()
    assert view is not None and (view.lat, view.position_via, view.track) == (61.0, "rf", [(T0 + timedelta(minutes=1), 61.0, 25.0)])


def test_the_last_hour_without_the_internet_counts_the_packets_of_the_radio() -> None:
    book = StationBook()
    for n in range(3):                                  # (in the order they came)
        heard(book, 61.0, at=T0 + timedelta(minutes=n))
        if n < 2:
            heard(book, 60.0, via="is", at=T0 + timedelta(minutes=n))
    both = station(book)
    view = both.radio_view()
    assert view is not None and both.hour.count(T0 + timedelta(minutes=5)) == 5 and view.hour.count(T0 + timedelta(minutes=5)) == 3
    assert view.hour.count(T0 + timedelta(minutes=61)) == 1, "the minutes expire as they do for the station"


def test_the_radios_place_is_made_again_from_the_packets_at_a_restart() -> None:
    book = StationBook()
    seeded = Station("OH2AAA", first_heard=T0, last_heard=T0 + timedelta(minutes=30), packets=2, heard_rf=1, heard_is=1, last_rf_at=T0, last_is_at=T0 + timedelta(minutes=30), lat=60.0, lon=24.0,
                     last_position_at=T0 + timedelta(minutes=30), position_via="is")
    book.seed([seeded])
    other = Station("OH2BBB", first_heard=T0, last_heard=T0, packets=1, heard_rf=1, last_rf_at=T0, lat=62.0, lon=26.0, last_position_at=T0, position_via="rf")
    book.seed([other])
    radio = Packet(heard_at=T0, direction="in", raw=b"", source="OH2AAA", destination="APRS", path=("OH2RCH-2*",), info=b"", decoded=Position(61.0, 25.0, "/", ">", comment="radio"), via="rf")
    elsewhere = Packet(heard_at=T0, direction="in", raw=b"", source="OH2BBB", destination="APRS", path=(), info=b"", decoded=Position(62.0, 26.0, "/", ">"), via="rf")
    book.seed_radio([radio, elsewhere])
    view = seeded.radio_view()
    assert view is not None and (view.lat, view.last_comment, view.position_via, view.last_position_at, view.track) == (61.0, "radio", "rf", T0, [(T0, 61.0, 25.0)])
    assert other.radio is None, "a station never heard from the internet is left alone"


def test_a_count_of_the_hour_less_the_packets_of_one_channel() -> None:
    whole, part = HourCount(), HourCount()
    for n, count in ((0, 2), (1, 1), (3, 4)):
        whole.note(T0 + timedelta(minutes=n), count)
    part.note(T0, 2)
    part.note(T0 + timedelta(minutes=3), 1)
    left = whole.without(part)
    assert (left.total, left.count(T0 + timedelta(minutes=5))) == (4, 4) and left.count(T0 + timedelta(minutes=62)) == 3
    assert whole.total == 7 and part.total == 3, "the counts it was made of are as they were"
