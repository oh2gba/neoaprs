"""The retry ticker of messages being sent (neoaprs/services/retries.py) on stub radios and a held
clock: an attempt goes when it is due, waits while its radio or every radio is away or the station
may not send, and the time a radio was away moves on the waits of its messages."""

import asyncio
import logging
from dataclasses import replace
from datetime import timedelta

import pytest

from neoaprs.config import RECEIVE_ONLY, Config
from neoaprs.interlock import Interlock
from neoaprs.message import MessageRecord
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.services.radioset import AirRadio
from neoaprs.services.retries import Retries
from neoaprs.source import Source
from tests.support.clock import FixedClock
from tests.support.env import until
from tests.test_radio_of_frame import BOTH, Host, record, two

WAIT_SEC = 32


class NoRadio(Host):
    """A host whose messages have no radio now (the email gateway with no email radio)."""

    def radio_of(self, record: MessageRecord) -> AirRadio | None:
        return None


class Station:
    """Radio 1 and radio 2 on stub lines, the messages given, the settings `config` (changeable)."""

    def __init__(self, *records: MessageRecord, host: type[Host] = Host, clock: FixedClock | None = None) -> None:
        self.config: Config = BOTH
        given, radios, self.lines = two(BOTH, False)
        self.radios = radios
        self.clock = clock or FixedClock()
        self.host = host(radios, list(records))
        self.flushed: list[int] = []
        self.retries = Retries(
            self.host,
            given,
            lambda: self.config,
            Interlock(lambda: self.config),
            self.clock,
            lambda: 0.01,
            lambda: self.flushed.append(1),
        )
        for r in records:
            self.retries.plan(r)

    def to(self, number: int, after_sec: float = 0) -> None:
        """Move the clock to the moment message `number` is due, plus `after_sec`."""
        self.clock.set(self.retries._due[number] + timedelta(seconds=after_sec))

    def away(self, *ids: int) -> None:
        for id in (FM_ID, HF_ID):
            self.lines[id].state = Source.State.SILENT if id in ids else Source.State.CONNECTED


def test_a_message_is_attempted_at_the_moment_it_is_due_and_not_before() -> None:
    s = Station(record(1, "OH2B", FixedClock()()))
    s.to(1, -0.001)
    s.retries.tick()
    assert s.host.attempted == []
    s.to(1)
    s.retries.tick()
    assert s.host.attempted == [1] and s.flushed == [1, 1]


def test_with_every_radio_away_a_due_message_is_told_once_with_the_reason_and_the_acks_wait(
    caplog: pytest.LogCaptureFixture,
) -> None:
    s = Station(record(1, "OH2B", FixedClock()()))
    s.away(FM_ID, HF_ID)
    with caplog.at_level(logging.WARNING, "neoaprs.messaging"):
        s.to(1, -0.001)
        s.retries.tick()
        assert caplog.records == [], "nothing is due yet"
        s.to(1)
        s.retries.tick()
        s.retries.tick()
    why = s.radios.get(FM_ID).why_unusable()  # type: ignore[union-attr]
    assert [r.getMessage() for r in caplog.records] == [
        f"a message is waiting and {why}: its attempts wait for the radio (none is used up)"
    ]
    assert s.host.attempted == [] and s.flushed == [], "the acks that wait for a radio are not flushed into none"


def test_a_message_that_has_no_radio_now_waits_and_is_told_once_by_its_number_and_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    s = Station(record(1, "OH2B", FixedClock()()), host=NoRadio)
    with caplog.at_level(logging.WARNING, "neoaprs.messaging"):
        s.to(1)
        s.retries.tick()
        s.retries.tick()
    assert [r.getMessage() for r in caplog.records] == ["message 1 to OH2B waits: it has no radio to go on now"]
    assert s.host.attempted == []


def test_a_message_with_no_radio_waits_its_plain_time_with_no_pause() -> None:
    at = FixedClock()()
    s = Station(record(1, "OH2B", at), host=NoRadio)
    assert s.retries._due[1] == at + timedelta(seconds=WAIT_SEC)


def test_receive_only_attempts_nothing_and_the_interlock_says_so_once(caplog: pytest.LogCaptureFixture) -> None:
    s = Station(record(1, "OH2B", FixedClock()()))
    s.config = replace(BOTH, station_transmit=False)
    with caplog.at_level(logging.WARNING, "neoaprs.interlock"):
        s.to(1)
        s.retries.tick()
        s.retries.tick()
    assert s.host.attempted == [] and s.flushed == []
    assert [r.getMessage() for r in caplog.records if r.name == "neoaprs.interlock"] == [
        f"no message sent: {RECEIVE_ONLY}"
    ]


def test_the_time_the_station_may_not_send_moves_on_the_waits_as_a_radio_away_does() -> None:
    at = FixedClock()()
    s = Station(record(1, "OH2B", at))
    s.config = replace(BOTH, station_transmit=False)
    s.retries.tick()
    assert s.retries.away(s.radios.get(FM_ID))  # type: ignore[arg-type]
    s.clock.advance(10)
    s.retries.tick()
    s.config = BOTH
    s.retries.tick()
    assert s.retries._due[1] == at + timedelta(seconds=WAIT_SEC + 10)
    assert not s.retries.away(s.radios.get(FM_ID))  # type: ignore[arg-type]


def test_the_time_away_runs_from_the_first_tick_that_found_the_radio_away_to_the_last() -> None:
    at = FixedClock()()
    s = Station(record(1, "OH2B", at))
    s.away(FM_ID)
    for _ in range(3):
        s.retries.tick()
        s.clock.advance(10)
    s.away()
    s.retries.tick()
    assert s.retries._due[1] == at + timedelta(seconds=WAIT_SEC + 20), "away from +0 to +20, seen at three ticks"


def test_a_radio_seen_away_at_one_tick_alone_moves_nothing_and_is_not_told(caplog: pytest.LogCaptureFixture) -> None:
    at = FixedClock()()
    s = Station(record(1, "OH2B", at))
    s.away(FM_ID)
    s.retries.tick()
    s.clock.advance(5)
    s.away()
    with caplog.at_level(logging.DEBUG, "neoaprs.messaging"):
        s.retries.tick()
    assert s.retries._due[1] == at + timedelta(seconds=WAIT_SEC)
    assert not any("takes frames again" in r.getMessage() for r in caplog.records)


def test_the_time_away_moves_on_the_messages_attempted_on_the_radio_and_not_one_waiting_for_its_first() -> None:
    at = FixedClock()()
    s = Station(record(1, "OH2B", at, attempts=0), record(2, "OH2D", at))
    s.away(FM_ID)
    s.retries.tick()
    s.clock.advance(20)
    s.retries.tick()
    s.away()
    s.retries.tick()
    assert s.retries._due[1] == at, "its first attempt is not a wait"
    assert s.retries._due[2] == at + timedelta(seconds=WAIT_SEC + 20)


def test_a_message_that_is_no_longer_being_sent_or_forgotten_is_not_attempted() -> None:
    at = FixedClock()()
    s = Station(record(1, "OH2B", at), record(2, "OH2D", at))
    s.retries.plan(replace(s.host.records[1], state="acked"))
    s.retries.plan(replace(record(3, "OH2E", at), state="acked"))
    s.retries.forget(2)
    s.retries.forget(4)
    s.clock.advance(3600)
    s.retries.tick()
    assert s.host.attempted == []


def test_a_message_too_long_for_its_radio_fails_with_that_reason_and_uses_no_attempt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    s = Station(record(1, "OH2B", FixedClock()()))
    with caplog.at_level(logging.WARNING, "neoaprs.messaging"):
        ended = s.retries.end_too_long(s.host.records[1], ValueError("the frame is 300 bytes, the radio takes 123"))
    assert ended == replace(record(1, "OH2B", FixedClock()()), state="failed", failure="too_long_for_radio")
    assert s.host.records[1] == ended and s.host.attempted == []
    assert [r.getMessage() for r in caplog.records] == [
        "message 1 to OH2B fails: the frame is 300 bytes, the radio takes 123"
    ]


async def test_the_started_ticker_attempts_a_due_message_and_stops() -> None:
    clock = FixedClock()
    s = Station(record(1, "OH2B", clock() - timedelta(seconds=60)), clock=clock)
    assert not s.retries.running
    s.retries.start()
    assert s.retries.running and "messaging" in {task.get_name() for task in asyncio.all_tasks()}
    await until(lambda: s.host.attempted == [1])
    await s.retries.stop()
    assert not s.retries.running and "messaging" not in {task.get_name() for task in asyncio.all_tasks()}
    await s.retries.stop()


@pytest.mark.expects_errors
async def test_a_failing_round_of_the_ticker_is_logged_by_its_name_and_the_ticker_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = FixedClock()
    s = Station(record(1, "OH2B", clock() - timedelta(seconds=60)), clock=clock)
    rounds: list[int] = []

    def fails(number: int) -> MessageRecord | None:
        rounds.append(number)
        raise RuntimeError("boom")

    s.host.get = fails  # type: ignore[method-assign]
    s.retries.start()
    await until(lambda: len(rounds) >= 3)
    await s.retries.stop()
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR] == [
        "the messaging ticker failed: RuntimeError: boom"
    ]
