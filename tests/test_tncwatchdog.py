"""The keep-alive's schedule (neoaprs/tncwatchdog.py) on a Tnc that is a record of what it was asked, and a loop whose time is skipped (tests/support/virtualtime.py): the quiet period before a check, the check's
steps and what each of its exits leaves, the silent state's probes and the reopen of every fifth, and the ways the line can go away between two steps. The Tnc with its real line is in test_tnc.py and test_silent.py."""
import asyncio
from datetime import datetime

import pytest

from neoaprs import tncwatchdog
from neoaprs.clock import utc
from neoaprs.source import Source
from neoaprs.tncprofile import KENWOOD_TNC2, Profile
from neoaprs.tncwatchdog import PROMPT, TncStats, Watchdog, how_long
from tests.support.virtualtime import virtual_time


class WatchedTnc:
    """What the watchdog asks of the Tnc, answered as the test sets it up and written down."""

    def __init__(self, profile: Profile = KENWOOD_TNC2) -> None:
        self.stats = TncStats()
        self.state = Source.State.CONNECTED
        self.confirmed = True
        self.profile = profile
        self.last_watchdog_action = ""
        self.last_watchdog_at: datetime | None = None
        self.calls: list[str] = []
        self.sent: list[bytes] = []
        self.has_line = True
        self.refuses_write_number = 0                     # the nth write is refused (1 is the first); 0: none
        self.alive = True
        self.silent_told: list[str] = []
        self.reopened = 0

    def now(self) -> datetime:
        return utc(2026, 10, 21, 12, 0, 0)

    def look_begin(self) -> bool:
        self.calls.append("begin")
        self.alive = self.alive and self.has_line                   # (a Tnc with no line has no line to watch either)
        return self.has_line

    def look_send(self, data: bytes) -> bool:
        self.sent.append(data)
        accepted = len(self.sent) != self.refuses_write_number
        self.alive = self.alive and accepted                        # (a write that fails loses the line, which is then not the one the watch was started for)
        return accepted

    def look_enter_kiss(self) -> None:
        self.calls.append("kiss on")

    def look_end(self) -> None:
        self.calls.append("end")

    async def reopen_port(self) -> None:
        self.reopened += 1

    def went_silent(self, then: str = "") -> None:
        self.state = Source.State.SILENT
        self.silent_told.append(then)


@pytest.fixture(autouse=True)
def no_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    """The quiet period is exactly `sec` (its random part is tested in test_tncwatchdog_jitter.py)."""
    monkeypatch.setattr(tncwatchdog.random, "uniform", lambda a, b: 0.0)


async def running(dog: Watchdog, tnc: WatchedTnc, check_first: bool = False) -> "asyncio.Task[None]":
    dog.opened()
    return asyncio.create_task(dog.run(lambda: tnc.alive, check_first))


async def end(task: "asyncio.Task[None]") -> None:
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


EXIT = KENWOOD_TNC2.exit_kiss


# ---- the check

async def test_a_line_quiet_for_the_period_is_checked_with_the_exit_frame_a_return_and_kiss_on_in_order() -> None:
    tnc = WatchedTnc()
    dog = Watchdog(tnc, 60.0)
    async with virtual_time():
        task = await running(dog, tnc)
        await asyncio.sleep(59)
        assert tnc.sent == [] and tnc.stats.keepalive_checks == 0, "not before the period is over"
        await asyncio.sleep(1.2)
        assert tnc.sent == [EXIT] and tnc.calls == ["begin"], "the exit frame goes first, then the pause"
        await asyncio.sleep(0.5)
        assert tnc.sent == [EXIT, PROMPT] and tnc.calls == ["begin"], "the return, then it is given its second to be answered"
        await asyncio.sleep(1.0)
        assert tnc.calls == ["begin", "kiss on"]
        await end(task)
    assert tnc.last_watchdog_action == "check" and tnc.stats.keepalive_checks == 1
    assert tnc.calls[-1] == "end", "the Tnc is told the check is over also when it is cut"


async def test_any_byte_in_answer_keeps_the_radio_and_the_next_check_is_a_whole_period_after_the_latest_byte() -> None:
    tnc = WatchedTnc()
    dog = Watchdog(tnc, 60.0)
    async with virtual_time():
        task = await running(dog, tnc)
        await asyncio.sleep(61)
        tnc.stats.bytes_in += 1                                      # the radio typed "cmd:"
        dog.heard()
        await asyncio.sleep(3)
        assert tnc.silent_told == [] and tnc.state is Source.State.CONNECTED and tnc.calls == ["begin", "kiss on", "end"]
        await asyncio.sleep(55)
        assert tnc.stats.keepalive_checks == 1, "the quiet period started again from the byte"
        await asyncio.sleep(10)
        assert tnc.stats.keepalive_checks == 2
        await end(task)


async def test_a_check_that_nothing_answers_makes_the_radio_silent_and_says_how_often_it_is_probed() -> None:
    tnc = WatchedTnc()
    dog = Watchdog(tnc, 60.0)
    async with virtual_time():
        task = await running(dog, tnc)
        await asyncio.sleep(60 + 0.5 + 1.0 + 2.0 + 0.5)
        assert tnc.silent_told == ["; probing every 30 s"] and tnc.state is Source.State.SILENT
        await end(task)


async def test_a_line_just_opened_that_has_not_shown_the_radio_is_checked_at_once() -> None:
    tnc = WatchedTnc()
    tnc.confirmed = False
    dog = Watchdog(tnc, 600.0)
    async with virtual_time():
        task = await running(dog, tnc, check_first=True)
        await asyncio.sleep(0.1)
        assert tnc.sent == [EXIT] and tnc.last_watchdog_action == "check"
        await end(task)


async def test_a_check_is_not_made_while_the_tnc_is_not_connected_the_period_is_waited_out_again() -> None:
    tnc = WatchedTnc()
    tnc.state = Source.State.WAITING
    dog = Watchdog(tnc, 60.0)
    async with virtual_time():
        task = await running(dog, tnc)
        await asyncio.sleep(130)
        assert tnc.stats.keepalive_checks == 0 and tnc.calls == []
        tnc.state = Source.State.CONNECTED
        await asyncio.sleep(60)
        assert tnc.stats.keepalive_checks == 1
        await end(task)


async def test_with_the_checks_off_a_radio_that_is_not_silent_ends_the_watch() -> None:
    tnc = WatchedTnc()
    dog = Watchdog(tnc, 0.0)
    async with virtual_time():
        await running(dog, tnc)
        await asyncio.sleep(1)
    assert tnc.calls == []


# ---- the exits of a check

async def test_a_line_that_is_gone_when_the_check_begins_says_nothing_of_the_radio() -> None:
    tnc = WatchedTnc()
    tnc.has_line = False
    dog = Watchdog(tnc, 60.0)
    async with virtual_time():
        task = await running(dog, tnc)
        await asyncio.sleep(62)
        await end(task)
    assert tnc.sent == [] and tnc.silent_told == [] and tnc.calls == ["begin"], "(nothing began, so nothing is ended)"


async def test_an_exit_frame_that_cannot_be_written_ends_the_check_with_the_radio_not_blamed() -> None:
    tnc = WatchedTnc()
    tnc.refuses_write_number = 1
    dog = Watchdog(tnc, 60.0)
    async with virtual_time():
        task = await running(dog, tnc)
        await asyncio.sleep(62)
        await end(task)
    assert tnc.sent == [EXIT] and tnc.silent_told == [] and tnc.calls[:2] == ["begin", "end"]


async def test_a_return_that_cannot_be_written_ends_the_check_with_the_radio_not_blamed() -> None:
    tnc = WatchedTnc()
    tnc.refuses_write_number = 2
    dog = Watchdog(tnc, 60.0)
    async with virtual_time():
        task = await running(dog, tnc)
        await asyncio.sleep(62)
        await end(task)
    assert tnc.sent == [EXIT, PROMPT] and tnc.silent_told == [] and tnc.calls[:2] == ["begin", "end"]


@pytest.mark.parametrize(("gone_at", "sent", "calls"), [(60.2, [EXIT], ["begin", "end"]), (61.0, [EXIT, PROMPT], ["begin", "end"])])
async def test_a_line_replaced_in_the_middle_of_a_check_ends_it_before_the_next_step(gone_at: float, sent: list[bytes], calls: list[str]) -> None:
    """(`alive` says the line the watch was started for is still the Tnc's.)"""
    tnc = WatchedTnc()
    dog = Watchdog(tnc, 60.0)
    async with virtual_time():
        task = await running(dog, tnc)
        await asyncio.sleep(gone_at)
        tnc.alive = False
        await asyncio.sleep(5)
        assert task.done()
    assert tnc.sent == sent and tnc.calls[:2] == calls and tnc.silent_told == []


# ---- the silent radio

async def test_a_silent_radio_is_probed_every_probe_time_and_every_fifth_probe_the_port_is_opened_again() -> None:
    tnc = WatchedTnc()
    tnc.state = Source.State.SILENT
    dog = Watchdog(tnc, 600.0, probe_sec=30.0)
    async with virtual_time():
        task = await running(dog, tnc)
        await asyncio.sleep(29)
        assert tnc.stats.watchdog_probes == 0
        await asyncio.sleep(2)
        assert tnc.stats.watchdog_probes == 1 and tnc.last_watchdog_action == "probe"
        for _ in range(4):
            await asyncio.sleep(33.5)                                # (a probe takes 3.5 s of its own: the pause, the wait for a reply, the wait for any byte)
        await asyncio.sleep(3)
        assert tnc.stats.watchdog_probes == 5 and tnc.last_watchdog_action == "reopen" and tnc.stats.port_reopens == 1 and tnc.reopened == 1
        await end(task)
    assert tnc.silent_told == [], "a probe that gets no answer says nothing new: the radio is silent already"


async def test_a_radio_that_answers_between_two_probes_is_not_probed() -> None:
    tnc = WatchedTnc()
    tnc.state = Source.State.SILENT
    dog = Watchdog(tnc, 600.0, probe_sec=30.0)
    async with virtual_time():
        task = await running(dog, tnc)
        await asyncio.sleep(10)
        tnc.state = Source.State.CONNECTED                          # (a byte came: the Tnc ended the silence itself)
        await asyncio.sleep(25)
        assert tnc.stats.watchdog_probes == 0 and tnc.calls == []
        await end(task)


async def test_a_probe_that_is_answered_resets_the_count_that_decides_the_reopen() -> None:
    tnc = WatchedTnc()
    tnc.state = Source.State.SILENT
    dog = Watchdog(tnc, 600.0, probe_sec=30.0)
    async with virtual_time():
        task = await running(dog, tnc)
        await asyncio.sleep(31 + 34 + 34)
        assert dog.probes == 3
        dog.heard()
        assert dog.probes == 0
        await end(task)


# ---- the words

@pytest.mark.parametrize(("seconds", "text"), [(12, "12 s"), (12.34, "12.3 s"), (59.9, "59.9 s"), (60, "1 min"), (900, "15 min"), (90, "1.5 min")])
def test_a_time_is_in_seconds_below_a_minute_and_in_minutes_from_it(seconds: float, text: str) -> None:
    assert how_long(seconds) == text
