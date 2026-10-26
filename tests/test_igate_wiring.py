"""The iGate inside the whole daemon: the radio a fake TNC, APRS-IS a fake server, both on the loopback. A capture of the radio played into the daemon becomes lines on the server, every packet heard is gated or
counted, the settings from the page switch it on and off, the page is told by the topic `igate`, what the server sends becomes stations of the internet in the book and the log, and nothing of it ever reaches the radio.
Without a passcode the daemon only listens: it logs in read-only, gates nothing and sends no position, and the stations of the internet come all the same."""
import re
from pathlib import Path

import pytest

from neoaprs import PROGRAM, TOCALL, VERSION
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.air import message_info, on_air
from tests.support.env import CAPTURE, Env, idle_for, until
from tests.support.fakeaprsis import FakeAprsIs, fake_aprsis

LINE = re.compile(r"^[A-Z0-9-]+>[^,:]+(,[^,:]+)*,qAO,OH2GBA:.+$")
PASSWORD = "19628"
FILTER = "r/60.17/24.94/150"                       # (the circle of 150 km round the station of the test, 60.1695 N 24.94 E)


def igate_settings(server: FakeAprsIs) -> dict[str, str]:
    return {"igate/enabled": "true", "igate/server": server.address, "igate/password": PASSWORD}


async def started(tmp_path: Path, server: FakeAprsIs, **options: object) -> Env:
    e = Env(tmp_path, settings=igate_settings(server), **options)                # type: ignore[arg-type]
    await e.start()
    await e.until_usable()
    await until(lambda: e.ctl.igate.state == "connected")
    return e


async def test_a_capture_played_into_the_daemon_is_on_the_server_and_every_packet_is_accounted_for(tmp_path: Path) -> None:
    server = await fake_aprsis()
    e = await started(tmp_path, server)
    frames = await e.play(CAPTURE)
    igate = e.ctl.igate
    await until(lambda: len(server.packets) == frames + 1)                            # (the four packets of the capture and our own position)
    assert frames == 4 and igate.gated == 4 and not igate.dropped, "(each packet heard is gated or counted by its reason)"
    gated = [line for line in server.packets if not line.startswith(f"OH2GBA>{TOCALL},")]
    assert gated == [
        "OH2RDG>APN391,OH2RCH-2*,TRACE2-1,qAO,OH2GBA:!6007.47NN02429.82E#PHG8470/R,W,T,Wn,Tn Kirkkonummi oh1gsm@sral.fi",
        "OH2RDK-7>APRX29,OH2RCH-2*,TRACE2-1,qAO,OH2GBA:!6009.90NT02456.80E&432.500 MHz",
        "OH2RDS>APN391,OH2RCH-2*,qAO,OH2GBA:!6016.66NN02515.26E#PHG8470/R,W,T,Wn,Tn Sipoo oh1gsm@sral.fi",
        "OH2PU-9>APOTC1,OH2RCH-2*,qAO,OH2GBA:!/0&m]TbwX>z!GQRV D-STAR 144.650MHz"]
    assert all(LINE.match(line) for line in gated)
    assert server.logins == [f"user OH2GBA pass {PASSWORD} vers {PROGRAM} {VERSION} filter {FILTER}"]
    await e.play(CAPTURE)                                                             # (the same four again, at once: the duplicates of a minute ago are not sent twice)
    assert igate.gated == 4 and igate.dropped["duplicate"] == 4
    await e.stop()


async def test_the_position_of_the_station_is_on_the_server_with_tcpip_as_its_only_path(tmp_path: Path) -> None:
    server = await fake_aprsis()
    e = await started(tmp_path, server)
    await until(lambda: any(line.startswith(f"OH2GBA>{TOCALL},TCPIP*:=6010.") for line in server.packets))
    [own] = [line for line in server.packets if line.startswith(f"OH2GBA>{TOCALL},")]
    assert own == f"OH2GBA>{TOCALL},TCPIP*:=6010.17N/02456.40E-NeoAPRS" or own.startswith(f"OH2GBA>{TOCALL},TCPIP*:=60")
    await e.stop()


async def test_what_the_server_sends_is_stations_of_the_internet_and_nothing_of_it_reaches_the_radio_or_is_gated_back(tmp_path: Path) -> None:
    server = await fake_aprsis()
    e = await started(tmp_path, server)
    await e.play(CAPTURE)
    await e.heard(1, 0.3)                                                             # (what the daemon wrote to the radio so far, taken out)
    before_packets, before_heard, before_sent = e.tnc.stats.packets, len(await e.packets()), list(server.packets)
    server.send(b"OH2XYZ>APRS,TCPIP*,qAC,TESTSRV::OH2GBA   :hello from the internet{1}")
    server.send(b"OH2XYZ>APRS,TCPIP*,qAC,TESTSRV:!6010.00N/02456.00E-internet")
    server.send(b"OH2XYZ>APRS,TCPIP*,qAC,TESTSRV::BLN1     :a bulletin")
    server.send(b"# aprsc 2.1.19 keepalive")
    server.send(b"this is no packet")
    await until(lambda: e.ctl.aprsis.read == 3 and e.ctl.aprsis.unreadable == 1)
    await e.settled()
    await idle_for(0.4)
    assert await e.heard(1, 0.3) == b"", "(no ack, no answer, no copy: the radio was written nothing)"
    assert e.tnc.stats.packets == before_packets
    assert e.ctl.messaging.records() == [] and e.ctl.bulletins.records() == []
    xyz = e.ctl.stationbook.get("OH2XYZ")
    assert xyz is not None and (xyz.heard_is, xyz.heard_rf, xyz.internet_only, xyz.can_message) == (3, 0, True, False)
    packets = await e.packets()
    assert len(packets) == before_heard + 3 and sorted(p.via for p in packets) == ["is"] * 3 + ["rf"] * before_heard, "(the log kept them, as from the internet)"
    assert server.packets == before_sent and e.ctl.igate.gated == 4, "(nothing of the internet was gated back to it)"
    await e.stop()


async def test_without_a_passcode_the_daemon_logs_in_read_only_gates_nothing_sends_no_position_and_shows_the_stations_of_the_internet(tmp_path: Path) -> None:
    server = await fake_aprsis(verified=False)
    e = Env(tmp_path, settings={**igate_settings(server), "igate/password": ""})
    await e.start()
    await e.until_usable()
    await until(lambda: e.ctl.igate.state == "listening")
    assert server.logins == [f"user OH2GBA pass -1 vers {PROGRAM} {VERSION} filter {FILTER}"]
    frames = await e.play(CAPTURE)
    server.send(b"OH2ABC>APRS,TCPIP*,qAC,TESTSRV:!6010.50N/02457.00E-internet station")
    server.send(b"OH2ABD-9>APRS,OH2RCH*,qAR,OH2RDK-7:!6011.50N/02458.00E>heard by an iGate")
    await until(lambda: e.ctl.stationbook.get("OH2ABD-9") is not None)
    await idle_for(0.3)
    abc, abd = e.ctl.stationbook.get("OH2ABC"), e.ctl.stationbook.get("OH2ABD-9")
    assert abc is not None and abd is not None and (abc.heard_is, abc.internet_only, abd.heard_is) == (1, True, 1)
    assert frames == 4 and e.ctl.stationbook.get("OH2RDG") is not None, "(the radio's stations are there too)"
    assert server.packets == [] and e.ctl.igate.gated == 0 and not e.ctl.igate.dropped, "(read only: nothing gated, no position sent)"
    assert await e.heard(1, 0.3) == b"", "(and nothing written to the radio)"
    await e.stop()


async def test_a_passcode_the_server_refuses_leaves_the_daemon_listening_and_the_stations_of_the_internet_come(tmp_path: Path) -> None:
    server = await fake_aprsis(verified=False)
    e = Env(tmp_path, settings=igate_settings(server))
    await e.start()
    await e.until_usable()
    await until(lambda: e.ctl.igate.state == "unverified")
    server.send(b"OH2ABC>APRS,TCPIP*,qAC,TESTSRV:!6010.50N/02457.00E-internet station")
    await until(lambda: e.ctl.stationbook.get("OH2ABC") is not None)
    assert server.connections == 1 and server.packets == [] and e.ctl.igate.problem == "the server did not accept the password"
    await e.stop()


async def test_a_packet_heard_on_the_radio_is_gated_and_nothing_of_it_is_answered_on_the_radio(tmp_path: Path) -> None:
    server = await fake_aprsis()
    e = await started(tmp_path, server)
    await e.heard(1, 0.3)
    e.feed(on_air("OH2RDG-7", b"!6010.00N/02456.00E>hello", path="WIDE1-1,WIDE2-1"))
    await until(lambda: "OH2RDG-7>APRS,WIDE1-1,WIDE2-1,qAO,OH2GBA:!6010.00N/02456.00E>hello" in server.packets)
    e.feed(on_air("OH2RDG-7", message_info("OH7XYZ", "not for us", "3")))              # (a message to somebody else: gated, not answered)
    await until(lambda: any(":OH7XYZ   :not for us{3" in line for line in server.packets))
    assert await e.heard(1, 0.3) == b""
    await e.stop()


async def test_the_igate_is_off_until_the_operator_turns_it_on_and_the_settings_from_the_page_switch_it(tmp_path: Path) -> None:
    server = await fake_aprsis()
    e = Env(tmp_path, web=True)
    await e.start()
    await e.until_usable()
    assert e.ctl.igate.state == "off" and server.connections == 0
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    assert page.topics["igate"] == {"enabled": False, "state": "off", "server": "", "problem": "", "gated": 0, "dropped": {}, "last_gated_at": None}
    values = page.topics["config"]["values"]
    assert values["igate/enabled"] == "false" and values["igate/server"] == "rotate.aprs2.net:14580" and values["igate/password"] == ""
    await page.send({"cmd": "set_config", "values": igate_settings(server)})
    await page.until(lambda: page.topics["igate"]["state"] == "connected")
    assert page.topics["igate"]["server"] == server.name and page.topics["igate"]["problem"] == "" and page.topics["igate"]["enabled"] is True
    e.feed(on_air("OH2RDG-7", b"!6010.00N/02456.00E>x"))
    e.feed(on_air("OH2RDG-8", b"!6010.00N/02456.00E>y", path="TCPIP*"))
    await page.until(lambda: page.topics["igate"]["gated"] == 1 and page.topics["igate"]["dropped"] == {"tcpip": 1})
    assert page.topics["igate"]["last_gated_at"] is not None
    await page.send({"cmd": "set_config", "values": {"igate/enabled": "false"}})
    await page.until(lambda: page.topics["igate"]["state"] == "off")
    await until(lambda: not e.ctl.aprsis.verified)
    await e.stop()


async def test_a_password_that_is_not_a_passcode_and_the_read_only_one_are_refused_by_the_page_command(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    for text in ("-1", "abc", "40000", "12 34"):
        await page.send({"cmd": "set_config", "values": {"igate/password": text}})
        error = await page.expect("error")
        assert error["text"].startswith("set_config: igate/password: ") and error["key"] == "igate/password", error
    assert error["code"] == "setting.not_passcode"
    await page.send({"cmd": "set_config", "values": {"igate/password": "-1"}})
    assert (await page.expect("error"))["code"] == "setting.passcode_read_only"
    await page.send({"cmd": "set_config", "values": {"igate/password": "00123"}})
    await page.until(lambda: page.topics["config"]["values"]["igate/password"] == "123")
    await e.stop()


@pytest.mark.parametrize("verified", [False])
async def test_a_password_the_server_does_not_accept_is_told_to_the_page(tmp_path: Path, verified: bool) -> None:
    server = await fake_aprsis(verified=verified)
    e = Env(tmp_path, web=True, settings=igate_settings(server))
    await e.start()
    page = await e.ws()
    await page.until(lambda: page.topics.get("igate", {}).get("state") == "unverified")
    assert page.topics["igate"]["problem"] == "the server did not accept the password"
    e.feed(on_air("OH2RDG-7", b"!6010.00N/02456.00E>x"))
    await idle_for(0.3)
    assert server.packets == []
    await e.stop()
