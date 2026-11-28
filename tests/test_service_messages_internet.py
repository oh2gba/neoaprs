"""Messages to the listed internet services (OTA, ANSRVR, EMAIL-2) inside the whole daemon, with a fake TNC and a
fake APRS-IS that answers as a service would: with Send what I hear on and a verified login they go over the
Internet connection and their acks and answers come back from it; otherwise they go on the radio as before. Nothing
else from the internet is taken.
"""

import re
from dataclasses import replace
from pathlib import Path

from neoaprs import TOCALL
from neoaprs.message import INTERNET_ROUTE, MessageRecord
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.air import on_air, said
from tests.support.env import Env, until
from tests.support.fakeaprsis import FakeAprsIs, fake_aprsis

OURS = f"OH2GBA>{TOCALL},TCPIP*:"


def settings(server: FakeAprsIs, gate: bool = True, show: bool = True) -> dict[str, str]:
    return {
        "igate/enabled": "true" if show else "false",
        "igate/gate": "true" if gate else "false",
        "igate/server": server.address,
    }


async def started(tmp_path: Path, server: FakeAprsIs, state: str = "connected", **options: object) -> Env:
    gate, show = bool(options.pop("gate", True)), bool(options.pop("show", True))
    e = Env(tmp_path, settings=settings(server, gate, show), **options)  # type: ignore[arg-type]
    e.ctl.messaging.tick_sec = 0.02
    e.ctl.messaging.pace.spacing_sec = 0.0
    await e.start()
    await e.until_usable()
    await until(lambda: e.ctl.igate.state == state)
    return e


def lines_to(server: FakeAprsIs, call: str) -> list[str]:
    """Our message and ack lines on the server to `call`."""
    return [line for line in server.packets if line.startswith(f"{OURS}:{call:<9}:")]


def record_of(e: Env, number: int) -> MessageRecord:
    found = e.ctl.messaging.get(number)
    assert found is not None
    return found


async def test_a_message_to_a_listed_service_goes_over_the_internet_and_its_ack_and_answer_come_back_from_there(
    tmp_path: Path,
) -> None:
    server = await fake_aprsis()
    e = await started(tmp_path, server)
    record = await e.ctl.messaging.send("OTA", "CHASE OH-0001")
    await until(lambda: lines_to(server, "OTA") != [])
    [line] = lines_to(server, "OTA")
    assert re.fullmatch(rf"{re.escape(OURS)}:OTA      :CHASE OH-0001\{{{record.msg_id}\}}", line), line
    assert await said(e, 1, 0.3) == [], "(nothing on the radio)"
    [attempt] = e.ctl.messaging.delivery.attempts_of(record.id)
    assert attempt.by_internet and attempt.radio_id is None
    await e.settled()
    [stored] = (await e.ctl.messagelog.chains())[record.id]
    assert stored.by_internet, "(the database keeps the way, so a restart shows it too)"
    server.send(f"OTA>APRS,TCPIP*,qAC,TESTSRV::OH2GBA   :ack{record.msg_id}".encode())
    await until(lambda: record_of(e, record.id).state == "acked")
    server.send(b"OTA>APRS,TCPIP*,qAC,TESTSRV::OH2GBA   :Chase logged{AB}")
    await until(lambda: any(r.direction == "in" for r in e.ctl.messaging.records()))
    [answer] = [r for r in e.ctl.messaging.records() if r.direction == "in"]
    assert (answer.from_call, answer.text, answer.route, answer.radio_id) == (
        "OTA",
        "Chase logged",
        INTERNET_ROUTE,
        None,
    )
    await until(lambda: len(lines_to(server, "OTA")) == 2)
    assert lines_to(server, "OTA")[1] == f"{OURS}:OTA      :ackAB}}", "(the ack goes back over the internet)"
    assert await said(e, 1, 0.3) == [], "(and nothing on the radio)"
    await e.stop()


async def test_the_email_gateway_follows_the_same_rule(tmp_path: Path) -> None:
    server = await fake_aprsis()
    e = await started(tmp_path, server)
    record = await e.ctl.messaging.send("EMAIL-2", "jane@example.org hello")
    await until(lambda: lines_to(server, "EMAIL-2") != [])
    assert record.attempts_max == 2 and await said(e, 1, 0.3) == []
    await e.stop()


async def test_without_send_what_i_hear_a_message_to_a_service_goes_on_the_radio_as_before(tmp_path: Path) -> None:
    server = await fake_aprsis(verified=False)
    e = await started(tmp_path, server, state="listening", gate=False)
    record = await e.ctl.messaging.send("ANSRVR", "CQ HOTG hello")
    [frame] = await said(e)
    assert frame.tnc2().endswith(f"::ANSRVR   :CQ HOTG hello{{{record.msg_id}}}") and server.packets == []
    [attempt] = e.ctl.messaging.delivery.attempts_of(record.id)
    assert not attempt.by_internet and attempt.radio_id is not None
    await e.stop()


async def test_with_a_passcode_the_server_refused_a_message_to_a_service_goes_on_the_radio(tmp_path: Path) -> None:
    server = await fake_aprsis(verified=False)
    e = await started(tmp_path, server, state="unverified")
    await e.ctl.messaging.send("OTA", "CQ")
    assert len(await said(e)) == 1 and server.packets == []
    await e.stop()


async def test_a_message_over_the_internet_from_a_call_that_is_no_listed_service_is_neither_kept_nor_acked(
    tmp_path: Path,
) -> None:
    server = await fake_aprsis()
    e = await started(tmp_path, server)
    await until(lambda: server.packets != [])  # (our position)
    before = list(server.packets)
    server.send(b"OH2XYZ>APRS,TCPIP*,qAC,TESTSRV::OH2GBA   :hello from the internet{1}")
    server.send(b"OTA>APRS,TCPIP*,qAC,TESTSRV::OH2XYZ   :not for us{2}")
    server.send(b"OTA>APRS,TCPIP*,qAC,TESTSRV::OH2GBA   :for us{3}")
    await until(lambda: e.ctl.messaging.records() != [])
    assert [(r.from_call, r.text) for r in e.ctl.messaging.records()] == [("OTA", "for us")]
    await until(lambda: len(server.packets) == len(before) + 1)
    assert server.packets[len(before) :] == [f"{OURS}:OTA      :ack3}}"]
    await e.stop()


async def test_an_answer_heard_both_over_the_internet_and_by_radio_through_an_igate_is_kept_once_and_shown_while_the_gated_packets_are_hidden(
    tmp_path: Path,
) -> None:
    server = await fake_aprsis()
    e = await started(tmp_path, server, web=True)
    assert await e.ctl.change_config(lambda c: replace(c, igate_show_gated=False))
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    server.send(b"ANSRVR>APRS,TCPIP*,qAC,TESTSRV::OH2GBA   :NOTICE Joined HOTG{7}")
    e.feed(on_air("OH7JHF-1", b"}ANSRVR>APRS,TCPIP,OH7JHF-1*::OH2GBA   :NOTICE Joined HOTG{7", path="OH2RCH-3*"))
    await until(lambda: e.tnc.stats.packets == 1)
    await e.settled()
    [kept] = [r for r in e.ctl.messaging.records() if r.direction == "in"]
    assert kept.text == "NOTICE Joined HOTG"
    await page.until(lambda: any(row["text"] == "NOTICE Joined HOTG" for row in page.topics["messages"].values()))
    await e.stop()


async def test_a_message_that_waits_when_send_what_i_hear_is_switched_off_goes_on_the_radio_at_its_next_attempt(
    tmp_path: Path,
) -> None:
    server = await fake_aprsis()
    e = await started(tmp_path, server)
    record = await e.ctl.messaging.send("OTA", "CQ")
    await until(lambda: lines_to(server, "OTA") != [])
    assert await e.ctl.change_config(lambda c: replace(c, igate_gate=False))
    assert not e.ctl.messaging.internet_open()
    e.now.advance(40)  # type: ignore[attr-defined]
    [frame] = await said(e)
    assert frame.tnc2().endswith(f"::OTA      :CQ{{{record.msg_id}}}")
    first, second = e.ctl.messaging.delivery.attempts_of(record.id)
    assert first.by_internet and not second.by_internet and second.radio_id is not None
    assert len(lines_to(server, "OTA")) == 1
    await e.stop()


async def test_a_message_on_its_way_over_the_internet_says_so_to_the_page_and_names_no_radio(tmp_path: Path) -> None:
    """Its Route is no radio's while the Internet way is open: the row says `internet_now`, and `radio_now` is null."""
    server = await fake_aprsis()
    e = await started(tmp_path, server, web=True)
    page = await e.ws()
    await page.until(lambda: "messages" in page.topics)
    record = await e.ctl.messaging.send("OTA", "CHASE OH-0001")
    await page.until(lambda: str(record.id) in page.topics["messages"])
    row = page.topics["messages"][str(record.id)]
    assert (row["state"], row["radio_now"], row["internet_now"]) == ("sending", None, True)
    await page.send({"cmd": "set_config", "values": {"igate/gate": "false"}})
    await page.until(
        lambda: page.topics["messages"][str(record.id)]["internet_now"] is False
        or page.topics["messages"][str(record.id)]["state"] != "sending"
    )
    await e.stop()
