"""The loop's skipped clock (tests/support/virtualtime.py): a wait on a timer takes no time and is counted, the loop is as it was afterwards, and a thread that delivers is still waited for."""
import asyncio
import threading
import time

from tests.support.virtualtime import virtual_time


async def test_a_long_wait_takes_no_time_and_the_loops_clock_has_moved_by_it() -> None:
    loop = asyncio.get_running_loop()
    began_at, real_began = loop.time(), time.monotonic()
    async with virtual_time() as clock:
        await asyncio.sleep(3600)
        assert 3599 < clock.skipped <= 3600          # (the time that really passed is part of the wait)
        assert loop.time() - began_at >= 3600
    assert time.monotonic() - real_began < 5


async def test_timers_run_in_their_order() -> None:
    seen: list[str] = []

    async def later(name: str, seconds: float) -> None:
        await asyncio.sleep(seconds)
        seen.append(name)

    async with virtual_time() as clock:
        await asyncio.gather(later("b", 20), later("a", 5), later("c", 20.5))
        assert 20 < clock.skipped <= 20.5
    assert seen == ["a", "b", "c"]


async def test_the_loop_is_as_it_was_afterwards() -> None:
    loop = asyncio.get_running_loop()
    first = loop.time
    async with virtual_time():
        assert loop.time != first
    assert loop.time == first
    before = loop.time()
    await asyncio.sleep(0.01)
    assert 0 < loop.time() - before < 5


async def test_a_thread_that_delivers_is_waited_for_not_skipped() -> None:
    loop = asyncio.get_running_loop()
    done: asyncio.Future[str] = loop.create_future()

    def work() -> None:
        time.sleep(0.1)
        loop.call_soon_threadsafe(done.set_result, "bytes")

    async with virtual_time() as clock:
        threading.Thread(target=work).start()
        assert await done == "bytes"
        assert clock.skipped == 0, "no timer was waiting, so nothing was brought forward"


async def test_work_handed_to_a_thread_holds_the_clock_so_a_wait_cannot_jump_past_its_answer() -> None:
    order: list[str] = []

    def slow() -> str:                                                                      # (a question the program asks the system on a thread, as about a serial adapter: slow on a slow machine)
        time.sleep(0.3)
        order.append("thread")
        return "adapter"

    async def waiter() -> None:
        await asyncio.sleep(5)
        order.append("timer")

    async with virtual_time() as clock:
        timer = asyncio.create_task(waiter())
        assert await asyncio.to_thread(slow) == "adapter"
        await timer
        assert order == ["thread", "timer"], "the 5 s timer waited for the thread instead of being brought forward past it"
        assert clock.in_threads == 0 and 4 < clock.skipped <= 5
