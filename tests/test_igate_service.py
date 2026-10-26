"""The receive-only iGate service (neoaprs/services/igate.py) on a fake APRS-IS: what the radio hears becomes lines on the server, each not gated is counted by its reason, a copy within 30 seconds is gated once, nothing is
gated while it is not logged in, our own position goes to the server, the log has the packets and the hour and never the password, and nothing the server says goes anywhere."""
import logging
from dataclasses import replace

import pytest

from neoaprs import TOCALL
from neoaprs.aprsis import NO_PASSWORD, UNVERIFIED
from neoaprs.igaterules import DUPLICATE, NOGATE, NOT_AIR, OFFLINE, OWN, QUERY, SOURCE, TCPIP
from tests.support.env import idle_for, until
from tests.support.fakeaprsis import fake_aprsis
from tests.support.igateworld import POSITION, frame_of, iworld

LINE = "OH2XYZ-9>APZ123,WIDE1-1*,WIDE2-1,qAO,OH2GBA-10:!6010.00N/02456.00E>Test"
OWN_LINE = "OH2GBA-10>" + TOCALL + ",TCPIP*:" + POSITION.decode()


# ---- gating

async def test_what_the_radio_hears_is_on_the_server_as_a_line_with_qao_and_our_call() -> None:
    server = await fake_aprsis()
    w = await iworld(server)
    w.hear()
    await w.until_sent(2)
    assert LINE in server.packets and w.igate.gated == 1 and w.igate.last_gated_at == w.clock() and not w.igate.dropped
    assert w.igate.state == "connected" and w.igate.problem == "" and w.igate.server_name == server.name


async def test_every_rule_counts_what_it_kept_off_the_server_by_its_reason() -> None:
    server = await fake_aprsis()
    w = await iworld(server)
    for kwargs in ({"path": "TCPIP*"}, {"path": "WIDE1*,TCPXX"}, {"path": "NOGATE"}, {"path": "RFONLY"}, {"info": b"?APRS?"}, {"source": "N0CALL"}, {"source": "OH2GBA-10"}, {"info": b"}OH7ABC>APRS,TCPIP,OH7JHF-1*:>x", "source": "OH7JHF-1"}):
        w.hear(**kwargs)                                                  # type: ignore[arg-type]
    w.hear(direction="out")
    assert dict(w.igate.dropped) == {TCPIP: 3, NOGATE: 2, QUERY: 1, SOURCE: 1, OWN: 1} and w.igate.gated == 0
    await w.until_sent(1)
    assert server.packets == [OWN_LINE], "(only our own position: none of the nine packets)"


async def test_a_packet_from_the_internet_or_made_up_by_the_dummy_radio_is_never_gated_and_is_counted_as_not_from_the_air() -> None:
    server = await fake_aprsis()
    w = await iworld(server)
    heard = w.hear()                                                      # (a real one, gated: the control)
    w.igate.on_packet(replace(heard, via="is"))
    w.igate.on_packet(replace(heard, via="dummy"))
    w.igate.on_packet(replace(heard, via="dummy", info=b"!6011.00N/02456.00E>Other"))
    assert w.igate.gated == 1 and w.igate.dropped[NOT_AIR] == 3 and dict(w.igate.dropped) == {NOT_AIR: 3}
    await w.until_sent(2)
    await idle_for(0.1)
    assert sorted(server.packets) == sorted([LINE, OWN_LINE]), "(only the real packet and our own position reached the server)"


async def test_a_packet_that_was_not_on_the_air_is_not_from_the_air_even_when_the_igate_is_not_logged_in() -> None:
    server = await fake_aprsis(answer=False)
    w = await iworld(server, wait=False)
    w.igate.on_packet(replace(w.hear(), via="is"))
    assert dict(w.igate.dropped) == {OFFLINE: 1, NOT_AIR: 1}


async def test_a_third_party_packet_without_the_internet_in_it_is_gated_as_the_packet_inside() -> None:
    server = await fake_aprsis()
    w = await iworld(server)
    w.hear(source="OH7JHF-1", path="WIDE2-1", info=b"}OH2XYZ-9>APZ123,WIDE1-1*:!6010.00N/02456.00E>Test")
    await until(lambda: "OH2XYZ-9>APZ123,WIDE1-1*,qAO,OH2GBA-10:!6010.00N/02456.00E>Test" in server.packets)


async def test_the_same_packet_heard_again_within_30_seconds_is_gated_once_and_after_30_seconds_again() -> None:
    server = await fake_aprsis()
    w = await iworld(server)
    w.hear(path="WIDE1-1*,WIDE2-1")
    w.clock.advance(5)
    w.hear(path="OH2RDG*,WIDE2-1")                                        # (the path is not part of it)
    w.clock.advance(24)
    w.hear(destination="APZ123-2")                                        # (nor is the destination's SSID)
    assert w.igate.gated == 1 and w.igate.dropped[DUPLICATE] == 2
    w.clock.advance(2)                                                    # (31 s after the first)
    w.hear()
    assert w.igate.gated == 2 and w.igate.dropped[DUPLICATE] == 2
    w.hear(info=b"!6010.00N/02456.00E>Other")
    assert w.igate.gated == 3


async def test_the_duplicate_window_is_a_number_that_can_be_set_to_nothing() -> None:
    server = await fake_aprsis()
    w = await iworld(server)
    w.igate.duplicate_sec = 0.0
    w.hear()
    w.hear()
    assert w.igate.gated == 2 and DUPLICATE not in w.igate.dropped


async def test_a_packet_heard_while_the_igate_is_not_logged_in_is_counted_and_not_queued() -> None:
    server = await fake_aprsis(answer=False)
    w = await iworld(server, wait=False)
    w.hear()
    assert w.igate.dropped[OFFLINE] == 1 and w.igate.gated == 0 and w.igate.state == "connecting"
    await idle_for(0.1)
    assert server.packets == []


async def test_the_igate_that_is_off_connects_to_nothing_and_counts_nothing() -> None:
    server = await fake_aprsis()
    w = await iworld(server, wait=False, igate_enabled=False)
    w.hear()
    await idle_for(0.2)
    assert w.igate.state == "off" and w.igate.problem == "" and server.connections == 0 and w.igate.gated == 0 and not w.igate.dropped


async def test_what_the_server_sends_goes_nowhere() -> None:
    server = await fake_aprsis()
    w = await iworld(server)
    server.send(b"OH2XYZ>APRS::OH2GBA-10 :hello{1}")
    server.send(b"OH7ABC>APRS,TCPIP*,qAC,T2TEST:=6010.00N/02456.00E-")
    await idle_for(0.2)
    assert w.igate.gated == 0 and not w.igate.dropped and w.link.verified


# ---- the state

async def test_an_igate_without_a_password_waits_and_says_what_it_needs() -> None:
    server = await fake_aprsis()
    w = await iworld(server, wait=False, igate_password="")
    await until(lambda: w.igate.problem == NO_PASSWORD)
    assert w.igate.state == "connecting"
    w.hear()
    assert w.igate.dropped[OFFLINE] == 1 and server.connections == 0
    w.save(igate_password="19628")
    await until(lambda: w.igate.state == "connected")
    assert w.igate.problem == "" and server.connections == 1


async def test_an_igate_without_a_call_waits_and_says_so() -> None:
    server = await fake_aprsis()
    w = await iworld(server, wait=False, station_call="")
    await until(lambda: "call" in w.igate.problem)
    assert w.igate.state == "connecting" and server.connections == 0


async def test_a_password_the_server_does_not_accept_is_unverified_and_gates_nothing() -> None:
    server = await fake_aprsis(verified=False)
    w = await iworld(server, wait=False)
    await until(lambda: w.igate.state == "unverified")
    assert w.igate.problem == UNVERIFIED
    w.hear()
    await idle_for(0.2)
    assert server.packets == [] and w.igate.gated == 0 and server.connections == 1


async def test_a_new_password_logs_in_again_and_the_switch_disconnects() -> None:
    server = await fake_aprsis()
    w = await iworld(server)
    w.save(igate_password="12345")
    await until(lambda: len(server.logins) == 2)
    assert "pass 12345" in server.logins[1]
    await until(lambda: w.igate.state == "connected")
    w.save(igate_enabled=False)
    await until(lambda: w.igate.state == "off" and not w.link.verified)
    w.hear()
    assert w.igate.gated == 0
    w.save(igate_enabled=True)
    await until(lambda: w.igate.state == "connected")


async def test_the_connection_lost_and_made_again_gates_again() -> None:
    server = await fake_aprsis()
    w = await iworld(server)
    server.hang_up()
    await until(lambda: w.igate.state == "connecting")
    w.hear()
    assert w.igate.dropped[OFFLINE] == 1
    await until(lambda: w.igate.state == "connected")
    w.clock.advance(60)
    w.hear(info=b"!6010.00N/02456.00E>After")
    await until(lambda: any(line.endswith(">After") for line in server.packets))


# ---- our own position

async def test_the_position_of_a_station_that_stays_goes_to_the_server_at_the_login_and_every_30_minutes() -> None:
    server = await fake_aprsis()
    w = await iworld(server)
    await until(lambda: server.packets == [OWN_LINE])
    w.clock.advance(29 * 60)
    w.igate.tick()
    await idle_for(0.1)
    assert server.packets == [OWN_LINE]
    w.clock.advance(61)
    w.igate.tick()
    await until(lambda: len(server.packets) == 2)
    assert server.packets == [OWN_LINE, OWN_LINE]


async def test_a_station_without_a_position_sends_none_and_tries_again_when_it_has_one() -> None:
    server = await fake_aprsis()
    w = await iworld(server, wait=False)
    w.position_info = None
    await until(lambda: w.igate.state == "connected")
    await idle_for(0.1)
    assert server.packets == []
    w.position_info = POSITION
    w.clock.advance(61)
    w.igate.tick()
    await until(lambda: server.packets == [OWN_LINE])


async def test_a_moving_station_sends_the_beacons_that_go_on_the_radio_at_most_once_a_minute() -> None:
    server = await fake_aprsis()
    w = await iworld(server, gps_source="gpsd")
    await idle_for(0.1)
    assert server.packets == [], "(a moving station sends its position when it beacons, not at the login)"
    beacon = frame_of(source="OH2GBA-10", destination=TOCALL, path="WIDE1-1,WIDE2-1", info=b"=/5L!!<*e7>7P[")
    w.igate.beacon_sent(beacon)
    await until(lambda: server.packets == [f"OH2GBA-10>{TOCALL},TCPIP*:=/5L!!<*e7>7P["])
    w.clock.advance(30)
    w.igate.beacon_sent(beacon)
    await idle_for(0.1)
    assert len(server.packets) == 1
    w.clock.advance(31)
    w.igate.beacon_sent(beacon)
    await until(lambda: len(server.packets) == 2)
    w.igate.tick()
    w.clock.advance(3600)
    w.igate.tick()
    await idle_for(0.1)
    assert len(server.packets) == 2, "(a moving station has no timer of its own)"


async def test_a_beacon_is_not_sent_to_the_server_while_the_igate_is_not_logged_in_or_the_station_stays() -> None:
    server = await fake_aprsis(answer=False)
    w = await iworld(server, wait=False, gps_source="gpsd")
    w.igate.beacon_sent(frame_of(source="OH2GBA-10", info=b"=x"))
    w.save(gps_source="off")
    w.igate.beacon_sent(frame_of(source="OH2GBA-10", info=b"=x"))
    await idle_for(0.1)
    assert server.packets == []


# ---- the log

async def test_the_log_has_the_login_and_each_gated_packet_and_never_the_password(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    server = await fake_aprsis()
    w = await iworld(server, igate_password="31415")
    w.hear()
    await w.until_sent(2)
    w.save(igate_password="27182")
    await until(lambda: len(server.logins) == 2)
    await w.igate.stop()
    assert "31415" not in caplog.text and "27182" not in caplog.text
    text = caplog.text
    assert "igate: on, a receive-only iGate; logging in to 127.0.0.1" in text and "as OH2GBA-10" in text
    assert any(r.levelno == logging.INFO and "logged in as OH2GBA-10, verified" in r.message for r in caplog.records)
    assert any(r.levelno == logging.DEBUG and r.message == f"igate: gated {LINE}" for r in caplog.records)
    assert any(r.levelno == logging.INFO and "connected to 127.0.0.1" in r.message for r in caplog.records)


async def test_the_hour_is_one_line_at_info_with_what_was_not_gated(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    server = await fake_aprsis()
    w = await iworld(server)
    for n in range(3):
        w.hear(info=b"!6010.00N/02456.00E>" + str(n).encode())
    for _ in range(5):
        w.hear(path="TCPIP*")
    w.clock.advance(1)
    w.hear(info=b"!6010.00N/02456.00E>0")
    w.hear(info=b"!6010.00N/02456.00E>1")
    w.hear(info=b"?APRS?")
    said = "igate: 3 packets gated in the last hour, 8 not gated: 5 TCPIP, 2 duplicate, 1 query"
    assert w.igate.summary() == said
    w.clock.advance(3598)
    w.igate.tick()
    assert said not in caplog.text, "(not before the hour is over)"
    w.clock.advance(1)
    w.igate.tick()
    assert [(r.levelno, r.message) for r in caplog.records if r.message.startswith("igate: 3 packets")] == [(logging.INFO, said)]
    assert w.igate.summary() == "igate: 0 packets gated in the last hour", "(the next hour starts from nothing, the totals go on)"
    assert w.igate.gated == 3 and w.igate.dropped[TCPIP] == 5
    w.hear(info=b"!6010.00N/02456.00E>9")
    assert w.igate.summary() == "igate: 1 packet gated in the last hour"


# ---- the structure

def test_the_service_has_no_radio_to_send_with() -> None:
    import inspect

    import neoaprs.services.igate as module
    source = inspect.getsource(module)
    imported = {line.split()[1] for line in source.splitlines() if line.startswith(("from ", "import "))}
    assert not {name for name in imported if name.startswith(("neoaprs.tnc", "neoaprs.kiss", "neoaprs.serialport", "neoaprs.interlock", "neoaprs.services.sender", "neoaprs.services.digipeater", "neoaprs.services.beacon"))}
    assert not {name for name in vars(module) if name in ("Tnc", "Radio", "Sender", "Interlock", "Digipeater", "Beacon")}
    assert "send_frame" not in source


async def test_the_igate_and_its_connection_hold_nothing_that_can_send_a_frame() -> None:
    server = await fake_aprsis()
    w = await iworld(server)
    for part in (w.igate, w.link):
        for name, value in vars(part).items():
            assert not hasattr(value, "send_frame"), f"{type(part).__name__}.{name} can send a frame"
