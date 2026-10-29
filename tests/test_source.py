"""What every feed of packets looks like from outside (neoaprs/source.py): the state and the problem, the lines it keeps, its tasks, and the back-off between two tries."""
import asyncio
import errno

import pytest

from neoaprs.source import Backoff, Source, os_error_text
from tests.support.clock import FixedClock
from tests.support.env import until


class Dummy(Source):
    async def start(self) -> None:
        self._set_state(Source.State.CONNECTING)
        self._set_state(Source.State.CONNECTED)

    async def stop(self) -> None:
        await self._cancel_tasks()
        self._set_state(Source.State.STOPPED)


def test_the_back_off_goes_up_to_the_last_delay_and_starts_over_when_a_connection_stayed_up(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr("neoaprs.source._time.monotonic", lambda: now[0])
    b = Backoff()
    assert [b.next_delay_sec() for _ in range(6)] == [5.0, 10.0, 20.0, 30.0, 30.0, 30.0]
    b.connected()
    now[0] += 59
    assert b.next_delay_sec() == 30.0, "a connection that lived 59 seconds is not stable"
    b.connected()
    now[0] += 61
    assert b.next_delay_sec() == 5.0, "one that lived a minute starts the series over"


def test_reset_starts_the_series_over() -> None:
    b = Backoff([1.0, 2.0])
    assert b.next_delay_sec() == 1.0 and b.next_delay_sec() == 2.0
    b.reset()
    assert b.next_delay_sec() == 1.0


def test_the_words_of_an_os_error_are_the_systems() -> None:
    assert os_error_text(FileNotFoundError(errno.ENOENT, "ignored")) == "No such file or directory"
    assert os_error_text(OSError("odd")) == "odd" and os_error_text(OSError(0, "from strerror")) == "from strerror"
    assert os_error_text(ValueError()) == "ValueError" and os_error_text(ValueError("bad")) == "bad"


async def test_state_changes_are_told_once_each_and_the_problem_is_kept() -> None:
    clock = FixedClock()
    s = Dummy("tnc", clock)
    states: list[Source.State] = []
    changes: list[int] = []
    s.state_changed.connect(states.append)
    s.changed.connect(lambda: changes.append(1))
    assert s.state is Source.State.STOPPED and s.describe() == "" and not await s.send(b"x")
    await s.start()
    s._set_state(Source.State.CONNECTED)                   # the same state again: counted as a change of the lines, not of the state
    assert states == [Source.State.CONNECTING, Source.State.CONNECTED] and len(changes) == 3
    clock.advance(30)
    s._set_state(Source.State.WAITING, "No such file or directory")
    assert s.state is Source.State.WAITING and s.problem == s.last_error == "No such file or directory"
    s._set_state(Source.State.WAITING, "Permission denied")
    assert s.problem == "No such file or directory" and s.last_error == "Permission denied", "the first problem is what is shown, the last is what happened last"
    s._set_state(Source.State.CONNECTING)
    assert s.problem == ""
    s._set_problem("the radio is off")
    assert s.problem == "the radio is off"
    await s.stop()


async def test_a_feed_that_waits_says_why_the_line_is_down_now_and_retries_unless_it_was_stopped_meanwhile() -> None:
    s = Dummy("tnc", FixedClock())
    tries: list[int] = []

    async def retry() -> None:
        tries.append(1)

    s._set_problem("the TNC sends text, not KISS frames")
    s._waiting("socket lost: reset", 0.0, retry)
    assert s.state is Source.State.WAITING and s.problem == s.last_error == "socket lost: reset"
    assert s.lines[-1].endswith("NeoAPRS: socket lost: reset; trying again in 0 s")
    await until(lambda: tries)
    s._waiting("without a retry", 0.0)
    assert tries == [1] and s.problem == "without a retry" and len(s._tasks) == 0


async def test_the_lines_are_numbered_stamped_bounded_and_counted() -> None:
    clock = FixedClock()
    s = Dummy("tnc", clock)
    s._note("opened /dev/brainbox_1")
    s._saw("x" * 500)
    s._reject()
    assert len(s.lines) == 2 and s.stats.frames_in == 1 and s.stats.rejected == 1
    assert s.lines[0] == "12:00:00  NeoAPRS: opened /dev/brainbox_1" and len(s.lines[1]) == len("12:00:00  ") + 300
    for _ in range(Source.MAX_LINES + 10):
        s._saw("line")
    assert len(s.lines) == Source.MAX_LINES


async def test_the_tasks_of_a_source_end_with_it_and_a_failed_one_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    s = Dummy("tnc")

    async def fails() -> None:
        raise RuntimeError("boom")

    async def waits() -> None:
        await asyncio.sleep(60)

    s._spawn(fails())
    waiting = s._spawn(waits())
    await until(lambda: any("source tnc: task failed" in r.getMessage() for r in caplog.records))
    assert any("source tnc: task failed" in r.getMessage() for r in caplog.records)
    await s.stop()
    assert waiting.cancelled()


async def test_a_source_that_implements_nothing_says_so() -> None:
    s = Source("bare")
    with pytest.raises(NotImplementedError):
        await s.start()
    with pytest.raises(NotImplementedError):
        await s.stop()
