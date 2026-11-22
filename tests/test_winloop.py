"""The tests' event loop on Windows is nudged from outside (tests/support/winloop.py): an answer
from another thread reaches a loop whose self-pipe reader is dead, and a loop with nothing to do is
not kept busy.
"""
import asyncio
import sys
import threading
import time

import pytest

from tests.support import winloop

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="the proactor loop is Windows's")


def test_the_loop_of_the_tests_is_the_nudged_one_on_windows_and_asyncios_own_elsewhere() -> None:
    loop = winloop.new_loop()
    try:
        assert (type(loop).__name__ == "NudgedLoop") == (sys.platform == "win32")
    finally:
        loop.close()
    assert sys.platform == "win32" or winloop.new_loop is asyncio.new_event_loop


async def test_the_loop_a_test_runs_on_is_the_one_the_hook_names() -> None:
    assert sys.platform != "win32" or type(asyncio.get_running_loop()).__name__ == "NudgedLoop"


@windows_only
async def test_an_answer_from_a_thread_reaches_a_loop_whose_self_pipe_is_no_longer_read() -> None:
    loop = asyncio.get_running_loop()
    # A run arms its reader after the first step of what it runs
    await asyncio.sleep(0.05)
    reader = loop._self_reading_future                      # type: ignore[attr-defined]
    assert reader is not None
    # The reader ends as asyncio ends it at the end of a run, and nothing arms it again in this one
    reader.cancel()
    await asyncio.sleep(0.05)
    answer: asyncio.Future[str] = loop.create_future()
    threading.Timer(0.1, lambda: loop.call_soon_threadsafe(answer.set_result, "here")).start()
    started = time.perf_counter()
    # No timer is pending: without the nudge the loop sleeps for ever here, and the test's time
    # limit ends the worker
    assert await answer == "here"
    assert time.perf_counter() - started < 5.0


@windows_only
def test_a_closed_loop_is_not_nudged_and_an_idle_one_stays_asleep() -> None:
    loop = winloop.new_loop()
    try:
        rounds = 0

        def count() -> None:
            nonlocal rounds
            rounds += 1

        async def idle() -> None:
            for _ in range(3):
                await asyncio.sleep(0.3)
                count()
        loop.run_until_complete(idle())
        # A nudge wakes the loop and runs nothing of the test's: the three sleeps ended by their own
        # timers
        assert rounds == 3 and winloop.nudge(loop)
    finally:
        loop.close()
    assert winloop.nudge(loop) is False
