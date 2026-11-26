"""One run of a child program at a time (neoaprs/childprogram.py, neoaprs/modemstate.py): a callback of
an old run that arrives after a new run started is dropped, a line the program cannot handle does not
end its reader, each run counts its own warnings, and a relaunch waits until the old run is gone.
"""

import asyncio
import io
import logging
import threading
from pathlib import Path
from typing import Any

import pytest

from neoaprs import childprogram
from neoaprs.childprogram import Post, Program, Run
from tests.support.env import until_started
from tests.test_mercury_modem import modem, stopped


class FakeProcess:
    """A process that has printed `lines` and ended with `code`."""

    def __init__(self, lines: list[str], code: int = 3) -> None:
        self.stdout = io.StringIO("".join(f"{line}\n" for line in lines))
        self.code, self.pid = code, 4242

    def wait(self, timeout: float | None = None) -> int:
        return self.code

    def poll(self) -> int:
        return self.code


class Heard(Program):
    name = "Fake"

    def __init__(self, ended: list[Any], fails_on: str = "") -> None:
        super().__init__(
            lambda code, lines: ended.append((code, lines)), logging.getLogger("t"), logging.getLogger("t")
        )
        self.heard: list[str] = []
        self.fails_on = fails_on

    def _end(self, process: Any) -> None:
        self.kill(process)

    def _heard(self, line: str, post: Post) -> None:
        if line == self.fails_on:
            raise ValueError(line)
        post(self.heard.append, line)


def read(program: Program, process: FakeProcess, loop: asyncio.AbstractEventLoop) -> None:
    program._read(process, loop)  # type: ignore[arg-type]


async def test_a_late_end_of_an_old_run_is_dropped_once_a_new_run_is_on() -> None:
    ended: list[Any] = []
    program = Heard(ended)
    old, new = FakeProcess(["one"]), FakeProcess([])
    program._process = old  # type: ignore[assignment]
    loop = asyncio.get_running_loop()
    thread = threading.Thread(target=read, args=(program, old, loop))
    thread.start()
    thread.join(30)
    # the end and the line are posted; before the loop delivers them a new run starts
    program._process = new  # type: ignore[assignment]
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert ended == [] and program.heard == [], "a stop and a start came between: the old run's word is void"
    program._process = old  # type: ignore[assignment]
    thread = threading.Thread(target=read, args=(program, FakeProcess(["two"]), loop))
    thread.start()
    thread.join(30)
    await asyncio.sleep(0)
    assert ended == [], "only the very process of the run counts"


async def test_the_current_runs_end_and_lines_are_delivered() -> None:
    ended: list[Any] = []
    program = Heard(ended)
    process = FakeProcess(["one", "two"])
    program._process = process  # type: ignore[assignment]
    thread = threading.Thread(target=read, args=(program, process, asyncio.get_running_loop()))
    thread.start()
    thread.join(30)
    await until_started(lambda: ended == [(3, ["one", "two"])])
    assert program.heard == ["one", "two"]


@pytest.mark.expects_errors
async def test_a_line_that_cannot_be_handled_does_not_end_the_reader(caplog: pytest.LogCaptureFixture) -> None:
    """A reader that ends leaves the program blocked on a full pipe."""
    ended: list[Any] = []
    program = Heard(ended, fails_on="bad")
    process = FakeProcess(["bad", "bad", "after"])
    program._process = process  # type: ignore[assignment]
    thread = threading.Thread(target=read, args=(program, process, asyncio.get_running_loop()))
    thread.start()
    thread.join(30)
    await until_started(lambda: ended and program.heard == ["after"])
    assert sum("could not be handled" in r.getMessage() for r in caplog.records) == 1, "said once"


def test_each_run_counts_its_own_warnings_and_a_new_start_has_a_new_count(tmp_path: Path) -> None:
    class Warned(Program):
        def _warning(self, line: str) -> str | None:
            return line

    program = Warned(lambda code, lines: None, logging.getLogger("t"), logging.getLogger("t"))
    old, new = Run(), Run()
    for _ in range(5):
        program._tell("[WRN] stuck", old)
    program._tell("[WRN] stuck", new)
    assert old.said["[WRN] stuck"][0] == 5 and new.said["[WRN] stuck"][0] == 1
    program._stopped_warnings(None, old)
    program._stopped_warnings(None, old)  # (a second look finds nothing, and fails on nothing)
    assert old.said == {} and new.lines_read == 1


async def test_a_start_gives_the_run_its_own_count(tmp_path: Path) -> None:
    program = Heard([])
    first = program._run
    program.start([childprogram.sys.executable, "-c", "print('x')"], tmp_path)
    try:
        assert program._run is not first
    finally:
        await asyncio.to_thread(program.stop)


async def test_a_relaunch_waits_until_the_old_run_is_gone(tmp_path: Path) -> None:
    m = modem(tmp_path)
    gone = threading.Event()
    launched: list[bool] = []

    async def launch() -> None:
        launched.append(gone.is_set())

    m._launch = launch  # type: ignore[method-assign]
    m._program.stop = lambda: gone.wait(30) and None  # type: ignore[method-assign, func-returns-value]
    m.state = "waiting"
    try:
        m._stop_run_later("test-stop")
        task = asyncio.create_task(m._relaunch_after(0.0, m._generation, m._waits))
        await asyncio.sleep(0.2)
        assert launched == [], "the old run still holds the sound card"
        gone.set()
        await asyncio.wait_for(task, 30)
        assert launched == [True]
    finally:
        gone.set()
        m._program.stop = lambda: None  # type: ignore[method-assign]
        await stopped(m)
