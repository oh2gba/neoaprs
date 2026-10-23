"""Reply-acks (neoaprs/aprsmessage.py, services/inbox.py, services/messaging.py) inside the whole daemon, the radio a pseudo-terminal: the exact frames on the line for a message we send, its ack and a
reply-ack, and what a reply-ack of a station settles."""
import asyncio
from pathlib import Path

from neoaprs.message import MessageRecord
from tests.support.air import ack_info, message_info, on_air, said
from tests.support.env import Env, until

SENT = "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :"                        # (the frame of every message and ack to OH2RDG, up to its text)


async def started(tmp_path: Path) -> Env:
    e = Env(tmp_path)
    e.ctl.messaging.tick_sec = 0.02
    await e.start()
    await asyncio.sleep(0.2)
    return e


def sent_one(e: Env) -> MessageRecord:
    return next(r for r in e.ctl.messaging.records() if r.direction == "out")


async def test_a_message_with_nothing_to_acknowledge_goes_out_as_text_and_the_number_in_braces(tmp_path: Path) -> None:
    e = await started(tmp_path)
    await e.ctl.messaging.send("OH2RDG", "Hello Pekka")
    assert [f.tnc2() for f in await said(e)] == [SENT + "Hello Pekka{01}"]
    await e.stop()


async def test_a_message_with_a_reply_ack_number_is_acked_with_a_copy_of_the_number_and_its_aa_settles_our_message(tmp_path: Path) -> None:
    e = await started(tmp_path)
    await e.ctl.messaging.send("OH2RDG", "Hello Pekka")                       # {01}
    await said(e)
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Hei Pekka", "05", "01"), path="OH2RCH-2*"))      # their message 05, with the reply-ack 01: "I have your 01"
    await until(lambda: e.tnc.stats.packets == 1)
    [ack] = await said(e)
    assert ack.tnc2() == SENT + "ack05}01", "the ack is the number as it came"
    await until(lambda: e.ctl.messaging.records()[0].state == "acked" and len(e.ctl.messaging.records()) == 2)
    assert [(m.direction, m.text, m.msg_id, m.state) for m in e.ctl.messaging.records()] == [("out", "Hello Pekka", "01", "acked"), ("in", "Hei Pekka", "05", "received")]
    await e.stop()


async def test_the_aa_of_another_station_or_of_no_message_of_ours_settles_nothing_and_the_message_is_still_kept_and_acked(tmp_path: Path) -> None:
    e = await started(tmp_path)
    await e.ctl.messaging.send("OH2RDG", "Hello Pekka")
    await said(e)
    e.feed(on_air("OH2XYZ", message_info("OH2GBA", "Hi", "05", "01")))        # (not the station we sent 01 to)
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Hej", "06", "77")))       # (no message 77 of ours)
    await until(lambda: e.tnc.stats.packets == 2)
    assert [f.tnc2() for f in await said(e, 2)] == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2XYZ   :ack05}01", SENT + "ack06}77"]
    await until(lambda: len(e.ctl.messaging.records()) == 3)
    assert e.ctl.messaging.records()[0].state == "sending"
    await e.stop()


async def test_a_message_that_says_it_knows_reply_acks_is_acked_plainly_and_the_next_message_to_it_carries_its_number(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi", "05", "")))         # {05}
    await until(lambda: e.tnc.stats.packets == 1)
    [ack] = await said(e)
    assert ack.tnc2() == SENT + "ack05"
    await e.ctl.messaging.send("OH2RDG", "Moikka")
    assert [f.tnc2() for f in await said(e)] == [SENT + "Moikka{01}05"], "our message acknowledges theirs by the way"
    await e.stop()


async def test_a_message_from_a_station_that_does_not_know_reply_acks_is_acked_plainly_and_nothing_rides_on_ours(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi", "05")))
    await until(lambda: e.tnc.stats.packets == 1)
    assert [f.tnc2() for f in await said(e)] == [SENT + "ack05"]
    await e.ctl.messaging.send("OH2RDG", "Moikka")
    assert [f.tnc2() for f in await said(e)] == [SENT + "Moikka{01}"]
    await e.stop()


async def test_every_attempt_carries_the_latest_message_that_is_owed_an_ack_and_a_station_that_answers_is_owed_none(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi", "05", "")))
    await until(lambda: e.tnc.stats.packets == 1)
    await said(e)
    await e.ctl.messaging.send("OH2RDG", "Moikka")                            # attempt 1: {01}05
    e.now.advance(2)                                                        # type: ignore[attr-defined]
    e.feed(on_air("OH2RDG", message_info("OH2GBA", "Moi taas", "06", "")))    # (they do not hear us: a newer message of theirs)
    await until(lambda: e.tnc.stats.packets == 2)
    e.now.advance(30)                                                       # type: ignore[attr-defined]
    await until(lambda: sent_one(e).attempts == 2)
    assert [f.tnc2() for f in await said(e, 3)] == [SENT + "Moikka{01}05", SENT + "ack06", SENT + "Moikka{01}06"], "the retry keeps the number 01 and carries the latest AA"
    e.feed(on_air("OH2RDG", ack_info("OH2GBA", "01")))
    await until(lambda: sent_one(e).state == "acked")
    await e.ctl.messaging.send("OH2RDG", "Kiitos")
    assert [f.tnc2() for f in await said(e)] == [SENT + "Kiitos{02}"], "they answered, so nothing is owed"
    await e.stop()


async def test_an_ack_with_a_copy_of_a_reply_ack_number_acks_the_message_it_names(tmp_path: Path) -> None:
    e = await started(tmp_path)
    await e.ctl.messaging.send("OH2RDG", "Hello Pekka")
    await said(e)
    e.feed(on_air("OH2RDG", b":OH2GBA   :ack01}05"))
    await until(lambda: e.ctl.messaging.records()[0].state == "acked")
    assert [m.direction for m in e.ctl.messaging.records()] == ["out"], "it is an ack and no message"
    await e.stop()


async def test_a_reply_ack_over_the_internet_works_the_same(tmp_path: Path) -> None:
    e = await started(tmp_path)
    await e.ctl.messaging.send("OH2BEA-9", "Hello Pekka")
    await said(e)
    e.feed(on_air("OH7JHF-1", b"}OH2BEA-9>APY300,TCPIP,OH7JHF-1*::OH2GBA   :Test ok{06}01", path="OH2RCH-3*"))
    await until(lambda: e.ctl.messaging.records()[0].state == "acked")
    [ack] = await said(e)
    assert ack.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2BEA-9 :ack06}01"
    await e.stop()
