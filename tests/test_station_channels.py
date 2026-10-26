"""The station book by channel (neoaprs/stationbook.py, stationnotes.py, station.py): each station keeps, for the radio, the radio's third-party packets and the internet, how many packets and when the latest was heard, and the
channel of its position (the latest packet wins); everything that means "on the air near us" counts the radio only: the routes, the direct time, the path to send by, the ALOHA circle, the card's last route and whether
a message to it makes sense."""
import json
from datetime import datetime, timedelta

import pytest

from neoaprs.aprsisline import parse_is_line
from neoaprs.aprsparse import parse
from neoaprs.clock import utc
from neoaprs.packet import Message, Packet, ThirdParty
from neoaprs.route import heard_path
from neoaprs.stationbook import StationBook
from neoaprs.web.stationwire import StationRow
from neoaprs.web.views import station_row

T0 = utc(2026, 10, 26, 12, 0, 0)
MIN = timedelta(minutes=1)


def on_air(info: str, source: str = "OH2AAA", at: datetime = T0, path: tuple[str, ...] = ("OH2RCH-2*",)) -> Packet:
    return Packet(at, "in", b"", source, "APRS", path, info.encode(), parse(info.encode(), source, "APRS", at))


def gated(info: str, inner: str = "OH2AAA", gate: str = "OH7JHF-1", at: datetime = T0) -> Packet:
    return Packet(at, "in", b"", gate, "APRS", ("OH2RCH-3*",), info.encode(), parse(info.encode(), inner, "APRS", at), ThirdParty(inner, "APRS", ("TCPIP", gate + "*")), "rf-gated")


def internet(info: str, source: str = "OH2AAA", at: datetime = T0, path: str = "TCPIP*,qAC,T2FINLAND") -> Packet:
    return parse_is_line(f"{source}>APRS,{path}:{info}", at)


POS_A = "!6010.00N/02456.00E>"
POS_B = "!6020.00N/02506.00E>"


def test_a_station_heard_on_the_radio_alone_counts_the_radio_and_has_a_route() -> None:
    book = StationBook()
    book.take(on_air(POS_A))
    book.take(on_air(">status", at=T0 + MIN, path=()))
    station = book.get("OH2AAA")
    assert station is not None
    assert (station.packets, station.heard_rf, station.heard_rf_gated, station.heard_is) == (2, 2, 0, 0)
    assert (station.last_rf_at, station.last_rf_gated_at, station.last_is_at, station.position_via, station.internet_only) == (T0 + MIN, None, None, "rf", False)
    assert (station.deliveries.direct, station.last_direct_at, station.last_path) == (1, T0 + MIN, ())


def test_a_station_known_from_the_internet_alone_is_marked_so_has_no_route_and_cannot_be_messaged() -> None:
    book = StationBook()
    book.take(internet(POS_A))
    book.take(internet(">on the net", at=T0 + MIN, path="WIDE1-1,qAR,OH2RDK-1"))
    station = book.get("OH2AAA")
    assert station is not None
    assert (station.packets, station.heard_rf, station.heard_rf_gated, station.heard_is) == (2, 0, 0, 2)
    assert (station.last_rf_at, station.last_is_at, station.position_via, station.internet_only, station.last_heard) == (None, T0 + MIN, "is", True, T0 + MIN)
    assert station.has_position and (station.lat, station.lon) == pytest.approx((60.1667, 24.9333), abs=1e-4)
    assert (station.deliveries.direct, station.deliveries.by_route, station.last_path, station.last_via, station.best_route, station.last_direct_at) == (0, {}, (), "", None, None)
    assert station.can_message is False and station.position_messaging is False, "(a position with `!` says it takes no messages; with `=` it would say yes, and the channel still says no)"
    book.take(internet("=6010.00N/02456.00E>", at=T0 + 2 * MIN))
    assert book.get("OH2AAA").position_messaging is True and book.get("OH2AAA").can_message is False  # type: ignore[union-attr]


def test_a_station_heard_both_ways_shows_both_and_the_latest_packet_gives_the_position() -> None:
    book = StationBook()
    book.take(on_air(POS_A))
    book.take(internet(POS_B, at=T0 + MIN))
    station = book.get("OH2AAA")
    assert station is not None
    assert (station.heard_rf, station.heard_is, station.last_rf_at, station.last_is_at, station.internet_only, station.packets) == (1, 1, T0, T0 + MIN, False, 2)
    assert (station.position_via, station.last_position_at) == ("is", T0 + MIN) and (station.lat, station.lon) == pytest.approx((60.3333, 25.1), abs=1e-4)
    book.take(on_air(POS_A, at=T0 + 2 * MIN))
    assert station.position_via == "rf" and (station.lat, station.lon) == pytest.approx((60.1667, 24.9333), abs=1e-4), "the channel that gave the position last"
    assert station.last_heard == T0 + 2 * MIN and len(station.track) == 3


def test_the_routes_the_direct_time_and_the_path_to_send_by_are_those_of_the_radio_whatever_the_internet_says() -> None:
    book = StationBook()
    for n in range(2):
        book.take(on_air(">a", at=T0 + n * MIN, path=("OH2RCH-2*",)))
    book.take(internet(">via the net", at=T0 + 3 * MIN, path="TCPIP*,qAC,T2FINLAND"))
    book.take(internet(">via a digipeater and an iGate", at=T0 + 4 * MIN, path="WIDE1*,OH2RDG-1*,qAR,OH2RDK-1"))
    station = book.get("OH2AAA")
    assert station is not None
    assert station.deliveries.heard_via() == [("OH2RCH-2", 2)] and station.deliveries.direct == 0 and station.last_direct_at is None
    assert station.last_path == ("OH2RCH-2*",) and station.last_via == "" and station.best_route is not None and station.best_route.hops == ("OH2RCH-2",)
    assert heard_path(station.deliveries, T0 + 5 * MIN) == ("OH2RCH-2",)
    assert station.packets == 4 and station.hour.count(T0 + 4 * MIN) == 4, "(the packets of the last hour are the station's, whatever the channel)"


def test_a_third_party_packet_is_the_radios_and_counts_for_its_iGate_while_one_from_the_internet_counts_for_nobody() -> None:
    book = StationBook()
    book.take(on_air("!6010.00N/02456.00E#iGate", source="OH7JHF-1", path=()))
    book.take(gated(">from the net", inner="OH2AAA"))
    book.take(internet(">also from the net", source="OH2BBB"))
    gate, inner = book.get("OH7JHF-1"), book.get("OH2AAA")
    assert gate is not None and inner is not None and gate.gated == 1
    assert (inner.heard_rf, inner.heard_rf_gated, inner.heard_is, inner.last_rf_gated_at, inner.internet_only, inner.deliveries.gated) == (0, 1, 0, T0, False, 1)
    assert inner.can_message is True, "(an iGate put it on the air: a message to it may go the same way back)"
    wrapped = parse_is_line("OH7JHF-1>APRS,TCPIP*,qAC,T2FINLAND:}OH2CCC>APJYC1,TCPIP,OH7JHF-1*:>third party from the net", T0)
    book.take(wrapped)
    assert book.get("OH2CCC") is not None and book.get("OH2CCC").heard_is == 1 and gate.gated == 1, "(the iGate is not credited with a packet that was never on the air)"  # type: ignore[union-attr]


def test_an_object_reported_over_the_internet_is_known_from_the_internet_only_and_the_one_on_the_radio_is_not() -> None:
    book = StationBook()
    book.take(internet(";LEADER   *092345z6012.00N/02456.00E>090/020 convoy", source="OH2XYZ"))
    book.take(on_air(")AID #!6015.00N/02458.00EA first aid", source="OH2XYZ"))
    leader, aid = book.get("LEADER"), book.get("AID #")
    assert leader is not None and aid is not None
    assert (leader.kind, leader.heard_is, leader.heard_rf, leader.internet_only, leader.position_via, leader.reported_by, leader.last_path) == ("object", 1, 0, True, "is", "OH2XYZ", ())
    assert (aid.kind, aid.heard_is, aid.heard_rf, aid.internet_only, aid.position_via, aid.last_path) == ("item", 0, 1, False, "rf", ("OH2RCH-2*",))
    assert aid.deliveries.direct == 0 and not aid.deliveries.by_route, "(an object has no route, as before)"
    assert isinstance(book.get("OH2XYZ"), type(leader)) and book.get("OH2XYZ").heard_is == 1 and book.get("OH2XYZ").heard_rf == 1  # type: ignore[union-attr]


def test_our_own_call_over_the_internet_is_not_proof_that_the_radio_is_heard_and_over_the_radio_it_is() -> None:
    book = StationBook()
    book.set_me("OH2GBA", 60.2, 24.9, "/", "-", "Home")
    me = book.me
    assert me is not None
    before = me.last_heard
    assert book.take(internet(POS_A, source="OH2GBA", at=T0 + MIN)) is None and me.last_heard == before and me.heard_is == 0 and me.lat == 60.2
    assert book.take(on_air(POS_A, source="OH2GBA", at=T0 + 2 * MIN)) is me and me.last_heard == T0 + 2 * MIN and me.heard_rf == 0 and me.lat == 60.2


def test_a_packet_we_sent_is_not_heard_at_all() -> None:
    book = StationBook()
    out = Packet(T0, "out", b"", "OH2GBA", "APRS", (), b"", Message("OH2AAA", "hi"))
    assert book.take(out) is None and len(book) == 0


def test_the_row_for_the_page_carries_the_channels_and_a_route_only_for_the_radio() -> None:
    book = StationBook()
    book.take(internet(POS_A, source="OH2NET"))
    book.take(on_air(POS_A, source="OH2RF"))
    book.take(gated(">x", inner="OH2GATE"))
    book.take(on_air(POS_A, source="OH2BOTH"))
    book.take(internet(POS_B, source="OH2BOTH", at=T0 + MIN))
    rows = {call: StationRow.model_validate_json(json.dumps(station_row(book, book.get(call)))) for call in ("OH2NET", "OH2RF", "OH2GATE", "OH2BOTH")}  # type: ignore[arg-type]
    assert [(r.heard_rf, r.heard_rf_gated, r.heard_is, r.position_via) for r in rows.values()] == [(0, 0, 1, "is"), (1, 0, 0, "rf"), (0, 1, 0, None), (1, 0, 1, "is")]
    assert rows["OH2NET"].last_route == "" and rows["OH2NET"].last_path == [] and rows["OH2NET"].best_route == "" and rows["OH2NET"].suggested_path is None and rows["OH2NET"].can_message is False
    assert rows["OH2RF"].last_route == "via OH2RCH-2" and rows["OH2GATE"].last_route == "via OH7JHF-1 (internet) → OH2RCH-3"
    assert rows["OH2BOTH"].last_route == "via OH2RCH-2" and rows["OH2BOTH"].last_is_at is not None and rows["OH2BOTH"].last_rf_at is not None
    assert rows["OH2GATE"].lat is None and rows["OH2GATE"].position_via is None, "(a status has no position)"


def test_the_book_sorts_by_the_latest_packet_of_any_channel() -> None:
    book = StationBook()
    book.take(on_air(">a", source="OH2RF", at=T0))
    book.take(internet(">b", source="OH2NET", at=T0 + MIN))
    assert [s.call for s in book.stations()] == ["OH2NET", "OH2RF"]


def test_a_status_report_and_a_message_from_the_internet_note_what_they_say_but_make_no_station_messageable() -> None:
    book = StationBook()
    book.take(internet(">on the net", source="OH2NET"))
    book.take(internet(":OH2GBA   :hello{1", source="OH2NET"))
    station = book.get("OH2NET")
    assert station is not None and station.last_status == "on the net" and station.sent_message and station.can_message is False
