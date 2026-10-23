"""Messaging (neoaprs/services/messaging.py) on a Tnc that is a stub, a real message log on a real database thread and a clock the test holds: the bytes of a message and of an ack, the checks, the
ids, the schedule of the attempts, the acks and rejects, retry and cancel, the radio away, the messages that come in (kept once, acked once for each burst of copies), and the restart."""
import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.config import Config
from neoaprs.message import MSG_IDS, MessageRecord, MessagingError
from neoaprs.messagelog import MessageLog
from neoaprs.packet import Message, Packet, ThirdParty
from neoaprs.services import messaging as messaging_module
from neoaprs.services.messaging import Messaging
from neoaprs.services.prefbook import PrefBook
from neoaprs.source import Source, unusable_because
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, remember_stop, until
from tests.support.storedb import store_at

TICK = 0.01
RUN_OUT = (30, 30, 60, 120, 240, 240)             # the waits after each attempt, the last of them the wait for the answer to the sixth: after these the message has failed
WORKED = "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :Hello Pekka{01}"


class StubTnc:
    """The part of the Tnc messaging uses: a state, and the frames it was given."""

    def __init__(self) -> None:
        self.state = Source.State.CONNECTED
        self.sent: list[ax25.Frame] = []
        self.takes = True

    @property
    def usable(self) -> bool:
        return self.state is Source.State.CONNECTED

    def why_unusable(self) -> str:
        return unusable_because(self.state)

    def send_frame(self, frame: ax25.Frame) -> bool:
        if self.takes:
            self.sent.append(frame)
        return self.takes

    def lines(self) -> list[str]:
        return [f.tnc2() for f in self.sent]


class Rig:
    def __init__(self, log: MessageLog, clock: FixedClock, tnc: StubTnc | None = None, spacing_sec: float = 0.0, **changes: object) -> None:
        self.config: Config = replace(ON_AIR, **changes)             # type: ignore[arg-type]
        self.tnc = tnc or StubTnc()
        self.clock = clock
        self.log = log
        self.prefs = PrefBook(log, lambda: self.config)
        self.board: list[tuple[Packet, Message]] = []                   # what messaging handed to the message board
        self.m = Messaging(self.tnc, lambda: self.config, log, self.prefs.path_for, clock, tick_sec=TICK, board=lambda packet, message: self.board.append((packet, message)),
                        attempts=self.prefs.attempts_for, spacing_sec=spacing_sec)
        remember_stop(self.m.stop)
        self.changed: list[MessageRecord] = []
        self.removed: list[MessageRecord] = []
        self.m.changed.connect(self.changed.append)
        self.m.removed.connect(self.removed.append)

    async def start(self) -> None:
        """What the controller's start does for messaging: the paths of the stations, then the service."""
        await self.prefs.load()
        await self.m.start()

    async def settled(self) -> None:
        """What messaging gave the database is on it (the keeping of a message that came in is a task, the updates are appends)."""
        await asyncio.gather(*self.m.inbox.tasks)
        assert self.log.db is not None
        await self.log.db.barrier()

    async def radio(self, state: Source.State) -> None:
        """The Tnc changes state and the ticker, which looks at it every few milliseconds, has seen it."""
        self.tnc.state = state
        await asyncio.sleep(TICK * 6)

    async def pass_time(self, seconds: float) -> None:
        """The clock moves and the ticker, which looks at it every few milliseconds, has looked."""
        self.clock.advance(seconds)
        await asyncio.sleep(TICK * 6)

    def heard(self, source: str, addressee: str, text: str = "", msg_id: str | None = None, ack: str | None = None, rej: str | None = None, direction: str = "in",
              reply: str | None = None) -> Packet:
        """A packet of a message heard: `reply` is the reply-ack part of its number (`{msg_id}reply`; "" for `{msg_id}`), and the information field is what the air would have had."""
        decoded = Message(addressee, text, msg_id, ack, rej)
        line = f"ack{ack}" if ack is not None else f"rej{rej}" if rej is not None else text + ("" if msg_id is None else f"{{{msg_id}" + ("" if reply is None else f"}}{reply}"))
        info = f":{addressee:<9}:{line}".encode()
        return Packet(self.clock(), direction, b"", source, "APRS", ("WIDE1*", "OH2RCH-2*", "WIDE2-2"), info, decoded)  # type: ignore[arg-type]

    def state(self, number: int = 1) -> MessageRecord:
        record = self.m.get(number)
        assert record is not None
        return record


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    assert store.db is not None
    r = Rig(MessageLog(store.db, clock), clock)
    await r.start()
    return r


@pytest.fixture
def another(rig: Rig) -> Callable[..., Rig]:
    """A second messaging on the same database, as after a restart of the daemon."""
    def make(**changes: object) -> Rig:
        return Rig(rig.log, rig.clock, rig.tnc, **changes)
    return make


# ---- sending -------------------------------------------------------------------------------------------------------------------------------------

async def test_a_message_goes_out_at_once_as_the_frame_the_settings_make_and_is_kept_as_sending(rig: Rig) -> None:
    record = await rig.m.send("oh2rdg", "Hello Pekka")
    assert rig.tnc.lines() == [WORKED]
    [frame] = rig.tnc.sent
    assert frame.info == b":OH2RDG   :Hello Pekka{01}" and frame.is_ui and (str(frame.source), str(frame.destination), frame.path_text) == ("OH2GBA", "APZNEO", "WIDE1-1,WIDE2-1")
    assert ax25.decode(ax25.encode(frame)) == frame
    assert record == MessageRecord(1, rig.clock(), "out", "OH2GBA", "OH2RDG", "Hello Pekka", "01", "sending", 1, rig.clock())
    await rig.settled()
    assert await rig.log.recent() == [record]


async def test_the_frame_follows_the_settings_destination_and_path_and_our_call(rig: Rig) -> None:
    rig.config = replace(rig.config, station_call="OH2GBA-9", beacon_destination="APRS", beacon_path="WIDE2-2")
    await rig.m.send("OH2RDG-7", "x")
    assert rig.tnc.lines() == ["OH2GBA-9>APRS,WIDE2-2::OH2RDG-7 :x{01}"]
    rig.config = replace(rig.config, beacon_path="")
    await rig.m.send("OH2RDG", "y")
    assert rig.tnc.lines()[1] == "OH2GBA-9>APRS::OH2RDG   :y{02}"


async def test_the_message_ids_go_01_02_03_and_on_after_a_restart(rig: Rig, another: Callable[..., Rig]) -> None:
    assert [(await rig.m.send("OH2RDG", t)).msg_id for t in "abc"] == ["01", "02", "03"]
    await rig.settled()
    await rig.m.stop()
    restarted = another()
    await restarted.start()
    assert (await restarted.m.send("OH2RDG", "d")).msg_id == "04"
    await restarted.m.stop()


async def test_the_ids_are_two_characters_01_to_99_then_a0_to_zz_and_go_round_past_those_still_being_sent(rig: Rig) -> None:
    await rig.log.insert(MessageRecord(0, rig.clock(), "out", "OH2GBA", "OH2XYZ", "pending", "01", "sending"))
    await rig.log.insert(MessageRecord(0, rig.clock(), "out", "OH2GBA", "OH2RDG", "old", "9Z", "acked"))
    other = Rig(rig.log, rig.clock, rig.tnc)
    await other.start()
    ids = [(await other.m.send("OH2RDG", "x")).msg_id for _ in range(4)]
    assert ids == ["00", "02", "03", "04"], "after 9Z comes 00, and 01 is a message that is still being sent"
    assert len(MSG_IDS) == 1296 and all(i is not None and len(i) == 2 for i in ids)
    await other.m.stop()


async def test_an_id_of_an_older_program_is_none_of_ours_and_the_numbers_begin_again_at_01(rig: Rig) -> None:
    await rig.log.insert(MessageRecord(0, rig.clock(), "out", "OH2GBA", "OH2RDG", "old", "99998", "acked"))
    other = Rig(rig.log, rig.clock, rig.tnc)
    await other.start()
    assert (await other.m.send("OH2RDG", "x")).msg_id == "01"
    await other.m.stop()


async def test_all_1296_ids_in_use_leave_no_id_for_another_message(rig: Rig) -> None:
    for ident in MSG_IDS:
        await rig.log.insert(MessageRecord(0, rig.clock(), "out", "OH2GBA", "OH2XYZ", "pending", ident, "sending", 1, rig.clock()))
    other = Rig(rig.log, rig.clock, rig.tnc)
    await other.start()
    with pytest.raises(MessagingError, match="1296"):
        await other.m.send("OH2RDG", "x")
    await other.m.stop()


async def test_a_message_of_a_station_with_a_ssid_goes_to_that_call_and_a_zero_ssid_is_none(rig: Rig) -> None:
    assert (await rig.m.send("oh2rdg-0", "x")).to_call == "OH2RDG"
    assert (await rig.m.send(" oh2rdg-12 ", "x")).to_call == "OH2RDG-12"


@pytest.mark.parametrize("to, text, reason", [
    ("", "x", "call"), ("TOOLONGCALL", "x", "call"), ("OH2RDG-16", "x", "SSID"), ("OH2 RDG", "x", "call"), ("OH2GBA", "x", "our own"), ("oh2gba-0", "x", "our own"),
    ("OH2RDG", "", "empty"), ("OH2RDG", " ", "empty"), ("OH2RDG", "x" * 68, "68 characters"), ("OH2RDG", "Hyvää", "printable ASCII"), ("OH2RDG", "a{b", "{"), ("OH2RDG", "a|b", "|"), ("OH2RDG", "a~b", "~"),
    ("OH2RDG", "a\tb", "control"), ("OH2RDG", "ack12", "ack")])
async def test_an_addressee_or_a_text_that_is_refused_is_told_why_and_nothing_is_kept_or_sent(rig: Rig, to: str, text: str, reason: str) -> None:
    with pytest.raises(MessagingError, match=reason):
        await rig.m.send(to, text)
    await rig.settled()
    assert rig.tnc.sent == [] and await rig.log.recent() == [] and rig.m.records() == [] and rig.changed == []


async def test_only_our_call_with_its_ssid_is_ours_to_refuse_and_the_base_call_and_another_ssid_are_stations(rig: Rig) -> None:
    rig.config = replace(rig.config, station_call="OH2GBA-7")
    with pytest.raises(MessagingError, match="our own"):
        await rig.m.send("OH2GBA-7", "x")
    assert [(await rig.m.send(call, "x")).to_call for call in ("OH2GBA", "OH2GBA-9")] == ["OH2GBA", "OH2GBA-9"]


async def test_settings_that_make_no_frame_refuse_the_message_before_it_is_kept(rig: Rig) -> None:
    rig.config = replace(rig.config, beacon_destination="A B")
    with pytest.raises(MessagingError, match="no frame"):
        await rig.m.send("OH2RDG", "x")
    await rig.settled()
    assert await rig.log.recent() == []


async def test_the_text_may_be_up_to_67_characters_of_printable_ascii_and_nothing_else(rig: Rig) -> None:
    record = await rig.m.send("OH2RDG", "x" * 67)
    assert record.attempts == 1 and rig.tnc.sent[0].info == b":OH2RDG   :" + b"x" * 67 + b"{01}"
    with pytest.raises(MessagingError, match="ä that is not printable ASCII"):
        await rig.m.send("OH2RDG", "Hyvää päivää")
    assert len(rig.tnc.sent) == 1


# ---- the schedule ---------------------------------------------------------------------------------------------------------------------------------

async def test_the_attempts_are_made_0_30_60_120_240_and_480_seconds_after_the_first_and_then_the_message_has_failed(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Hello")
    seen = []
    for step in (29, 1, 29, 1, 59, 1, 119, 1, 239, 1):
        await rig.pass_time(step)
        seen.append(len(rig.tnc.sent))
    assert seen == [1, 2, 2, 3, 3, 4, 4, 5, 5, 6], "attempts 2 to 6 at 30, 60, 120, 240 and 480 seconds"
    assert rig.state().state == "sending" and rig.state().attempts == 6
    await rig.pass_time(239)
    assert rig.state().state == "sending"
    await rig.pass_time(1)
    assert rig.state().state == "failed" and rig.state().attempts == 6
    await rig.pass_time(3600)
    assert len(rig.tnc.sent) == 6, "a failed message is not sent again"
    await rig.settled()
    assert [(m.state, m.attempts) for m in await rig.log.recent()] == [("failed", 6)]
    assert len({f.tnc2() for f in rig.tnc.sent}) == 1, "every attempt is the same frame"


async def attempts_at(rig: Rig, offsets: tuple[int, ...], wait: int = 240, end: str = "failed") -> None:
    """The message in `rig` is sent at these seconds after the first and is `end` (failed, or unconfirmed) `wait` seconds after the last, not a second before."""
    here = 0
    for n, offset in enumerate(offsets[1:], start=1):
        await rig.pass_time(offset - here - 1)
        assert len(rig.tnc.sent) == n and rig.state().state == "sending", f"attempt {n + 1} is not due a second before {offset}"
        await rig.pass_time(1)
        assert len(rig.tnc.sent) == n + 1
        here = offset
    await rig.pass_time(wait - 1)
    assert rig.state().state == "sending"
    await rig.pass_time(1)
    assert (rig.state().state, rig.state().attempts, len(rig.tnc.sent)) == (end, len(offsets), len(offsets))


@pytest.mark.parametrize("count, offsets", [(3, (0, 30, 60)), (10, (0, 30, 60, 120, 240, 480, 960, 1920, 2880, 3840))])
async def test_the_number_of_attempts_is_the_setting_and_the_waits_double_up_to_960_seconds(rig: Rig, count: int, offsets: tuple[int, ...]) -> None:
    rig.config = replace(rig.config, messages_attempts=count)
    record = await rig.m.send("OH2RDG", "Hello")
    assert record.attempts_max == count and len(rig.tnc.sent) == 1
    await attempts_at(rig, offsets)
    await rig.settled()
    assert [(m.state, m.attempts, m.attempts_max) for m in await rig.log.recent()] == [("failed", count, count)]


@pytest.mark.parametrize("count, offsets", [(1, (0,)), (2, (0, 30))])
async def test_a_message_that_was_given_one_or_two_attempts_and_got_no_ack_is_unconfirmed_not_failed(rig: Rig, count: int, offsets: tuple[int, ...]) -> None:
    rig.config = replace(rig.config, messages_attempts=count)
    record = await rig.m.send("OH2RDG", "Hello")
    assert record.attempts_max == count
    await attempts_at(rig, offsets, end="unconfirmed")
    await rig.pass_time(3600)
    assert len(rig.tnc.sent) == count, "an unconfirmed message is not sent again"
    await rig.settled()
    assert [(m.state, m.attempts, m.attempts_max) for m in await rig.log.recent()] == [("unconfirmed", count, count)]


async def test_a_message_that_was_given_three_attempts_has_failed_when_they_are_used_up(rig: Rig) -> None:
    rig.config = replace(rig.config, messages_attempts=3)
    await rig.m.send("OH2RDG", "Hello")
    await attempts_at(rig, (0, 30, 60))


async def test_send_takes_the_attempts_of_the_station_else_the_setting_and_keeps_them_across_a_change(rig: Rig, another: Callable[..., Rig]) -> None:
    await rig.prefs.set_attempts("EMAIL-2", 2)
    mail = await rig.m.send("EMAIL-2", "me@example.org Hello")
    friend = await rig.m.send("OH2RDG", "Hello")
    assert (mail.attempts_max, friend.attempts_max) == (2, 6) and len(rig.tnc.sent) == 2
    await rig.prefs.set_attempts("EMAIL-2", 5)
    await rig.prefs.set_attempts("OH2RDG", 1)
    assert (rig.state(1).attempts_max, rig.state(2).attempts_max) == (2, 6), "a message in the air keeps its own count"
    rig.config = replace(rig.config, messages_attempts=4)
    third = await rig.m.send("OH2XYZ", "Hello")
    fourth = await rig.m.send("OH2RDG", "Hello")
    assert (third.attempts_max, fourth.attempts_max) == (4, 1)
    await rig.settled()
    await rig.m.stop()
    again = another()
    await again.start()
    assert [m.attempts_max for m in again.m.records()] == [2, 6, 4, 1]
    await again.m.stop()


async def test_messaging_without_a_pref_book_takes_the_setting(rig: Rig) -> None:
    alone = Messaging(rig.tnc, lambda: rig.config, rig.log, rig.prefs.path_for, rig.clock, tick_sec=TICK, spacing_sec=0.0)
    rig.config = replace(rig.config, messages_attempts=3)
    assert (await alone.send("OH2RDG", "x")).attempts_max == 3
    await alone.stop()


async def test_the_station_with_one_attempt_gets_the_message_once_and_with_two_gets_it_twice_the_same(rig: Rig) -> None:
    await rig.prefs.set_attempts("EMAIL-2", 2)
    await rig.m.send("EMAIL-2", "me@example.org Hello")
    await rig.pass_time(30)
    assert len(rig.tnc.sent) == 2 and len({f.tnc2() for f in rig.tnc.sent}) == 1, "the gateway takes the repeat as the same message by its id"
    await rig.pass_time(240)
    assert rig.state().state == "unconfirmed"


async def test_a_message_keeps_the_number_of_attempts_it_was_sent_with_when_the_setting_changes_and_after_a_restart(rig: Rig, another: Callable[..., Rig]) -> None:
    rig.config = replace(rig.config, messages_attempts=3)
    await rig.m.send("OH2RDG", "first")
    rig.config = replace(rig.config, messages_attempts=5)
    second = await rig.m.send("OH2RDG", "second")
    assert (rig.state(1).attempts_max, second.attempts_max) == (3, 5)
    await rig.settled()
    assert [m.attempts_max for m in await rig.log.recent()] == [5, 3], "the number is in the database"
    again = another(messages_attempts=9)
    await again.start()
    assert [(m.id, m.attempts_max) for m in again.m.records()] == [(1, 3), (2, 5)], "and is what the message has after a restart, whatever the setting is then"
    await rig.m.stop()
    again.tnc.sent.clear()
    for step, expected in ((30, [(1, 2), (2, 2)]), (30, [(1, 3), (2, 3)]), (60, [(1, 3), (2, 4)]), (120, [(1, 3), (2, 5)])):
        await again.pass_time(step)
        assert [(m.id, m.attempts) for m in again.m.records()] == expected
    await again.pass_time(60)
    assert [(m.id, m.state) for m in again.m.records()] == [(1, "failed"), (2, "sending")], "three attempts and the wait are over for the first, the second's fifth is waited for still"


async def test_an_ack_from_the_addressee_with_our_id_settles_the_message_and_ends_the_attempts(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Hello")
    await rig.pass_time(31)
    assert len(rig.tnc.sent) == 2
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    record = rig.state()
    assert (record.state, record.attempts, record.acked_at) == ("acked", 2, rig.clock())
    await rig.pass_time(3600)
    assert len(rig.tnc.sent) == 2
    await rig.settled()
    assert await rig.log.recent() == [record]


async def test_the_ack_must_come_from_the_addressee_quote_our_id_and_be_for_us(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Hello")
    for packet in (rig.heard("OH2RDG-7", "OH2GBA", ack="01"), rig.heard("OH2XYZ", "OH2GBA", ack="01"), rig.heard("OH2RDG", "OH2GBA", ack="02"), rig.heard("OH2RDG", "OH2XYZ", ack="01"),
                   rig.heard("OH2RDG", "OH2GBA", ack="01", direction="out")):
        rig.m.on_packet(packet)
    assert rig.state().state == "sending"
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    assert rig.state().state == "acked"


async def test_a_second_ack_changes_nothing_and_an_ack_of_a_rejected_message_is_not_taken(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "a")
    await rig.m.send("OH2RDG", "b")
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    count = len(rig.changed)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    assert len(rig.changed) == count
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", rej="02"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="02"))
    assert (rig.state(1).state, rig.state(2).state, rig.state(2).acked_at) == ("acked", "rejected", None)


async def test_a_rej_settles_the_message_as_rejected_and_ends_the_attempts(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Hello")
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", rej="01"))
    assert (rig.state().state, rig.state().acked_at) == ("rejected", None)
    await rig.pass_time(3600)
    assert len(rig.tnc.sent) == 1


async def test_an_ack_that_comes_late_still_settles_a_message_that_has_failed_or_was_cancelled(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "a")
    await rig.m.send("OH2RDG", "b")
    rig.m.cancel(2)
    for step in RUN_OUT:
        await rig.pass_time(step)
    assert rig.state(1).state == "failed"
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="02"))
    assert (rig.state(1).state, rig.state(2).state) == ("acked", "acked")


@pytest.mark.parametrize("count", [1, 2])
async def test_an_ack_that_comes_after_the_message_is_unconfirmed_still_settles_it_and_so_does_a_rej(rig: Rig, count: int) -> None:
    rig.config = replace(rig.config, messages_attempts=count)
    await rig.m.send("OH2RDG", "a")
    await rig.m.send("OH2RDG", "b")
    for step in RUN_OUT:
        await rig.pass_time(step)
    assert (rig.state(1).state, rig.state(2).state) == ("unconfirmed", "unconfirmed")
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", rej="02"))
    assert (rig.state(1).state, rig.state(2).state) == ("acked", "rejected")
    assert rig.state(1).acked_at is not None
    await rig.settled()
    assert [m.state for m in await rig.log.recent()] == ["rejected", "acked"]


async def test_the_ack_settles_the_newest_message_with_that_id_to_that_station(rig: Rig, another: Callable[..., Rig]) -> None:
    for n in range(2):
        await rig.log.insert(MessageRecord(0, rig.clock(), "out", "OH2GBA", "OH2RDG", f"old {n}", "01", "failed", 6))
    restarted = another()
    await restarted.start()
    restarted.m.on_packet(restarted.heard("OH2RDG", "OH2GBA", ack="01"))
    assert [(r.text, r.state) for r in restarted.m.records()] == [("old 0", "failed"), ("old 1", "acked")]
    await restarted.m.stop()


# ---- retry and cancel -----------------------------------------------------------------------------------------------------------------------------

async def test_cancel_stops_a_message_that_is_being_sent_and_nothing_else(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Hello")
    cancelled = rig.m.cancel(1)
    assert cancelled.state == "cancelled" and rig.state().state == "cancelled"
    await rig.pass_time(3600)
    assert len(rig.tnc.sent) == 1
    for number in (1, 99):
        with pytest.raises(MessagingError):
            rig.m.cancel(number)
    await rig.settled()
    assert [m.state for m in await rig.log.recent()] == ["cancelled"]


@pytest.mark.parametrize("how", ["failed", "rejected", "cancelled"])
async def test_retry_sends_a_message_that_did_not_get_through_again_with_the_schedule_from_the_start(rig: Rig, how: str) -> None:
    await rig.m.send("OH2RDG", "Hello")
    if how == "cancelled":
        rig.m.cancel(1)
    elif how == "rejected":
        rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", rej="01"))
    else:
        for step in RUN_OUT:
            await rig.pass_time(step)
    assert rig.state().state == how
    before = len(rig.tnc.sent)
    again = rig.m.retry(1)
    assert (again.state, again.attempts, again.msg_id, again.acked_at) == ("sending", 1, "01", None) and len(rig.tnc.sent) == before + 1
    await rig.pass_time(29)
    assert len(rig.tnc.sent) == before + 1
    await rig.pass_time(1)
    assert len(rig.tnc.sent) == before + 2 and rig.state().attempts == 2


async def test_retry_sends_an_unconfirmed_message_again_with_the_count_it_has_and_it_is_unconfirmed_again(rig: Rig) -> None:
    rig.config = replace(rig.config, messages_attempts=2)
    await rig.m.send("OH2RDG", "Hello")
    for step in RUN_OUT:
        await rig.pass_time(step)
    assert rig.state().state == "unconfirmed"
    rig.config = replace(rig.config, messages_attempts=6)
    before = len(rig.tnc.sent)
    again = rig.m.retry(1)
    assert (again.state, again.attempts, again.attempts_max, again.acked_at) == ("sending", 1, 2, None) and len(rig.tnc.sent) == before + 1
    await rig.pass_time(30)
    assert len(rig.tnc.sent) == before + 2
    for step in RUN_OUT:
        await rig.pass_time(step)
    assert rig.state().state == "unconfirmed" and len(rig.tnc.sent) == before + 2
    await rig.settled()
    assert [m.state for m in await rig.log.recent()] == ["unconfirmed"]


async def test_only_a_message_that_did_not_get_through_can_be_sent_again_and_only_one_of_ours(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Hello")
    with pytest.raises(MessagingError, match="sending"):
        rig.m.retry(1)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    with pytest.raises(MessagingError, match="acked"):
        rig.m.retry(1)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "hi", "5"))
    await rig.settled()
    for number in (2, 99):
        with pytest.raises(MessagingError, match="no message"):
            rig.m.retry(number)
        with pytest.raises(MessagingError, match="no message"):
            rig.m.cancel(number)


# ---- delete ---------------------------------------------------------------------------------------------------------------------------------------

async def test_delete_removes_a_message_of_any_kind_from_the_database_the_records_and_the_pages(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "hi", "5"))
    rig.m.on_packet(rig.heard("OH2AAA", "OH2BBB", "overheard", "6"))
    await rig.m.send("OH2RDG", "ours")
    await rig.settled()
    assert len(rig.m.records()) == 3
    rig.removed.clear()
    gone = {m.text: m for m in rig.m.records()}
    for text in ("hi", "overheard"):
        await rig.m.delete(gone[text].id)
        assert rig.removed[-1] == gone[text] and rig.m.get(gone[text].id) is None
    assert [m.text for m in rig.m.records()] == ["ours"]
    await rig.settled()
    assert [m.text for m in await rig.log.recent()] == ["ours"] and await rig.log.recent(overheard=True) == []


async def test_delete_cancels_a_message_that_is_being_sent_first_and_no_attempt_is_made_after_it(rig: Rig) -> None:
    record = await rig.m.send("OH2RDG", "ours")
    rig.changed.clear()
    await rig.m.delete(record.id)
    assert [m.state for m in rig.changed] == ["cancelled"] and rig.removed[-1].state == "cancelled" and rig.m.records() == []
    await rig.pass_time(3600)
    assert len(rig.tnc.sent) == 1 and rig.m.records() == []
    await rig.settled()
    assert await rig.log.recent() == []
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    assert rig.m.records() == [], "an ack for a message that is gone settles nothing"


async def test_delete_of_a_message_there_is_not_is_refused_and_so_is_one_the_database_would_not_remove(rig: Rig) -> None:
    with pytest.raises(MessagingError, match="no message 7"):
        await rig.m.delete(7)
    record = await rig.m.send("OH2RDG", "ours")
    await rig.m.delete(record.id)
    with pytest.raises(MessagingError, match="no message 1"):
        await rig.m.delete(record.id)
    kept = await rig.m.send("OH2RDG", "kept")
    rig.log.db = None
    with pytest.raises(MessagingError, match="could not be removed"):
        await rig.m.delete(kept.id)
    assert rig.m.get(kept.id) is not None and rig.state(kept.id).state == "cancelled", "what the database still has is what is held"


async def test_delete_conversation_removes_every_message_with_the_station_and_nothing_else(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "hi", "5"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2AAA", "overheard from him", "6"))
    rig.m.on_packet(rig.heard("OH2AAA", "OH2RDG", "overheard to him", "7"))
    rig.m.on_packet(rig.heard("OH2AAA", "OH2GBA", "other friend", "8"))
    await rig.m.send("OH2RDG", "ours")
    await rig.m.send("OH2AAA", "ours to the other")
    await rig.settled()
    await rig.prefs.set_path("OH2RDG", "OH2RCH-2")
    await rig.prefs.set_timeout("OH2RDG", 30)
    rig.removed.clear()
    assert await rig.m.delete_conversation("oh2rdg") == 2
    assert sorted(m.text for m in rig.removed) == ["hi", "ours"]
    assert sorted(m.text for m in rig.m.records()) == ["other friend", "ours to the other", "overheard from him", "overheard to him"]
    await rig.settled()
    assert sorted(m.text for m in await rig.log.recent()) == ["other friend", "ours to the other"]
    assert sorted(m.text for m in await rig.log.recent(overheard=True)) == ["overheard from him", "overheard to him"]
    assert rig.prefs.path_for("OH2RDG") == ("OH2RCH-2",) and rig.prefs.timeout_for("OH2RDG") == 30, "the path and the timeout are the station's, not the conversation's"


async def test_delete_conversation_stops_the_messages_being_sent_and_goes_by_the_peer_not_by_the_records(rig: Rig) -> None:
    record = await rig.m.send("OH2RDG", "ours")
    await rig.m.send("OH2RDG-7", "another ssid")
    rig.changed.clear()
    assert await rig.m.delete_conversation("OH2RDG") == 1
    assert [m.state for m in rig.changed] == ["cancelled"] and rig.removed[-1].id == record.id and [m.text for m in rig.m.records()] == ["another ssid"]
    sent = len(rig.tnc.sent)
    await rig.pass_time(3600)
    assert len(rig.tnc.sent) > sent and not any("::OH2RDG   :" in line for line in rig.tnc.lines()[sent:]), "the other station's message goes on, the conversation's does not"
    await rig.settled()
    assert [m.text for m in await rig.log.recent()] == ["another ssid"]
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    assert [m.text for m in rig.m.records()] == ["another ssid"], "an ack for a message that is gone settles nothing"


async def test_delete_conversation_of_a_station_there_is_no_conversation_with_is_refused_and_so_is_a_database_that_would_not(rig: Rig) -> None:
    with pytest.raises(MessagingError, match="no conversation with OH2RDG"):
        await rig.m.delete_conversation("OH2RDG")
    with pytest.raises(MessagingError):
        await rig.m.delete_conversation("not a call")
    rig.m.on_packet(rig.heard("OH2AAA", "OH2BBB", "overheard", "6"))
    await rig.settled()
    with pytest.raises(MessagingError, match="no conversation with OH2AAA"):
        await rig.m.delete_conversation("OH2AAA")
    kept = await rig.m.send("OH2RDG", "kept")
    rig.log.db = None
    with pytest.raises(MessagingError, match="could not be removed"):
        await rig.m.delete_conversation("OH2RDG")
    assert rig.state(kept.id).state == "cancelled" and len(rig.m.records()) == 2, "what the database still has is what is held"


async def test_delete_conversation_reaches_the_messages_older_than_the_window_the_daemon_holds(rig: Rig) -> None:
    for n in range(3):
        rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", f"old {n}", str(n)))
    await rig.settled()
    for record in rig.m.records()[:2]:
        rig.m._records.pop(record.id)                                       # (the window moved on: these are in the database only)
    assert await rig.m.delete_conversation("OH2RDG") == 3
    assert rig.m.records() == [] and await rig.log.recent() == []


async def test_delete_overheard_removes_the_messages_of_that_pair_only(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2AAA", "OH2BBB", "first", "1"))
    rig.m.on_packet(rig.heard("OH2AAA", "OH2BBB", "second", "2"))
    rig.m.on_packet(rig.heard("OH2BBB", "OH2AAA", "the other way", "3"))
    rig.m.on_packet(rig.heard("OH2AAA", "OH2CCC", "another addressee", "4"))
    rig.m.on_packet(rig.heard("OH2AAA", "OH2GBA", "to us", "5"))
    await rig.m.send("OH2AAA", "ours to him")
    await rig.settled()
    rig.removed.clear()
    assert await rig.m.delete_overheard(" OH2AAA ", "OH2BBB") == 2
    assert sorted(m.text for m in rig.removed) == ["first", "second"]
    assert sorted(m.text for m in rig.m.records()) == ["another addressee", "ours to him", "the other way", "to us"]
    await rig.settled()
    assert sorted(m.text for m in await rig.log.recent(overheard=True)) == ["another addressee", "the other way"]
    assert sorted(m.text for m in await rig.log.recent()) == ["ours to him", "to us"], "a conversation is not touched"


async def test_delete_overheard_of_a_pair_there_is_none_of_is_refused_and_so_is_a_database_that_would_not(rig: Rig) -> None:
    with pytest.raises(MessagingError, match="no overheard message from OH2AAA to OH2BBB"):
        await rig.m.delete_overheard("OH2AAA", "OH2BBB")
    rig.m.on_packet(rig.heard("OH2AAA", "OH2GBA", "to us", "5"))
    await rig.m.send("OH2AAA", "ours")
    await rig.settled()
    with pytest.raises(MessagingError, match="no overheard message"):
        await rig.m.delete_overheard("OH2AAA", "OH2GBA")
    with pytest.raises(MessagingError, match="no overheard message"):
        await rig.m.delete_overheard("OH2GBA", "OH2AAA")
    rig.m.on_packet(rig.heard("OH2AAA", "OH2BBB", "overheard", "6"))
    await rig.settled()
    rig.log.db = None
    with pytest.raises(MessagingError, match="could not be removed"):
        await rig.m.delete_overheard("OH2AAA", "OH2BBB")
    assert len(rig.m.records()) == 3, "what the database still has is what is held"


# ---- the radio away -------------------------------------------------------------------------------------------------------------------------------

async def test_with_the_tnc_away_the_message_is_kept_its_attempt_waits_and_the_log_says_so_once(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.messaging")
    rig.tnc.state = Source.State.WAITING
    record = await rig.m.send("OH2RDG", "Hello Pekka")
    assert (record.state, record.attempts, record.last_attempt_at) == ("sending", 0, None) and rig.tnc.sent == []
    for _ in range(5):
        await rig.pass_time(600)
    assert rig.state().attempts == 0 and rig.tnc.sent == []
    assert len([r for r in caplog.records if "TNC is not connected" in r.getMessage()]) == 1
    rig.tnc.state = Source.State.CONNECTED
    await until(lambda: rig.state().attempts == 1)
    assert rig.tnc.lines() == [WORKED], "the first attempt goes out when the radio is back, and is the first of six"
    await rig.pass_time(30)
    assert rig.state().attempts == 2


async def test_with_the_radio_silent_a_message_is_refused_and_one_that_was_sent_waits_and_resumes_when_the_radio_answers(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.messaging")
    await rig.m.send("OH2RDG", "Hello Pekka")
    await rig.pass_time(20)
    await rig.radio(Source.State.SILENT)
    with pytest.raises(MessagingError, match="^the radio is silent$"):
        await rig.m.send("OH2RDG", "Another")
    assert len(rig.m.records()) == 1
    for _ in range(5):
        await rig.pass_time(600)
    assert len(rig.tnc.sent) == 1 and rig.state().attempts == 1 and rig.state().state == "sending", "no attempt is used up"
    assert len([r for r in caplog.records if "the radio is silent" in r.getMessage()]) == 1
    await rig.radio(Source.State.CONNECTED)
    await rig.pass_time(9)
    assert len(rig.tnc.sent) == 1, "the waits that were running did not run while the radio was silent"
    await rig.pass_time(2)
    assert len(rig.tnc.sent) == 2 and rig.state().attempts == 2


async def test_the_waits_that_were_running_do_not_run_while_the_radio_is_away(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Hello")
    await rig.pass_time(20)
    await rig.radio(Source.State.WAITING)
    await rig.pass_time(500)
    assert len(rig.tnc.sent) == 1
    await rig.radio(Source.State.CONNECTED)
    await rig.pass_time(9)
    assert len(rig.tnc.sent) == 1, "the radio was away for 500 s: the 10 seconds that were left are still to come"
    await rig.pass_time(2)
    assert len(rig.tnc.sent) == 2


async def test_the_last_wait_does_not_run_out_while_the_radio_is_away(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Hello")
    for step in RUN_OUT[:-1]:
        await rig.pass_time(step)
    assert rig.state().attempts == 6
    await rig.radio(Source.State.WAITING)
    await rig.pass_time(3600)
    assert rig.state().state == "sending"
    await rig.radio(Source.State.CONNECTED)
    await rig.pass_time(1)
    assert rig.state().state == "sending"
    await rig.pass_time(240)
    assert rig.state().state == "failed"


async def test_a_tnc_that_will_not_take_the_frame_is_not_an_attempt_and_is_tried_at_the_next_tick(rig: Rig) -> None:
    rig.tnc.takes = False
    record = await rig.m.send("OH2RDG", "Hello")
    assert record.attempts == 0
    await asyncio.sleep(TICK * 5)
    assert rig.state().attempts == 0
    rig.tnc.takes = True
    await until(lambda: rig.state().attempts == 1)


# ---- messages that come in ------------------------------------------------------------------------------------------------------------------------

async def test_a_message_to_us_is_kept_and_answered_at_once_with_an_ack(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", "Moi!", "12"))
    assert rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG-7 :ack12"], "the ack is on the air before the message is on the disk"
    [frame] = rig.tnc.sent
    assert frame.info == b":OH2RDG-7 :ack12"
    await rig.settled()
    [record] = rig.m.records()
    assert record == MessageRecord(1, rig.clock(), "in", "OH2RDG-7", "OH2GBA", "Moi!", "12", "received", route="via ? → OH2RCH-2")
    assert await rig.log.recent() == [record] and rig.changed == [record]


async def test_a_message_without_an_id_is_kept_and_not_acked_and_a_copy_of_it_within_half_an_hour_is_not_kept_again(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "no id"))
    await rig.settled()
    assert rig.tnc.sent == [] and [(m.text, m.msg_id) for m in rig.m.records()] == [("no id", None)]
    rig.clock.advance(1)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "no id"))                  # (the second digipeater's copy)
    await rig.settled()
    assert len(rig.m.records()) == 1 and rig.tnc.sent == [], "the same sender, addressee and text within half an hour is one message"
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "another text"))
    rig.m.on_packet(rig.heard("OH2XYZ", "OH2GBA", "no id"))
    await rig.settled()
    assert len(rig.m.records()) == 3
    rig.clock.advance(31 * 60)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "no id"))
    await rig.settled()
    assert [m.text for m in rig.m.records()] == ["no id", "another text", "no id", "no id"]


async def test_a_message_is_ours_only_to_our_call_with_its_ssid_and_not_to_our_base_call_or_another_ssid(rig: Rig) -> None:
    rig.config = replace(rig.config, station_call="OH2GBA-7")
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "to the base call", "1"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA-7", "to us", "2"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA-9", "to another", "3"))
    await rig.settled()
    assert [m.text for m in rig.m.records() if m.state == "received"] == ["to us"]
    assert [m.text for m in rig.m.records() if m.state == "overheard"] == ["to the base call", "to another"]
    assert [f.info for f in rig.tnc.sent] == [b":OH2RDG   :ack2"], "the ones to another call are overheard, and not acked"
    rig.config = replace(rig.config, station_call="OH2GBA")
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA-0", "zero is none", "4"))
    assert rig.tnc.sent[-1].info == b":OH2RDG   :ack4"
    assert rig.tnc.lines()[0].startswith("OH2GBA-7>APZNEO")


async def test_a_message_of_our_own_call_or_sent_by_us_is_nothing_to_messaging(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2GBA", "OH2GBA", "from ourselves", "2"))
    rig.m.on_packet(rig.heard("OH2GBA", "OH2RDG", "what we sent, heard back", "3"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "ours but our own", "4", direction="out"))
    await rig.settled()
    assert rig.tnc.sent == [] and rig.m.records() == [] and await rig.log.recent() == [] and await rig.log.recent(overheard=True) == []


async def test_a_packet_that_is_no_message_is_nothing_to_messaging(rig: Rig) -> None:
    from neoaprs.packet import Status
    rig.m.on_packet(Packet(rig.clock(), "in", b"", "OH2RDG", "APRS", (), b">hi", Status("hi")))
    assert rig.tnc.sent == [] and rig.m.records() == []


async def test_a_repeat_within_half_an_hour_is_acked_again_and_not_kept_again(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    rig.clock.advance(60)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    rig.clock.advance(28 * 60)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    await rig.settled()
    assert len(rig.tnc.sent) == 3 and set(rig.tnc.lines()) == {"OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :ack12"}
    assert len(rig.m.records()) == 1 and len(await rig.log.recent()) == 1
    rig.clock.advance(60)                                           # (30 minutes after the first)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    await rig.settled()
    assert len(rig.tnc.sent) == 4 and len(rig.m.records()) == 2, "after half an hour the same id is a new message"


async def test_the_copies_of_a_message_within_ten_seconds_get_one_ack_between_them(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.messaging")
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))                  # (by way of the first digipeater)
    rig.clock.advance(3)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))                  # (by way of the second)
    rig.clock.advance(3)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))                  # (the internet copy, an iGate's)
    await rig.settled()
    assert rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :ack12"] and len(rig.m.records()) == 1
    assert sum("not acked again" in r.getMessage() for r in caplog.records) == 2, "the copies that were not answered are noted in the log"


async def test_a_copy_more_than_ten_seconds_after_our_last_ack_is_acked_again_and_ten_seconds_is_not_enough(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    rig.clock.advance(10)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    assert len(rig.tnc.sent) == 1, "exactly ten seconds is not more than ten seconds"
    rig.clock.advance(1)                                                          # (11 s after the first ack)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    assert len(rig.tnc.sent) == 2
    rig.clock.advance(5)                                                          # (the ten seconds count from the last ack, not from the first)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    assert len(rig.tnc.sent) == 2
    rig.clock.advance(6)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    await rig.settled()
    assert len(rig.tnc.sent) == 3 and len(rig.m.records()) == 1


async def test_a_copy_after_half_an_hour_is_a_new_message_and_is_acked(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    rig.clock.advance(5)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    rig.clock.advance(31 * 60)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    await rig.settled()
    assert len(rig.tnc.sent) == 2 and len(rig.m.records()) == 2


async def test_a_copy_an_igate_put_on_the_air_within_ten_seconds_of_our_ack_is_not_acked_and_one_after_them_is(rig: Rig) -> None:
    gated = replace(rig.heard("OH7JHF-1", "OH2GBA", "Moi!", "12"), source="OH7JHF-1", third_party=ThirdParty("OH2RDG", "APRS", ("TCPIP", "OH7JHF-1*")))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    rig.clock.advance(4)
    rig.m.on_packet(replace(gated, heard_at=rig.clock()))
    assert len(rig.tnc.sent) == 1, "the sender inside the frame is the same station: the same message"
    rig.clock.advance(7)
    rig.m.on_packet(replace(gated, heard_at=rig.clock()))
    await rig.settled()
    assert len(rig.tnc.sent) == 2 and len(rig.m.records()) == 1 and rig.m.records()[0].route == "via ? → OH2RCH-2"


async def test_a_message_without_an_id_is_never_acked_whatever_the_time(rig: Rig) -> None:
    for seconds in (0, 5, 60, 31 * 60):
        rig.clock.advance(seconds)
        rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "no id"))
    await rig.settled()
    assert rig.tnc.sent == [] and len(rig.m.records()) == 2


async def test_the_time_of_the_last_ack_is_kept_for_each_message_and_each_sender(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "a", "12"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "b", "13"))
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", "c", "12"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "a", "12"))
    assert [f.info for f in rig.tnc.sent] == [b":OH2RDG   :ack12", b":OH2RDG   :ack13", b":OH2RDG-7 :ack12"]


async def test_the_same_id_from_another_station_or_another_id_from_the_same_one_is_a_new_message(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "a", "12"))
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", "b", "12"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "c", "13"))
    await rig.settled()
    assert [m.text for m in rig.m.records()] == ["a", "b", "c"]


async def test_after_a_restart_a_repeat_of_a_message_that_was_kept_is_acked_and_not_kept_again(rig: Rig, another: Callable[..., Rig]) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    await rig.settled()
    await rig.m.stop()
    restarted = another()
    await restarted.start()
    restarted.m.on_packet(restarted.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    await restarted.settled()
    assert len(restarted.tnc.sent) == 2 and len(restarted.m.records()) == 1 and len(await rig.log.recent()) == 1
    await restarted.m.stop()


async def test_an_ack_that_cannot_be_sent_is_told_and_the_message_is_kept_all_the_same(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.messaging")
    rig.tnc.takes = False
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi!", "12"))
    await rig.settled()
    assert len(rig.m.records()) == 1 and any("ack of message 12" in r.getMessage() for r in caplog.records)


async def test_a_conversation_goes_both_ways_in_one_table(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Moi")
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi moi", "A1"))
    await rig.settled()
    assert [(m.direction, m.state, m.peer) for m in await rig.log.recent()] == [("in", "received", "OH2RDG"), ("out", "acked", "OH2RDG")]


# ---- keeping and telling --------------------------------------------------------------------------------------------------------------------------

async def test_every_new_or_changed_message_is_told_with_the_message_as_it_is(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Moi")
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    assert [(r.id, r.state, r.attempts) for r in rig.changed] == [(1, "sending", 0), (1, "sending", 1), (1, "acked", 1)]


async def test_no_message_is_dropped_by_count_or_by_age_and_a_message_being_sent_stays(rig: Rig) -> None:
    first = await rig.m.send("OH2RDG", "pending")
    for n in range(700):
        rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", f"in {n}", str(n)))
        if n % 100 == 99:
            await rig.settled()
    rig.clock.advance(86400 * 400)
    await rig.settled()
    assert first.id == 1 and len(rig.m.records()) == 701 and rig.removed == []
    assert len(await rig.log.recent(1000)) == 701


async def test_a_start_holds_every_message_the_database_has_old_ones_and_overheard_ones_too(rig: Rig, another: Callable[..., Rig]) -> None:
    old = rig.clock() - timedelta(days=400)
    for text, state, direction in (("old out", "acked", "out"), ("old in", "received", "in"), ("old chatter", "overheard", "in"), ("old pending", "sending", "out")):
        await rig.log.insert(MessageRecord(0, old, direction, "OH2GBA" if direction == "out" else "OH2XYZ", "OH2RDG" if direction == "out" else "OH2GBA", text, "7", state))  # type: ignore[arg-type]
    await rig.m.stop()
    restarted = another()
    await restarted.start()
    assert sorted(m.text for m in restarted.m.records()) == ["old chatter", "old in", "old out", "old pending"]
    await restarted.m.stop()


async def test_a_database_with_more_than_the_most_gives_the_latest_and_a_warning(rig: Rig, another: Callable[..., Rig], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    for n in range(5):
        await rig.log.insert(MessageRecord(0, rig.clock(), "in", "OH2XYZ", "OH2GBA", f"m{n}", str(n), "received"))
    await rig.m.stop()
    monkeypatch.setattr(messaging_module, "MESSAGES_HELD_MAX", 3)
    caplog.set_level(logging.WARNING, "neoaprs.messaging")
    restarted = another()
    await restarted.start()
    assert [m.text for m in restarted.m.records()] == ["m2", "m3", "m4"]
    assert any("3 messages or more" in r.getMessage() for r in caplog.records)
    await restarted.m.stop()


async def test_the_daily_care_forgets_the_memory_of_old_hearings_but_no_message(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2XYZ", "OH2GBA", "old in", "3"))
    await rig.settled()
    rig.clock.advance(86400 * 40)
    rig.m.forget_heard(30)
    rig.m.on_packet(rig.heard("OH2XYZ", "OH2GBA", "old in", "3"))
    await rig.settled()
    assert len(rig.m.records()) == 2 and rig.removed == [], "the repeat of a message forgotten long ago is a new message; the first stays"


async def test_a_restart_goes_on_with_the_schedule_of_the_messages_that_were_being_sent(rig: Rig, another: Callable[..., Rig]) -> None:
    await rig.m.send("OH2RDG", "Hello")
    await rig.pass_time(31)
    assert len(rig.tnc.sent) == 2
    await rig.settled()
    await rig.m.stop()
    rig.tnc.sent.clear()
    restarted = another()
    await restarted.start()
    assert [(m.id, m.state, m.attempts) for m in restarted.m.records()] == [(1, "sending", 2)]
    await restarted.pass_time(28)
    assert restarted.tnc.sent == []
    await restarted.pass_time(30)
    assert len(restarted.tnc.sent) == 1 and restarted.state().attempts == 3, "the third attempt is due 60 s after the first"
    await restarted.m.stop()


async def test_a_message_that_was_waiting_for_the_radio_when_the_daemon_stopped_is_sent_after_the_start(rig: Rig, another: Callable[..., Rig]) -> None:
    rig.tnc.state = Source.State.WAITING
    await rig.m.send("OH2RDG", "Hello Pekka")
    await rig.settled()
    await rig.m.stop()
    restarted = another()
    restarted.tnc.state = Source.State.CONNECTED
    await restarted.start()
    await until(lambda: restarted.state().attempts == 1)
    assert restarted.tnc.lines() == [WORKED]
    await restarted.m.stop()


async def test_start_twice_starts_one_ticker_and_stop_twice_is_harmless(rig: Rig) -> None:
    await rig.start()
    await rig.m.send("OH2RDG", "Hello")
    await rig.pass_time(31)
    assert len(rig.tnc.sent) == 2
    await rig.m.stop()
    await rig.m.stop()
    await rig.pass_time(3600)
    assert len(rig.tnc.sent) == 2


async def test_a_message_that_came_in_just_before_the_stop_is_kept(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "last words", "9"))
    await rig.m.stop()
    assert rig.log.db is not None
    await rig.log.db.barrier()
    assert [m.text for m in await rig.log.recent()] == ["last words"]


# ---- the path of each station ---------------------------------------------------------------------------------------------------------------------

async def test_a_message_goes_by_way_of_the_path_of_its_station_and_the_others_by_the_beacon_path(rig: Rig) -> None:
    await rig.prefs.set_path("OH2RDG", "OH2RCH-2,WIDE2-1")
    await rig.prefs.set_path("OH2DIR", "")
    await rig.m.send("OH2RDG", "a")
    await rig.m.send("OH2DIR", "b")
    await rig.m.send("OH2XYZ", "c")
    assert rig.tnc.lines() == ["OH2GBA>APZNEO,OH2RCH-2,WIDE2-1::OH2RDG   :a{01}", "OH2GBA>APZNEO::OH2DIR   :b{02}", "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2XYZ   :c{03}"]


async def test_the_attempts_and_a_retry_use_the_path_the_station_has_then(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "a")
    await rig.prefs.set_path("OH2RDG", "WIDE2-2")
    await rig.pass_time(31)
    assert rig.tnc.sent[-1].path_text == "WIDE2-2"
    rig.m.cancel(1)
    await rig.prefs.clear_path("OH2RDG")
    rig.m.retry(1)
    assert rig.tnc.sent[-1].path_text == "WIDE1-1,WIDE2-1"


async def test_the_ack_goes_by_way_of_the_remembered_path_of_the_station_and_by_the_beacon_path_otherwise(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", "one", "1"))
    assert rig.tnc.lines()[-1] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG-7 :ack1"
    await rig.prefs.set_path("OH2RDG-7", "OH2RCH-2,WIDE2-1")
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", "two", "2"))
    rig.m.on_packet(rig.heard("OH2XYZ", "OH2GBA", "three", "3"))
    assert rig.tnc.lines()[-2:] == ["OH2GBA>APZNEO,OH2RCH-2,WIDE2-1::OH2RDG-7 :ack2", "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2XYZ   :ack3"]
    await rig.prefs.set_path("OH2RDG-7", "")
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", "four", "4"))
    assert rig.tnc.lines()[-1] == "OH2GBA>APZNEO::OH2RDG-7 :ack4", "direct is a path too"
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "five", "5"))
    assert rig.tnc.lines()[-1] == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG   :ack5", "the path is of the station and its SSID"


async def test_a_repeat_is_acked_again_by_the_path_it_has_then_and_kept_once(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi", "9"))
    await rig.prefs.set_path("OH2RDG", "WIDE2-2")
    rig.clock.advance(120)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "Moi", "9"))
    await rig.settled()
    assert [f.path_text for f in rig.tnc.sent] == ["WIDE1-1,WIDE2-1", "WIDE2-2"] and len([m for m in rig.m.records() if m.state == "received"]) == 1


async def test_an_ack_goes_out_for_every_distinct_message_to_us_that_has_an_id_and_for_none_that_has_not(rig: Rig) -> None:
    for n, (source, msg_id) in enumerate([("OH2RDG", "1"), ("OH2RDG", "2"), ("OH2XYZ", "1"), ("OH2RDG", None)]):
        rig.m.on_packet(rig.heard(source, "OH2GBA", f"text {n}", msg_id))
    await rig.settled()
    assert [f.info for f in rig.tnc.sent] == [b":OH2RDG   :ack1", b":OH2RDG   :ack2", b":OH2XYZ   :ack1"] and len(rig.m.records()) == 4


# ---- messages we only overhear --------------------------------------------------------------------------------------------------------------------

async def test_a_message_to_another_station_is_kept_as_overheard_and_never_acked(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2XYZ", "not for us", "3"))
    await rig.settled()
    assert rig.tnc.sent == []
    [record] = rig.m.records()
    assert record == MessageRecord(1, rig.clock(), "in", "OH2RDG", "OH2XYZ", "not for us", "3", "overheard", route="via ? → OH2RCH-2")
    assert await rig.log.recent() == [] and await rig.log.recent(overheard=True) == [record] and rig.changed == [record]


async def test_a_repeat_of_an_overheard_message_is_kept_once_within_half_an_hour_and_one_without_an_id_by_its_text(rig: Rig) -> None:
    for text, msg_id in (("a", "3"), ("a", "3"), ("b", None), ("b", None), ("c", "4"), ("a", "4")):
        rig.m.on_packet(rig.heard("OH2RDG", "OH2XYZ", text, msg_id))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2ABC", "a", "3"))
    rig.m.on_packet(rig.heard("OH2AAA", "OH2XYZ", "a", "3"))
    await rig.settled()
    assert [(m.from_call, m.to_call, m.text, m.msg_id) for m in rig.m.records()] == [
        ("OH2RDG", "OH2XYZ", "a", "3"), ("OH2RDG", "OH2XYZ", "b", None), ("OH2RDG", "OH2XYZ", "c", "4"), ("OH2RDG", "OH2XYZ", "a", "4"), ("OH2RDG", "OH2ABC", "a", "3"),
        ("OH2AAA", "OH2XYZ", "a", "3")]
    rig.clock.advance(31 * 60)
    rig.m.on_packet(rig.heard("OH2RDG", "OH2XYZ", "a", "3"))
    await rig.settled()
    assert len(rig.m.records()) == 7


async def test_the_acks_and_rejects_between_other_stations_are_not_messages_and_are_not_kept(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2XYZ", "OH2RDG", ack="3"))
    rig.m.on_packet(rig.heard("OH2XYZ", "OH2RDG", rej="3"))
    await rig.settled()
    assert rig.m.records() == [] and rig.tnc.sent == []


@pytest.mark.parametrize("addressee", ["BLN1", "BLN9", "BLNA", "BLNZ", "BLN3HAMS", "ALL", "CQ", "QST"])
async def test_a_message_to_a_bulletin_or_a_group_goes_to_the_board_and_is_neither_overheard_nor_acked_though_it_carries_an_id(rig: Rig, addressee: str) -> None:
    packet = rig.heard("OH2RDG", addressee, "net tonight 20:00", "7")
    rig.m.on_packet(packet)
    await rig.settled()
    assert rig.board == [(packet, Message(addressee, "net tonight 20:00", "7"))]
    assert rig.m.records() == [] and rig.tnc.sent == [] and await rig.log.recent(overheard=True) == [] and rig.changed == []


async def test_an_ack_or_a_reject_to_a_bulletin_is_nothing_and_a_message_to_a_station_is_not_the_boards(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "BLN1", ack="7"))
    rig.m.on_packet(rig.heard("OH2RDG", "QST", rej="7"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2XYZ", "hello"))
    await rig.settled()
    assert rig.board == [] and [m.to_call for m in rig.m.records()] == ["OH2XYZ"]


async def test_a_message_we_hear_from_ourselves_to_a_bulletin_is_not_the_boards(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2GBA", "BLN1", "echo"))
    assert rig.board == []


async def test_without_a_board_a_message_to_a_bulletin_is_overheard(rig: Rig) -> None:
    alone = Messaging(rig.tnc, lambda: rig.config, rig.log, rig.prefs.path_for, rig.clock, tick_sec=TICK, spacing_sec=0.0)
    remember_stop(alone.stop)
    alone.on_packet(rig.heard("OH2RDG", "BLN1", "net tonight 20:00"))
    await asyncio.gather(*alone.inbox.tasks)
    assert [(m.to_call, m.state) for m in alone.records()] == [("BLN1", "overheard")]


async def test_overheard_messages_are_not_limited_and_push_out_nothing(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "ours 1", "1"))
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", "ours 2", "2"))
    await rig.settled()
    for n in range(260):
        rig.m.on_packet(rig.heard("OH2AAA", "OH2BBB", f"chatter {n}", str(n)))
        if n % 50 == 49:
            await rig.settled()
    await rig.settled()
    assert len(rig.m.records()) == 262 and rig.removed == []
    assert len(await rig.log.recent(overheard=True, count=1000)) == 260


async def test_after_a_restart_the_overheard_messages_are_there_and_a_repeat_is_not_kept_again(rig: Rig, another: Callable[..., Rig]) -> None:
    rig.m.on_packet(rig.heard("OH2RDG", "OH2XYZ", "not for us", "3"))
    await rig.settled()
    await rig.m.stop()
    restarted = another()
    await restarted.start()
    assert [m.state for m in restarted.m.records()] == ["overheard"]
    restarted.m.on_packet(restarted.heard("OH2RDG", "OH2XYZ", "not for us", "3"))
    await restarted.settled()
    assert len(restarted.m.records()) == 1 and len(await rig.log.recent(overheard=True)) == 1
    await restarted.m.stop()


async def test_every_change_of_a_message_we_sent_and_the_ack_that_settles_it_are_in_the_database(rig: Rig) -> None:
    await rig.m.send("OH2RDG", "Hello")
    await rig.pass_time(31)
    await rig.settled()
    assert [(m.state, m.attempts) for m in await rig.log.recent()] == [("sending", 2)]
    rig.m.on_packet(rig.heard("OH2RDG", "OH2GBA", ack="01"))
    await rig.settled()
    [row] = await rig.log.recent()
    assert (row.state, row.attempts, row.acked_at) == ("acked", 2, rig.clock())


async def test_a_call_that_is_none_cannot_have_its_path_cleared(rig: Rig) -> None:
    with pytest.raises(MessagingError, match="call"):
        await rig.prefs.clear_path("TOOLONGCALL")
