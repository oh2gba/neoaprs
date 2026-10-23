"""Which stations the page offers a Message button: the station book's `can_message`, from the data type identifier of a position (`=` and `@` take messages, `!` and `/` do not), Mic-E, a message
or an ack heard from the station, and the kind of the row; carried on the wire as `can_message`, and found again at the start from the packet log."""
import json
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.aprsthirdparty import parse_packet
from neoaprs.clock import utc
from neoaprs.packet import Packet
from neoaprs.packetlog import PacketLog
from neoaprs.stationbook import StationBook
from neoaprs.store import DB_NAME
from neoaprs.web.stationwire import StationRow
from neoaprs.web.views import station_row
from tests.support.clock import FixedClock
from tests.support.storedb import store_at

T0 = utc(2026, 10, 21, 12, 0, 0)
POSITION = "6010.00N/02456.00E>x"
MICE = "S32UVT"                                     # the destination of a Mic-E packet
MICE_BODY = b'(_fn"Oj/'


def heard(info: str | bytes, source: str = "OH2AAA", destination: str = "APRS", at: object = T0, direction: str = "in") -> Packet:
    data = info.encode("latin-1") if isinstance(info, str) else info
    frame = ax25.Frame(ax25.Address.parse(destination), ax25.Address.parse(source), (), info=data)
    decoded, third_party = parse_packet(data, source, destination, T0)
    return Packet(at, direction, ax25.encode(frame), source, destination, (), data, decoded, third_party)  # type: ignore[arg-type]


def can_message(book: StationBook, call: str = "OH2AAA") -> bool:
    station = book.get(call)
    assert station is not None
    row = StationRow.model_validate_json(json.dumps(station_row(book, station)))
    assert row.can_message is station.can_message
    return row.can_message


@pytest.mark.parametrize(("identifier", "expected"), [("=", True), ("@092345z", True), ("!", False), ("/092345z", False)])
def test_a_position_says_by_its_identifier(identifier: str, expected: bool) -> None:
    book = StationBook()
    book.take(heard(identifier + POSITION))
    assert can_message(book) is expected


@pytest.mark.parametrize("identifier", [b"`", b"'"])
def test_a_mic_e_station_does_messages(identifier: bytes) -> None:
    book = StationBook()
    book.take(heard(identifier + MICE_BODY, destination=MICE))
    assert book.get("OH2AAA").has_position and can_message(book) is True       # type: ignore[union-attr]


def test_a_mic_e_position_in_a_third_party_packet_counts_too() -> None:
    book = StationBook()
    book.take(heard(b"}OH2AAA>" + MICE.encode() + b",TCPIP*:`" + MICE_BODY, source="OH2GAT"))
    assert can_message(book) is True


def test_an_object_and_an_item_are_never_a_station_to_message() -> None:
    book = StationBook()
    book.take(heard(";FIRE     *092345z6010.00N/02456.00E>"))
    book.take(heard(")BUOY!6010.00N/02456.00E>"))
    assert can_message(book, "FIRE") is False and can_message(book, "BUOY") is False
    assert can_message(book, "OH2AAA") is True, "the one that reported them is a station we know nothing of"


def test_a_station_that_sent_a_message_does_messages_whatever_its_positions_say() -> None:
    book = StationBook()
    book.take(heard("!" + POSITION))
    assert can_message(book) is False
    book.take(heard(":OH2BBB   :hello{1"))
    assert can_message(book) is True
    book.take(heard("!" + POSITION))
    assert can_message(book) is True, "a later position does not take it back"


def test_an_ack_and_a_message_to_somebody_else_count_too() -> None:
    book = StationBook()
    book.take(heard("!" + POSITION, source="OH2AAA"))
    book.take(heard("/092345z" + POSITION, source="OH2CCC"))
    book.take(heard(":OH2BBB   :ack7", source="OH2AAA"))
    book.take(heard(":OH2DDD   :hi", source="OH2CCC"))
    assert can_message(book, "OH2AAA") is True and can_message(book, "OH2CCC") is True


def test_a_bulletin_and_a_telemetry_definition_are_no_talk() -> None:
    book = StationBook()
    book.take(heard("!" + POSITION))
    book.take(heard(":BLN1     :water level high"))
    book.take(heard(":OH2AAA   :PARM.Temp,Volt"))
    assert can_message(book) is False


def test_the_latest_position_decides_without_a_message() -> None:
    book = StationBook()
    book.take(heard("=" + POSITION))
    book.take(heard("!" + POSITION, at=T0 + timedelta(minutes=1)))
    assert can_message(book) is False
    book.take(heard("@092345z" + POSITION, at=T0 + timedelta(minutes=2)))
    assert can_message(book) is True


def test_a_station_of_which_nothing_is_known_is_not_hidden() -> None:
    book = StationBook()
    book.take(heard(">on the air"))
    assert can_message(book) is True
    book.take(heard("T#001,1,2,3,4,5,00000000"))
    assert can_message(book) is True


def test_our_own_station_is_none_to_message() -> None:
    book = StationBook()
    book.set_me("OH2ME", 60.1, 24.9)
    assert can_message(book, "OH2ME") is False
    book.take(heard(":OH2BBB   :hello", source="OH2ME"))
    assert can_message(book, "OH2ME") is False


def test_a_change_is_signalled_so_that_the_page_hears_of_it() -> None:
    book, seen = StationBook(), []
    book.changed.connect(lambda s: seen.append(s.can_message))
    book.take(heard("!" + POSITION))
    book.take(heard(":OH2BBB   :hello"))
    assert seen == [False, True]


async def test_the_flag_is_found_again_at_the_start(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    log, book = PacketLog(store.db, FixedClock()), StationBook()
    packets = [heard("!" + POSITION, "OH2NO"), heard("=" + POSITION, "OH2YES"), heard("/092345z" + POSITION, "OH2TLK"), heard(b"`" + MICE_BODY, "OH2MIC", MICE),
               heard(":OH2BBB   :hello", "OH2TLK"), heard(">just a status", "OH2NON"), heard(";FIRE     *092345z6010.00N/02456.00E>", "OH2NO")]
    for n, p in enumerate(packets):
        later = Packet(T0 + timedelta(seconds=n), p.direction, p.raw, p.source, p.destination, p.path, p.info, p.decoded)
        book.take(later)
        log.append(later)
    for station in book.stations():
        log.save_station(station)
    expected = {s.call: s.can_message for s in book.stations()}
    assert expected == {"OH2NO": False, "OH2YES": True, "OH2TLK": True, "OH2MIC": True, "OH2NON": True, "FIRE": False}
    for _ in range(100):                                                  # (more packets than the other things the book starts from read)
        log.append(heard(">noise", "OH2NSE"))
    assert await log.count() > 100

    fresh = StationBook()
    fresh.seed(await log.stations())
    assert fresh.get("OH2NO").can_message is True                        # type: ignore[union-attr]  (nothing but the cache: it knows nothing yet)
    fresh.seed_messaging(await log.messaging_evidence(30))
    assert {s.call: s.can_message for s in fresh.stations()} == expected
