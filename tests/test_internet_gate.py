"""The one gate for packets from the internet (neoaprs/wiring.py, `Services.hear_internet`): a packet that came from APRS-IS (`Packet.via` is `is`) goes only to the packet log, the station book and the weather log and
is told to the page; what answers, acknowledges, repeats, sends or gates never gets it. The test walks the signals of a built app and every part that takes a packet, so that a part added later and connected
to the radio's signal, or given a packet by any other way, fails here until it is classified; then a whole daemon is handed such packets that would each make it transmit, and says nothing: by `hear_internet`, and
again by the connection to APRS-IS that reads them from a server (neoaprs/aprsis.py), whose one outlet, the signal `heard`, is held to `hear_internet` alone."""
import inspect
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from neoaprs import wiring
from neoaprs.packet import GATEABLE, IS, VIAS, Packet
from neoaprs.wiring import ON_AIR_ONLY, SEEN_BY_ALL, AirOnly
from tests.support.air import from_internet, message_info, on_air, said
from tests.support.env import Env, idle_for, until
from tests.support.fakeaprsis import fake_aprsis

POSITION = b"=6012.34N/02456.78E-from the internet"


def parts_of(e: Env) -> dict[str, Any]:
    return {name: value for name, value in vars(e.ctl).items() if not name.startswith("_")}


def owner(e: Env, handler: Any) -> str:
    """The name in `Services` of the part a handler of a signal belongs to ('wiring' for a function of the wiring itself)."""
    target = handler.handler if isinstance(handler, AirOnly) else handler
    part = getattr(target, "__self__", None)
    if part is None:
        assert target is wiring._log_packet, f"{target!r} is connected to a packet signal and is no part of the program"
        return "wiring"
    names = [name for name, value in parts_of(e).items() if value is part]
    assert len(names) == 1, f"{target!r} belongs to no single part of Services"
    return names[0]


def connected(e: Env, which: str) -> list[tuple[str, bool]]:
    signal = e.ctl.tnc.packet if which == "radio" else e.ctl.internet_packet
    return [(owner(e, handler), isinstance(handler, AirOnly)) for handler in signal._handlers]


def test_the_radios_signal_has_the_parts_of_the_two_lists_and_nothing_else_and_the_ones_that_act_are_behind_the_lock(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    radio = connected(e, "radio")
    assert [name for name, locked in radio if not locked and name != "wiring"] == list(SEEN_BY_ALL)
    assert [name for name, locked in radio if locked] == list(ON_AIR_ONLY), "in this order: the digipeater last"
    assert radio[-1] == ("digipeater", True)


def test_the_signal_of_the_internet_has_the_log_the_book_and_the_weather_log_and_nothing_else(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    assert connected(e, "internet") == [("wiring", False), *[(name, False) for name in SEEN_BY_ALL]]
    assert set(ON_AIR_ONLY).isdisjoint(name for name, _ in connected(e, "internet"))


def packet_takers(e: Env) -> dict[str, set[str]]:
    """For each part of the program, and the parts it holds (two levels down), the public methods that have a parameter that is a Packet."""
    found: dict[str, set[str]] = {}
    seen: set[int] = set()

    def walk(label: str, part: object, depth: int) -> None:
        if id(part) in seen or not type(part).__module__.startswith("neoaprs") or depth > 2:
            return
        seen.add(id(part))
        for name in dir(part):
            member = inspect.getattr_static(part, name, None)
            if name.startswith("_") or not inspect.isfunction(member):
                continue
            hints = inspect.signature(getattr(part, name)).parameters.values()
            if any(p.annotation is Packet or p.annotation == "Packet" for p in hints):
                found.setdefault(label, set()).add(name)
        for name, child in vars(part).items() if hasattr(part, "__dict__") else []:
            walk(f"{label}.{name}", child, depth + 1)

    for name, part in parts_of(e).items():
        walk(name, part, 0)
    return found


# what takes a packet, by where it is in Services; a part added later that takes one is not in this table and fails the test below until it is put in it, with a test of its own in tests/test_internet_services.py
TAKERS = {
    "packetlog": {"append"}, "stationbook": {"take"}, "weatherlog": {"take"},                                   # SEEN_BY_ALL
    "messaging": {"on_packet", "echoed"}, "messaging.inbox": {"on_packet"}, "messaging.delivery": {"heard"},     # ON_AIR_ONLY: messaging and what it hands the packet to
    "queries": {"on_packet"}, "ownobjects": {"on_packet"}, "igate": {"on_packet"}, "digipeater": {"on_packet"},
    "qru": {"heard"}, "bulletins": {"heard"},                                                                    # (handed a message by the inbox)
}


def test_every_part_that_takes_a_packet_is_known_and_the_ones_that_act_refuse_what_is_from_the_internet(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    found = packet_takers(e)
    assert found == TAKERS, "a part takes a packet that this test does not know: the gate must say who sees an internet packet"
    assert set(TAKERS) - set(SEEN_BY_ALL) >= set(ON_AIR_ONLY)
    for part in TAKERS:
        for method in TAKERS[part]:
            if part in SEEN_BY_ALL:
                continue
            source = inspect.getsource(getattr(_resolve(e, part), method))
            assert "on_air" in source or "GATEABLE" in source or "inbox.on_packet" in source or "self.delivery.heard" in source, f"{part}.{method} does not look at Packet.on_air or GATEABLE"


def _resolve(e: Env, label: str) -> Any:
    first, *rest = label.split(".")
    part = getattr(e.ctl, first)
    for name in rest:
        part = getattr(part, name)
    return part


def test_the_connection_to_aprs_is_has_one_outlet_for_what_it_reads_and_it_is_the_gate(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    assert e.ctl.aprsis.heard._handlers == [e.ctl.hear_internet], "what the connection reads goes to the one gate and to nothing else"
    assert all(owner(e, h) != "aprsis" for h in e.ctl.tnc.packet._handlers), "(and nothing of the connection is connected to the radio's signal)"
    readers = [(name, value) for name, value in vars(e.ctl.aprsis).items() if hasattr(value, "emit") and name != "heard"]
    assert [name for name, _ in readers] == ["state_changed", "changed"], "the connection's other signals carry no packet"
    taken = packet_takers(e)
    assert "aprsis" not in taken, "(no method of the connection takes a packet: it only makes them, from the lines of the server)"


def test_hear_internet_takes_a_packet_from_the_internet_only(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    taken: list[Packet] = []
    e.ctl.internet_packet.connect(taken.append)
    packet = from_internet("OH2ABC", POSITION, e.now())
    e.ctl.hear_internet(packet)
    assert taken == [packet] and packet.via == IS
    with pytest.raises(ValueError, match="only a packet received from the internet"):
        e.ctl.hear_internet(replace(packet, via="rf"))
    assert taken == [packet]


def test_a_packet_from_the_internet_that_is_handed_to_the_radios_signal_is_refused_by_every_part_that_acts(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = Env(tmp_path, radio=False)
    reached: list[str] = []
    for handler in e.ctl.tnc.packet._handlers:
        if isinstance(handler, AirOnly):
            name = owner(e, handler)
            handler.handler = lambda packet, name=name: reached.append(name)           # type: ignore[misc]
    packet = from_internet("OH2ABC", POSITION, e.now())
    with caplog.at_level(logging.WARNING, logger="neoaprs.wiring"):
        e.ctl.tnc.packet.emit(packet)
        e.ctl.tnc.packet.emit(packet)
    assert reached == [], "no part that acts saw it"
    assert [h.refused for h in e.ctl.tnc.packet._handlers if isinstance(h, AirOnly)] == [2] * len(ON_AIR_ONLY)
    assert len([r for r in caplog.records if "from the internet was handed" in r.getMessage()]) == len(ON_AIR_ONLY), "said once for each"
    e.ctl.tnc.packet.emit(replace(packet, via="rf"))
    assert reached == list(ON_AIR_ONLY), "a packet of the radio reaches them, in order"
    assert e.ctl.stationbook.get("OH2ABC") is not None, "the book took both"


async def test_a_whole_daemon_handed_packets_from_the_internet_that_ask_for_everything_transmits_nothing_and_keeps_what_it_may(tmp_path: Path) -> None:
    e = Env(tmp_path, settings={"digi/enabled": "true"})
    await e.start()
    await e.until_usable()
    now = e.now()
    ours = e.ctl.config.station_call
    asks = [
        from_internet("OH2RDG-7", message_info(ours, "Moi!", "12"), now),                           # a message to us: kept and acked if it were heard
        from_internet("OH2RDG-7", message_info(ours, "?APRSP"), now),                               # a query to us: answered if it were heard
        from_internet("OH2RDG-7", message_info(ours, "?APRSD"), now),
        from_internet("OH2RDG-7", b"?APRS?", now),                                                  # the general query
        from_internet("OH2RDG-7", message_info("BLN1", "Road closed"), now),                        # a bulletin: the message board is for the radio
        from_internet("OH2RDG-7", message_info("QRU", "INFO"), now),
        from_internet("OH2RDG-7", b"!6010.00N/02456.00E-repeat me", now, path="WIDE1-1,qAR,OH2RDK-1"),     # a packet to be repeated by the fill-in digipeater
    ]
    for packet in asks:
        e.ctl.hear_internet(packet)
    e.ctl.hear_internet(from_internet("N0WX", b"_10090556c220s004g005t077r000p000P000h50b09720", now))
    await e.settled()
    await idle_for(0.3)
    assert await e.heard(1, timeout_sec=0.3) == b"", "nothing was transmitted: no ack, no answer, no repeat"
    assert e.ctl.messaging.records() == [] and e.ctl.bulletins.records() == []
    assert e.ctl.digipeater._seen == {} and e.ctl.queries._general_until is None
    book = e.ctl.stationbook.get("OH2RDG-7")
    assert book is not None and (book.heard_is, book.heard_rf, book.heard_rf_gated, book.internet_only, book.can_message) == (len(asks), 0, 0, True, False)
    assert len(await e.packets()) == len(asks) + 1 and {p.via for p in await e.packets()} == {IS}, "the packet log kept them all, as from the internet"
    assert await e.ctl.weatherlog.latest("N0WX") is not None, "the weather log took the observation"
    assert e.ctl.aloha.radius_km is None and e.ctl.stationbook.me is not None
    # the same packets on the radio are what they would have been: the control that shows the test could see a transmission
    e.feed(on_air("OH2RDG-7", message_info(ours, "Moi!", "12"), path=""))
    [ack] = await said(e, 1)
    assert ack.info.startswith(b":OH2RDG-7 :ack12")
    await e.stop()


@pytest.mark.parametrize("passcode", ["19628", ""])
async def test_a_whole_daemon_whose_connection_reads_packets_that_ask_for_everything_transmits_nothing_and_keeps_what_it_may(tmp_path: Path, passcode: str) -> None:
    server = await fake_aprsis(verified=bool(passcode))
    e = Env(tmp_path, settings={"digi/enabled": "true", "igate/enabled": "true", "igate/server": server.address, "igate/password": passcode})
    await e.start()
    await e.until_usable()
    await until(lambda: e.ctl.igate.state == ("connected" if passcode else "listening"))
    ours = e.ctl.config.station_call
    path = "TCPIP*,qAC,T2TEST"
    asks = [
        (message_info(ours, "Moi!", "12"), path),                                                    # a message to us: kept and acked if it were heard
        (message_info(ours, "?APRSP"), path),                                                        # a query to us: answered if it were heard
        (message_info(ours, "?APRSD"), path),
        (b"?APRS?", path),                                                                           # the general query
        (message_info("BLN1", "Road closed"), path),                                                 # a bulletin: the message board is for the radio
        (message_info("QRU", "INFO"), path),
        (b"!6010.00N/02456.00E-repeat me", "WIDE1-1,qAR,OH2RDK-1"),                                  # a packet to be repeated by the fill-in digipeater
    ]
    for info, via in asks:
        server.send(f"OH2RDG-7>APRS,{via}:".encode() + info)
    server.send(b"N0WX>APRS,TCPIP*,qAC,T2TEST:_10090556c220s004g005t077r000p000P000h50b09720")
    await until(lambda: e.ctl.aprsis.read == len(asks) + 1)
    await e.settled()
    await idle_for(0.3)
    assert await e.heard(1, timeout_sec=0.3) == b"", "nothing was transmitted: no ack, no answer, no repeat"
    assert e.ctl.messaging.records() == [] and e.ctl.bulletins.records() == []
    assert e.ctl.digipeater._seen == {} and e.ctl.queries._general_until is None
    book = e.ctl.stationbook.get("OH2RDG-7")
    assert book is not None and (book.heard_is, book.heard_rf, book.internet_only, book.can_message) == (len(asks), 0, True, False)
    assert {p.via for p in await e.packets()} == {IS}, "the packet log kept them all, as from the internet"
    assert await e.ctl.weatherlog.latest("N0WX") is not None
    assert e.ctl.igate.gated == 0 and not e.ctl.igate.dropped, "none of it reached the iGate"
    assert [line for line in server.packets if not line.startswith(f"{ours}>")] == [], "and nothing of it went back to the server"
    await e.stop()


async def test_the_page_is_told_the_packets_from_the_internet_and_the_stations_they_make(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: "packets" in page.topics and "stations" in page.topics)
    e.ctl.hear_internet(from_internet("OH2ABC", POSITION, e.now()))
    await until(lambda: len(page.topics["packets"]) == 1 and "OH2ABC" in page.topics["stations"])
    [row] = page.topics["packets"].values()
    assert (row["via"], row["gate"], row["route"], row["path"], row["source"]) == ("is", "", "", ["TCPIP*", "qAC", "T2FINLAND"], "OH2ABC")
    station = page.topics["stations"]["OH2ABC"]
    assert (station["heard_is"], station["heard_rf"], station["heard_rf_gated"], station["position_via"], station["can_message"], station["last_route"]) == (1, 0, 0, "is", False, "")
    await e.stop()


async def test_a_restart_finds_the_stations_by_channel_and_the_routes_only_of_the_radio(tmp_path: Path) -> None:
    first = Env(tmp_path)
    await first.start()
    await first.play()
    first.ctl.hear_internet(from_internet("OH2RDG", b">also on the net", first.now()))
    first.ctl.hear_internet(from_internet("OH2NET", POSITION, first.now()))
    await first.settled()
    await first.stop()
    second = Env(tmp_path)
    await second.start()
    book = second.ctl.stationbook
    rdg, net = book.get("OH2RDG"), book.get("OH2NET")
    assert rdg is not None and net is not None
    assert (rdg.heard_rf, rdg.heard_is, rdg.internet_only, rdg.last_is_at is not None, rdg.last_rf_at is not None, rdg.position_via) == (1, 1, False, True, True, "rf")
    assert (net.heard_rf, net.heard_is, net.internet_only, net.position_via, net.can_message, net.deliveries.by_route, net.last_path) == (0, 1, True, "is", False, {}, ())
    assert rdg.deliveries.direct + sum(rdg.deliveries.by_route.values()) == 1, "the routes were counted again from the packets of the radio; the one of the internet is none"
    assert len([p for p in await second.packets() if p.via == IS]) == 2
    await second.stop()


async def test_the_dummy_radios_packets_go_everywhere_the_radios_do_and_are_not_gateable(tmp_path: Path) -> None:
    e = Env(tmp_path)
    e.tnc.dummy = True
    await e.start()
    await e.until_usable()
    ours = e.ctl.config.station_call
    e.feed(on_air("QDUMMY-1", message_info(ours, "Moi!", "12"), path=""))
    e.feed(on_air("QDUMMY-2", b"=6012.34N/02456.78E-made up", path="WIDE1*"))
    [ack] = await said(e, 1)
    assert ack.info.startswith(b":QDUMMY-1 :ack12"), "messaging works with the Dummy radio"
    await until(lambda: e.ctl.stationbook.get("QDUMMY-2") is not None)
    first, second = e.ctl.stationbook.get("QDUMMY-1"), e.ctl.stationbook.get("QDUMMY-2")
    assert first is not None and second is not None
    assert (first.heard_dummy, first.heard_rf, first.internet_only, first.last_dummy_at is not None, first.can_message) == (1, 0, False, True, True)
    assert (second.position_via, second.last_path, second.heard_dummy) == ("dummy", ("WIDE1*",), 1) and second.last_on_air_at is not None and second.deliveries.by_route == {("?",): 1}
    assert [r.text for r in e.ctl.messaging.records()] == ["Moi!"]
    packets = await e.packets()
    assert {p.via for p in packets if p.direction == "in"} == {"dummy"}
    assert {p.via for p in packets if p.direction == "out"} == {"dummy"}, "what a Dummy radio sends is its own: it never reaches a real one"
    assert all(p.via not in GATEABLE for p in packets)
    await e.stop()
    again = Env(tmp_path)
    await again.start()
    back = again.ctl.stationbook.get("QDUMMY-1")
    assert back is not None and (back.heard_dummy, back.packets, back.last_dummy_at is not None) == (1, 1, True)
    await again.stop()


def test_what_may_be_gated_is_what_was_on_the_air_and_nothing_made_up_or_from_the_internet() -> None:
    assert GATEABLE == {"rf", "rf-gated"} and not GATEABLE & {"is", "dummy"}
    assert "is" in VIAS and "dummy" in VIAS and set(VIAS) - GATEABLE == {"is", "dummy"}
