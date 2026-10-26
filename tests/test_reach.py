"""How a packet got to us in plain words (neoaprs/reach.py): the way an internet packet got into the network, read from the q-construct of its APRS-IS path, and the two latest routes of a station for the map."""
from datetime import timedelta

import pytest

from neoaprs.aprsisline import parse_is_line
from neoaprs.aprsparse import parse
from neoaprs.clock import utc
from neoaprs.packet import Packet, ThirdParty
from neoaprs.reach import Reach, RouteMark, mark_of, pushed, reach_of, reach_of_path
from neoaprs.stationbook import StationBook

T0 = utc(2026, 10, 26, 12, 0, 0)
MIN = timedelta(minutes=1)
POS_A = "!6010.00N/02456.00E>"
POS_B = "!6020.00N/02506.00E>"


def path(text: str) -> tuple[str, ...]:
    return tuple(text.split(",")) if text else ()


@pytest.mark.parametrize("text, expected", [
    ("qAR,OH2GW-10", Reach("igate", "OH2GW-10")),                                        # an iGate heard it direct
    ("WIDE1*,OH2RCH-2*,WIDE2-1,qAR,OH2GW-10", Reach("igate", "OH2GW-10", ("?", "OH2RCH-2"))),
    ("OH2RCH-2*,qAO,OH2RX-1", Reach("igate", "OH2RX-1", ("OH2RCH-2",))),                  # (a receive-only iGate)
    ("OH2RCH-2*,qAO,OH2RX-1*", Reach("igate", "OH2RX-1", ("OH2RCH-2",))),                 # (a star after the iGate's call is not part of it)
    ("OH2RCH-1*,OH2RCH-3*,qAR,OH2GW-10", Reach("igate", "OH2GW-10", ("OH2RCH-1", "OH2RCH-3"))),
    ("WIDE1-1,WIDE2-1,qAR,OH2GW-10", Reach("igate", "OH2GW-10")),                         # (nobody repeated it: the iGate heard the sender itself)
    ("OH2RCH-2,qAR,OH2GW-10", Reach("igate", "OH2GW-10")),                                # (a digipeater without a star has not repeated it)
    ("OH2RCH-2*,qAr,OH2GW-10", Reach("igate", "OH2GW-10", ("OH2RCH-2",))),               # (gated, received indirectly)
    ("OH2RCH-2*,qAo,OH2GW-10", Reach("igate", "OH2GW-10", ("OH2RCH-2",))),
    ("TCPIP*,qAC,T2FINLAND", Reach("app")),
    ("TCPXX*,qAX,CWOP-5", Reach("app")),
    ("TCPIP*,qAS,PE1RXF", Reach("app")),
    ("qAU,T2FINLAND", Reach("app")),
    ("TCPIP*", Reach("app")),                                                             # (no q-construct, but it says TCPIP)
    ("WIDE1*,qAC,T2FINLAND", Reach("app")),                                               # (a client that wrote a digipeater of its own into the path is still a client)
])
def test_the_way_an_internet_packet_got_there_is_read_from_the_q_construct(text: str, expected: Reach) -> None:
    assert reach_of_path(path(text)) == expected


@pytest.mark.parametrize("text", ["", "WIDE1*,OH2RCH-2*", "qAZ,OH2GW-10", "TCPIP*,qAI,T2FINLAND,OH2ABC", "OH2RCH-2*,qAR", "qAR"])
def test_a_path_that_does_not_say_is_not_read(text: str) -> None:
    assert reach_of_path(path(text)) is None


def test_an_internet_packet_is_read_and_one_heard_on_the_radio_is_not() -> None:
    line = parse_is_line("OH2RDG-7>APRX29,WIDE1*,OH2RCH-2*,WIDE2-1,qAR,OH2RDK-1:!6010.00N/02456.00E>", T0)
    assert reach_of(line) == Reach("igate", "OH2RDK-1", ("?", "OH2RCH-2"))
    on_air = Packet(T0, "in", b"", "OH2AAA", "APRS", ("OH2RCH-2*",), POS_A.encode(), parse(POS_A.encode(), "OH2AAA", "APRS", T0))
    assert reach_of(on_air) is None


def test_a_third_party_packet_heard_on_the_radio_is_a_route_through_its_gate_and_has_no_reach() -> None:
    info = POS_A.encode()
    packet = Packet(T0, "in", b"", "OH7JHF-1", "APRS", ("OH2RCH-3*",), info, parse(info, "OH2AAA", "APRS", T0), ThirdParty("OH2AAA", "APRS", ("TCPIP", "OH7JHF-1*")), "rf-gated")
    assert reach_of(packet) is None
    assert mark_of(packet, 60.1, 24.9) == RouteMark("gated", ("OH2RCH-3",), "OH7JHF-1", T0, 60.1, 24.9)
    direct = Packet(T0, "in", b"", "OH7JHF-1", "APRS", (), info, parse(info, "OH2AAA", "APRS", T0), ThirdParty("OH2AAA", "APRS", ("TCPIP", "OH7JHF-1*")), "rf-gated")
    assert mark_of(direct, None, None) == RouteMark("gated", (), "OH7JHF-1", T0, None, None)


def test_the_mark_of_a_packet_is_its_route() -> None:
    radio = Packet(T0, "in", b"", "OH2AAA", "APRS", ("WIDE1*", "OH2RCH-2*"), POS_A.encode(), parse(POS_A.encode(), "OH2AAA", "APRS", T0))
    assert mark_of(radio, 60.1, 24.9) == RouteMark("rf", ("?", "OH2RCH-2"), "", T0, 60.1, 24.9)
    assert mark_of(radio, None, None) == RouteMark("rf", ("?", "OH2RCH-2"), "", T0, None, None)
    heard = parse_is_line("OH2AAA>APRS,OH2RCH-2*,qAR,OH2GW-10:" + POS_A, T0)
    assert mark_of(heard, 60.1, 24.9) == RouteMark("igate", ("OH2RCH-2",), "OH2GW-10", T0, 60.1, 24.9)
    sent = parse_is_line("OH2AAA>APRS,TCPIP*,qAC,T2FINLAND:" + POS_A, T0)
    assert mark_of(sent, None, None) == RouteMark("app", (), "", T0, None, None)
    assert mark_of(parse_is_line("OH2AAA>APRS,qAZ,T2FINLAND:" + POS_A, T0), None, None) is None


def mark(kind: str, *hops: str, gate: str = "", minute: int = 0) -> RouteMark:
    return RouteMark(kind, hops, gate, T0 + minute * MIN, None, None)  # type: ignore[arg-type]


def test_a_station_keeps_the_latest_route_and_the_one_before_it_that_was_another() -> None:
    a, b, c = mark("rf", "OH2RCH-2"), mark("rf", "OH2RCH-1", "OH2RCH-3", minute=1), mark("igate", "OH2RCH-2", gate="OH2GW-10", minute=2)
    marks = pushed((), a)
    assert marks == (a,)
    marks = pushed(marks, b)
    assert marks == (b, a)
    again = mark("rf", "OH2RCH-1", "OH2RCH-3", minute=3)
    marks = pushed(marks, again)
    assert marks == (again, a), "(the same route again only renews the latest)"
    marks = pushed(marks, c)
    assert marks == (c, again), "(three routes: the oldest is gone)"
    back = mark("rf", "OH2RCH-1", "OH2RCH-3", minute=4)
    assert pushed(marks, back) == (back, c), "(the route before comes back: the two change places)"


def test_the_same_hops_by_another_channel_or_another_iGate_are_another_route() -> None:
    radio, gated = mark("rf", "OH2RCH-2"), mark("gated", "OH2RCH-2", gate="OH7JHF-1")
    assert pushed((radio,), gated) == (gated, radio)
    one, other = mark("igate", gate="OH2GW-10"), mark("igate", gate="OH2GW-11")
    assert pushed((one,), other) == (other, one)
    assert pushed((mark("app"),), mark("app", minute=1)) == (mark("app", minute=1),)


def test_the_station_book_keeps_where_a_moving_station_was_when_each_route_was_heard() -> None:
    book = StationBook()

    def heard(info: str, path_text: str, minute: int) -> None:
        at = T0 + minute * MIN
        book.take(Packet(at, "in", b"", "OH2MOV-9", "APRS", path(path_text), info.encode(), parse(info.encode(), "OH2MOV-9", "APRS", at)))

    heard(POS_A, "OH2RCH-2*", 0)
    heard(">status, no position", "OH2RCH-2*", 1)
    heard(POS_B, "OH2RCH-1*,OH2RCH-3*", 2)
    heard(">status again", "OH2RCH-1*,OH2RCH-3*", 3)
    station = book.get("OH2MOV-9")
    assert station is not None
    first, latest = station.route_marks[1], station.route_marks[0]
    assert (first.kind, first.hops, first.at) == ("rf", ("OH2RCH-2",), T0 + MIN), "(the later packet of the same route renews it)"
    assert (first.lat, first.lon) == pytest.approx((60.1667, 24.9333), abs=1e-4), "(a packet with no position was heard where the station had been put by the one before)"
    assert (latest.hops, latest.at) == (("OH2RCH-1", "OH2RCH-3"), T0 + 3 * MIN) and (latest.lat, latest.lon) == pytest.approx((60.3333, 25.1), abs=1e-4)


def test_the_station_book_keeps_the_reach_of_the_latest_internet_packet_and_both_channels_have_a_mark() -> None:
    book = StationBook()
    book.take(Packet(T0, "in", b"", "OH2AAA", "APRS", ("OH2RCH-2*",), POS_A.encode(), parse(POS_A.encode(), "OH2AAA", "APRS", T0)))
    book.take(parse_is_line("OH2AAA>APRS,OH2RCH-2*,qAR,OH2GW-10:" + POS_A, T0 + MIN))
    station = book.get("OH2AAA")
    assert station is not None
    assert station.internet_reach == Reach("igate", "OH2GW-10", ("OH2RCH-2",))
    assert [m.kind for m in station.route_marks] == ["igate", "rf"]
    book.take(parse_is_line("OH2AAA>APRS,TCPIP*,qAC,T2FINLAND:>from an app", T0 + 2 * MIN))
    assert station.internet_reach == Reach("app") and [m.kind for m in station.route_marks] == ["app", "igate"]
    book.take(parse_is_line("OH2AAA>APRS,qAZ,T2FINLAND:>unreadable", T0 + 3 * MIN))
    assert station.internet_reach == Reach("app") and [m.kind for m in station.route_marks] == ["app", "igate"], "(a path that does not say changes nothing)"


def test_the_routes_are_read_again_from_the_packets_kept_at_the_start() -> None:
    book = StationBook()
    book.take(Packet(T0, "in", b"", "OH2AAA", "APRS", (), POS_A.encode(), parse(POS_A.encode(), "OH2AAA", "APRS", T0)))
    fresh = StationBook()
    fresh.seed([book.get("OH2AAA")])  # type: ignore[list-item]
    station = fresh.get("OH2AAA")
    assert station is not None
    station.route_marks = ()
    packets = [
        Packet(T0, "in", b"", "OH2AAA", "APRS", ("OH2RCH-2*",), POS_A.encode(), parse(POS_A.encode(), "OH2AAA", "APRS", T0)),
        parse_is_line("OH2AAA>APRS,OH2RCH-2*,qAR,OH2GW-10:>x", T0 + MIN),
        Packet(T0 + 2 * MIN, "out", b"", "OH2AAA", "APRS", (), b">ours", parse(b">ours", "OH2AAA", "APRS", T0)),
        parse_is_line("NOBODY>APRS,TCPIP*,qAC,T2FINLAND:>x", T0 + 3 * MIN),
    ]
    fresh.seed_routes(packets)
    assert [(m.kind, m.gate) for m in station.route_marks] == [("igate", "OH2GW-10"), ("rf", "")]
    assert station.route_marks[1].lat == pytest.approx(60.1667, abs=1e-4) and station.route_marks[0].lat == pytest.approx(60.1667, abs=1e-4), "(the position seen in the packets before it)"
    assert station.internet_reach == Reach("igate", "OH2GW-10", ("OH2RCH-2",))


OBJECT = ";OH2FTJ   *111111z6020.08N/02503.76E-Vantaa, Asola"


@pytest.mark.parametrize("path_text, reach, kind", [("TCPIP*,qAC,T2CZECH", Reach("app"), "app"), ("OH2RCH-2*,qAR,OH2GW-10", Reach("igate", "OH2GW-10", ("OH2RCH-2",)), "igate")])
def test_an_object_that_came_over_the_internet_has_the_way_it_got_there_as_well_as_the_station_that_sent_it(path_text: str, reach: Reach, kind: str) -> None:
    book = StationBook()
    book.take(parse_is_line(f"OH2HCY>APRX29,{path_text}:{OBJECT}", T0))
    for call in ("OH2HCY", "OH2FTJ"):
        station = book.get(call)
        assert station is not None and station.internet_reach == reach and [m.kind for m in station.route_marks] == [kind]
    named = book.get("OH2FTJ")
    assert named is not None and named.kind == "object" and named.route_marks[0].lat == pytest.approx(60.3347, abs=1e-4), "(the mark is where the object is)"


def test_the_routes_of_an_object_and_an_item_are_read_again_from_the_packets_kept_at_the_start() -> None:
    book = StationBook()
    book.take(parse_is_line(f"OH2HCY>APRX29,TCPIP*,qAC,T2CZECH:{OBJECT}", T0))
    book.take(parse_is_line("OH2HCY>APRX29,OH2RCH-2*,qAR,OH2GW-10:)WELL!6021.00N/02504.00E-spring", T0))
    fresh = StationBook()
    fresh.seed([s for call in ("OH2HCY", "OH2FTJ", "WELL") if (s := book.get(call)) is not None])
    for call in ("OH2FTJ", "WELL"):
        station = fresh.get(call)
        assert station is not None
        station.internet_reach, station.route_marks = None, ()
    fresh.seed_routes([parse_is_line(f"OH2HCY>APRX29,TCPIP*,qAC,T2CZECH:{OBJECT}", T0), parse_is_line("OH2HCY>APRX29,OH2RCH-2*,qAR,OH2GW-10:)WELL!6021.00N/02504.00E-spring", T0 + MIN)])
    obj, item = fresh.get("OH2FTJ"), fresh.get("WELL")
    assert obj is not None and item is not None
    assert obj.internet_reach == Reach("app") and item.internet_reach == Reach("igate", "OH2GW-10", ("OH2RCH-2",))
    assert obj.route_marks[0].lat == pytest.approx(60.3347, abs=1e-4)
