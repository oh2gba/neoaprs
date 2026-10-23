"""Messaging (neoaprs/services/messaging.py) inside the whole daemon, the radio a pseudo-terminal: a message goes out as a KISS frame and is in the packet log as a packet we sent, a message that is
sent to us is kept and acked on the line, an ack through the line settles the message, a restart goes on where it left off, the pruning, and the controller starting and stopping the part."""
import asyncio
import logging
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.clock import utc
from neoaprs.message import MessageRecord, MessagingError
from neoaprs.packet import Message
from neoaprs.source import Source
from tests.support.air import ack_info, message_info, on_air, reject_info, said
from tests.support.env import Env, until

WORKED = "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :Hello Pekka{01}"


async def started(tmp_path: Path) -> Env:
    e = Env(tmp_path)
    e.ctl.messaging.tick_sec = 0.02
    e.ctl.messaging.pace.spacing_sec = 0.0
    await e.start()
    await asyncio.sleep(0.2)                                                # (the TNC has settled: nothing was said in command mode)
    return e


async def kept(e: Env) -> list[MessageRecord]:
    await e.settled()
    return await e.ctl.messagelog.recent()


async def test_a_message_goes_out_as_a_kiss_frame_and_is_in_the_packet_log_as_a_packet_we_sent(tmp_path: Path) -> None:
    e = await started(tmp_path)
    record = await e.ctl.messaging.send("OH2RDG", "Hello Pekka")
    [frame] = await said(e)
    assert frame.tnc2() == WORKED and frame.is_ui
    [sent] = await e.packets()
    assert (sent.direction, sent.source, sent.destination, sent.path) == ("out", "OH2GBA", "APZNEO", ("WIDE1-1", "WIDE2-1"))
    assert isinstance(sent.decoded, Message) and (sent.decoded.addressee, sent.decoded.text, sent.decoded.msg_id) == ("OH2RDG", "Hello Pekka", "01")
    assert await kept(e) == [record] and record.state == "sending" and record.attempts == 1
    assert e.ctl.stationbook.get("OH2RDG") is None, "a packet we sent makes no station"
    await e.stop()


async def test_an_ack_through_the_line_settles_the_message_and_the_database_has_it(tmp_path: Path) -> None:
    e = await started(tmp_path)
    await e.ctl.messaging.send("OH2RDG", "Hello Pekka")
    await said(e)
    e.feed(on_air("OH2RDG", ack_info("OH2GBA", "01")))
    await until(lambda: e.ctl.messaging.records()[0].state == "acked")
    [row] = await kept(e)
    assert (row.state, row.attempts, row.acked_at) == ("acked", 1, e.now())
    e.now.advance(3600)                                                     # type: ignore[attr-defined]
    await asyncio.sleep(0.15)
    assert await said(e, 1, 0.2) == [], "an acked message is not sent again"
    await e.stop()


async def test_a_rej_through_the_line_settles_the_message_as_rejected(tmp_path: Path) -> None:
    e = await started(tmp_path)
    await e.ctl.messaging.send("OH2RDG", "Hello Pekka")
    e.feed(on_air("OH2RDG", reject_info("OH2GBA", "01")))
    await until(lambda: e.ctl.messaging.records()[0].state == "rejected")
    assert [m.state for m in await kept(e)] == ["rejected"]
    await e.stop()


async def test_a_message_sent_to_us_is_kept_and_the_ack_is_on_the_line_and_in_the_log(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH2RDG-7", message_info("OH2GBA", "Moi!", "12")))
    await until(lambda: e.tnc.stats.packets == 1)                          # (the line is read by the loop: said() blocks it, so it comes after)
    [ack] = await said(e)
    assert ack.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG-7 :ack12"
    await until(lambda: len(e.ctl.messaging.records()) == 1)
    [row] = await kept(e)
    assert (row.direction, row.from_call, row.to_call, row.text, row.msg_id, row.state) == ("in", "OH2RDG-7", "OH2GBA", "Moi!", "12", "received")
    assert [p.direction for p in reversed(await e.packets())] == ["in", "out"], "the message, then our ack"
    station = e.ctl.stationbook.get("OH2RDG-7")
    assert station is not None and station.packets == 1
    e.now.advance(11)                                                        # type: ignore[attr-defined]  (it did not hear the ack: it sends it again, and that is more than ten seconds after our ack)
    e.feed(on_air("OH2RDG-7", message_info("OH2GBA", "Moi!", "12")))
    await until(lambda: e.tnc.stats.packets == 2)
    assert len(await said(e)) == 1
    assert len(await kept(e)) == 1
    await e.stop()


async def test_a_message_to_somebody_else_is_in_the_packet_log_and_kept_as_overheard_and_not_acked(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH2RDG", message_info("OH2XYZ", "not for us", "3")))
    await until(lambda: e.tnc.stats.packets == 1)
    assert await said(e, 1, 0.3) == [] and await kept(e) == [] and len(await e.packets()) == 1
    [row] = await e.ctl.messagelog.recent(overheard=True)
    assert (row.state, row.direction, row.from_call, row.to_call, row.text) == ("overheard", "in", "OH2RDG", "OH2XYZ", "not for us")
    await e.stop()


async def test_the_ack_and_the_messages_to_a_station_go_by_its_remembered_path_which_a_restart_remembers(tmp_path: Path) -> None:
    first = await started(tmp_path)
    await first.ctl.prefbook.set_path("OH2RDG-7", "OH2RCH-2,WIDE2-1")
    first.feed(on_air("OH2RDG-7", message_info("OH2GBA", "Moi!", "12")))
    await until(lambda: first.tnc.stats.packets == 1)
    [ack] = await said(first)
    assert ack.tnc2() == "OH2GBA>APZNEO,OH2RCH-2,WIDE2-1::OH2RDG-7 :ack12"
    await first.stop()
    second = await started(tmp_path)
    await second.ctl.messaging.send("OH2RDG-7", "Hello Pekka")
    assert [f.tnc2() for f in await said(second)] == ["OH2GBA>APZNEO,OH2RCH-2,WIDE2-1::OH2RDG-7 :Hello Pekka{01}"]
    await second.stop()


async def test_a_restart_finds_the_messages_and_goes_on_with_the_one_being_sent(tmp_path: Path) -> None:
    first = await started(tmp_path)
    await first.ctl.messaging.send("OH2RDG", "Hello Pekka")
    first.feed(on_air("OH2RDK", message_info("OH2GBA", "Moi!", "5")))
    await until(lambda: len(first.ctl.messaging.records()) == 2)
    await first.stop()
    second = Env(tmp_path)
    second.ctl.messaging.tick_sec = 0.02
    await second.start()
    assert [(m.direction, m.text, m.state) for m in second.ctl.messaging.records()] == [("out", "Hello Pekka", "sending"), ("in", "Moi!", "received")]
    await asyncio.sleep(0.2)
    second.now.advance(31)                                                  # type: ignore[attr-defined]
    await until(lambda: second.ctl.messaging.records()[0].attempts == 2)
    assert [f.tnc2() for f in await said(second)] == [WORKED]
    assert (await second.ctl.messaging.send("OH2RDG", "second")).msg_id == "02", "the ids go on from the latest we sent"
    await second.stop()


async def test_with_the_cable_pulled_the_message_waits_and_goes_out_when_the_radio_is_back(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.unplug()
    await until(lambda: e.tnc.state is Source.State.WAITING)
    record = await e.ctl.messaging.send("OH2RDG", "Hello Pekka")
    assert (record.state, record.attempts) == ("sending", 0)
    e.now.advance(300)                                                      # type: ignore[attr-defined]
    await asyncio.sleep(0.15)
    assert e.ctl.messaging.records()[0].attempts == 0
    await e.plug()
    await e.until_connected()
    await until(lambda: e.ctl.messaging.records()[0].attempts == 1)
    await asyncio.sleep(0.2)
    assert [f.tnc2() for f in await said(e)] == [WORKED]
    await e.stop()


async def test_the_daily_prune_removes_no_message_however_old(tmp_path: Path) -> None:
    e = await started(tmp_path)
    await e.ctl.messagelog.insert(MessageRecord(0, utc(2026, 9, 1), "in", "OH2RDG", "OH2GBA", "ancient", "1", "received"))
    await e.ctl.messagelog.insert(MessageRecord(0, e.now() - timedelta(days=1), "in", "OH2RDG", "OH2GBA", "yesterday", "2", "received"))
    await e.settled()
    packets, stations = await e.ctl.prune()
    assert sorted(m.text for m in await e.ctl.messagelog.recent()) == ["ancient", "yesterday"] and packets == 0 and stations == []
    await e.stop()


async def test_the_controller_starts_the_ticker_after_the_beacon_and_stops_it_before(tmp_path: Path) -> None:
    e = Env(tmp_path)
    assert "messaging" not in {t.get_name() for t in asyncio.all_tasks()}
    await e.start()
    assert "messaging" in {t.get_name() for t in asyncio.all_tasks()}
    await e.stop()
    assert "messaging" not in {t.get_name() for t in asyncio.all_tasks()}
    assert e.ctl.messaging.get(1) is None


# ---- third-party packets: an iGate put on the air what it heard on the internet

GATED_ACK = b"}OH2DPN>APJYC1,TCPIP,OH7JHF-1*::OH2GBA   :ack01"                 # (the shape of a frame an iGate puts on the air, with the id of our first message)
GATED_MESSAGE = b"}OH2BEA-9>APY300,TCPIP,OH7JHF-1*::OH2GBA   :Test ok{06"


async def test_an_ack_the_internet_sent_and_an_igate_put_on_the_air_settles_the_message(tmp_path: Path) -> None:
    e = await started(tmp_path)
    await e.ctl.messaging.send("OH2DPN", "Hello Pekka")
    await said(e)
    e.feed(on_air("OH7JHF-1", GATED_ACK, path="OH2RCH-3*"))
    await until(lambda: e.ctl.messaging.records()[0].state == "acked")
    [row] = await kept(e)
    assert (row.state, row.attempts, row.acked_at) == ("acked", 1, e.now())
    station = e.ctl.stationbook.get("OH2DPN")
    assert station is not None and station.packets == 1 and e.ctl.stationbook.get("OH7JHF-1") is None, "the packet counts for the sender inside, the iGate is no station"
    await e.stop()


async def test_a_message_the_internet_sent_is_received_once_and_acked_to_the_inner_sender_and_the_route_says_where_it_came_in(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH7JHF-1", GATED_MESSAGE, path="OH2RCH-3*"))
    await until(lambda: e.tnc.stats.packets == 1)
    [ack] = await said(e)
    assert ack.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2BEA-9 :ack06", "the ack goes to the sender inside, not to the iGate"
    await until(lambda: len(e.ctl.messaging.records()) == 1)
    e.feed(on_air("OH2BEA-9", message_info("OH2GBA", "Test ok", "06"), path=""))     # (the same message, heard direct as well)
    await until(lambda: e.tnc.stats.packets == 2)
    assert await said(e, 1, 0.3) == [], "the copy that came direct, within ten seconds of our ack, is not acked again"
    [row] = await kept(e)
    assert (row.from_call, row.to_call, row.text, row.msg_id, row.state) == ("OH2BEA-9", "OH2GBA", "Test ok", "06", "received")
    assert row.route == "via OH7JHF-1 (internet) → OH2RCH-3", "the copy that came first is the one that was kept"
    station = e.ctl.stationbook.get("OH2BEA-9")
    assert station is not None and station.packets == 2 and station.deliveries.gated == 1 and station.deliveries.direct == 1
    assert station.best_route is not None and station.best_route.direct, "only the direct delivery is a route to send by"
    await e.stop()


async def test_our_own_message_gated_back_to_us_is_ignored_like_an_echo(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH7JHF-1", b"}OH2GBA>APZNEO,TCPIP,OH7JHF-1*::OH2DPN   :Hello Pekka{1", path="OH2RCH-3*"))
    await until(lambda: e.tnc.stats.packets == 1)
    await asyncio.sleep(0.1)
    assert await said(e, 1, 0.2) == [] and e.ctl.messaging.records() == []
    assert e.ctl.stationbook.get("OH7JHF-1") is None, "the iGate is no station: the packet was our own"
    await e.stop()


async def test_three_copies_of_a_message_within_six_seconds_are_one_ack_on_the_line(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH2RDG-7", message_info("OH2GBA", "Moi!", "12"), path="OH2RCH-2*"))
    await until(lambda: e.tnc.stats.packets == 1)
    [ack] = await said(e)
    assert ack.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG-7 :ack12"
    e.now.advance(3)                                                        # type: ignore[attr-defined]
    e.feed(on_air("OH2RDG-7", message_info("OH2GBA", "Moi!", "12"), path="OH2RCH-3*"))
    await until(lambda: e.tnc.stats.packets == 2)
    e.now.advance(3)                                                        # type: ignore[attr-defined]
    e.feed(on_air("OH7JHF-1", b"}OH2RDG-7>APRS,TCPIP,OH7JHF-1*::OH2GBA   :Moi!{12", path="OH2RCH-3*"))
    await until(lambda: e.tnc.stats.packets == 3)
    assert await said(e, 1, 0.3) == [], "the other two copies are not acked"
    await until(lambda: len(e.ctl.messaging.records()) == 1)
    assert len(await kept(e)) == 1
    await e.stop()


# ---- RF only: RFONLY is the last element of every path we send to the station

async def test_a_message_and_our_ack_to_an_rf_only_station_end_with_rfonly_and_the_chain_does_not_hold_it(tmp_path: Path) -> None:
    e = await started(tmp_path)
    await e.ctl.prefbook.set_rf_only("OH2RDG", True)
    await e.ctl.messaging.send("OH2RDG", "Hello Pekka")
    [frame] = await said(e)
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1,RFONLY::OH2RDG   :Hello Pekka{01}"
    assert [a.path for a in e.ctl.messaging.delivery.attempts_of(1)] == [("WIDE1-1", "WIDE2-1")], "RFONLY is no hop"
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi!", "12")))
    await until(lambda: e.tnc.stats.packets == 1)
    [ack] = await said(e)
    assert ack.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1,RFONLY::OH2RDG   :ack12"
    e.feed(on_air("OH2XYZ", message_info("OH2GBA", "Moi!", "13")))
    await until(lambda: e.tnc.stats.packets == 2)
    [other] = await said(e)
    assert other.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2XYZ   :ack13", "the others are not RF only"
    await e.stop()


async def test_the_station_path_comes_before_rfonly_and_a_path_that_has_rfonly_or_nogate_gets_no_second(tmp_path: Path) -> None:
    e = await started(tmp_path)
    await e.ctl.prefbook.set_rf_only("OH2RDG", True)
    await e.ctl.prefbook.set_path("OH2RDG", "OH2RCH-2,WIDE2-1")
    await e.ctl.messaging.send("OH2RDG", "one")
    await e.ctl.prefbook.set_path("OH2RDG", "RFONLY,OH2RCH-2")
    await e.ctl.messaging.send("OH2RDG", "two")
    await e.ctl.prefbook.set_path("OH2RDG", "OH2RCH-2,NOGATE")
    await e.ctl.messaging.send("OH2RDG", "three")
    await e.ctl.prefbook.set_path("OH2RDG", "")
    await e.ctl.messaging.send("OH2RDG", "four")
    assert [f.tnc2() for f in await said(e, 4)] == [
        "OH2GBA>APZNEO,OH2RCH-2,WIDE2-1,RFONLY::OH2RDG   :one{01}", "OH2GBA>APZNEO,RFONLY,OH2RCH-2::OH2RDG   :two{02}",
        "OH2GBA>APZNEO,OH2RCH-2,NOGATE::OH2RDG   :three{03}", "OH2GBA>APZNEO,RFONLY::OH2RDG   :four{04}"]
    await e.stop()


async def test_with_eight_digipeaters_already_a_message_to_an_rf_only_station_is_refused_and_a_waiting_one_waits_and_goes_when_the_path_is_shorter(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = await started(tmp_path)
    eight = ",".join(f"OH2RC{n}" for n in range(8))
    await e.ctl.prefbook.set_path("OH2RDG", eight)
    await e.ctl.messaging.send("OH2RDG", "waits")                                  # (it goes: the station is not RF only yet)
    assert len(await said(e)) == 1
    await e.ctl.prefbook.set_rf_only("OH2RDG", True)
    with pytest.raises(MessagingError, match="path too long for RF only"):
        await e.ctl.messaging.send("OH2RDG", "refused")
    assert [r.text for r in e.ctl.messaging.records()] == ["waits"], "a refused message is not kept"
    e.now.advance(60)                                                              # type: ignore[attr-defined]  (the second attempt of the first message is due)
    with caplog.at_level(logging.WARNING, "neoaprs.messaging"):
        await asyncio.sleep(0.3)
    assert await said(e, 1, 0.2) == [] and e.ctl.messaging.records()[0].attempts == 1 and e.ctl.messaging.records()[0].state == "sending"
    assert len([r for r in caplog.records if "path too long for RF only" in r.getMessage()]) == 1, "told once, not at every tick"
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi!", "12")))
    await until(lambda: e.tnc.stats.packets == 1)
    assert await said(e, 1, 0.3) == [], "an ack that cannot go by that path is not sent"
    await e.ctl.prefbook.set_path("OH2RDG", "OH2RC0")
    await until(lambda: e.ctl.messaging.records()[0].attempts == 2)
    assert [f.tnc2() for f in await said(e)] == ["OH2GBA>APZNEO,OH2RC0,RFONLY::OH2RDG   :waits{01}"]
    await e.stop()
