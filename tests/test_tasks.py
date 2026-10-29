"""The tasks a part starts (neoaprs/tasks.py): cancelled and waited for, kept while they run, and an exception in one handed to the owner."""
import asyncio
import logging
from typing import Any

import pytest

from neoaprs.tasks import TaskSet, cancel_all, every
from tests.support.env import until


async def test_cancel_all_ends_the_tasks_and_waits_for_them_whatever_they_ended_with(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.tasks")
    cleaned: list[str] = []

    async def sleeper() -> None:
        try:
            await asyncio.sleep(60)
        finally:
            cleaned.append("sleeper")

    async def stubborn() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise RuntimeError("fails while it is cancelled") from None

    tasks = [asyncio.ensure_future(sleeper()), asyncio.ensure_future(stubborn())]
    await asyncio.sleep(0)
    await cancel_all(tasks)
    assert all(t.done() for t in tasks) and cleaned == ["sleeper"]
    assert any("ended with" in r.getMessage() and "fails while it is cancelled" in r.getMessage() for r in caplog.records)


async def test_the_task_that_asks_is_left_alone() -> None:
    done: list[str] = []

    async def stopper() -> None:
        await cancel_all([asyncio.current_task()])        # type: ignore[list-item]
        done.append("reached")

    await asyncio.ensure_future(stopper())
    assert done == ["reached"]


async def test_a_task_set_keeps_its_tasks_while_they_run_and_forgets_them_when_they_end() -> None:
    failed: list[asyncio.Task[Any]] = []
    tasks = TaskSet(failed.append)
    gate = asyncio.Event()

    async def waits() -> None:
        await gate.wait()

    task = tasks.spawn(waits(), "waits")
    assert task in tasks and len(tasks) == 1 and list(tasks) == [task] and task.get_name() == "waits"
    gate.set()
    await task
    await asyncio.sleep(0)
    assert len(tasks) == 0 and failed == []


async def test_a_task_that_fails_is_handed_to_the_owner_and_a_cancelled_one_is_not() -> None:
    failed: list[asyncio.Task[Any]] = []
    tasks = TaskSet(failed.append)

    async def fails() -> None:
        raise ValueError("boom")

    async def waits() -> None:
        await asyncio.sleep(60)

    bad = tasks.spawn(fails(), "bad")
    tasks.spawn(waits(), "waits")
    await until(lambda: failed == [bad])
    assert failed == [bad] and isinstance(bad.exception(), ValueError)
    await tasks.cancel_all()
    assert failed == [bad] and len(tasks) == 0


@pytest.mark.expects_errors
@pytest.mark.parametrize(("what", "words"), [("", "task bad failed"), ("beacon", "beacon task bad failed")])
async def test_a_task_set_given_a_logger_logs_the_failure_of_a_task_as_an_error(caplog: pytest.LogCaptureFixture, what: str, words: str) -> None:
    tasks = TaskSet(logging.getLogger("neoaprs.test"), what)

    async def fails() -> None:
        raise ValueError("boom")

    tasks.spawn(fails(), "bad")
    await asyncio.sleep(0.01)
    assert [(r.name, r.levelno, r.getMessage()) for r in caplog.records] == [("neoaprs.test", logging.ERROR, f"{words}: ValueError('boom')")]


async def test_the_cancellation_of_the_task_that_waits_in_cancel_all_is_not_swallowed() -> None:
    cleaning = asyncio.Event()

    async def slow_to_end() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cleaning.set()
            await asyncio.sleep(0.05)                      # (a slow clean-up while it is cancelled)
            raise

    victim = asyncio.ensure_future(slow_to_end())
    await asyncio.sleep(0)

    async def stopper() -> str:
        await cancel_all([victim])
        return "went on"

    waiting = asyncio.ensure_future(stopper())
    await cleaning.wait()
    waiting.cancel()                                       # (the owner of the stop is cancelled while it waits for the slow one)
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert victim.done() and waiting.cancelled()


async def test_cancel_all_of_a_caller_that_was_cancelled_earlier_and_goes_on_cleaning_up_still_ends_the_tasks() -> None:
    async def sleeper() -> None:
        await asyncio.sleep(60)

    victim = asyncio.ensure_future(sleeper())
    await asyncio.sleep(0)

    async def cleaner() -> str:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            await cancel_all([victim])                     # (a shutdown that runs in the finally of a cancelled task)
        return "cleaned"

    task = asyncio.ensure_future(cleaner())
    await asyncio.sleep(0)
    task.cancel()
    assert await task == "cleaned" and victim.cancelled()


async def test_every_runs_the_function_each_time_the_wait_is_over_and_goes_on_after_a_round_that_fails(caplog: pytest.LogCaptureFixture) -> None:
    rounds: list[int] = []

    def tick() -> None:
        rounds.append(len(rounds))
        if len(rounds) == 2:
            raise ValueError("boom")

    ticker = asyncio.ensure_future(every(0.01, tick, "the test timer"))
    await until(lambda: len(rounds) >= 4)
    ticker.cancel()
    assert [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "neoaprs.tasks"] == [(logging.ERROR, "the test timer failed")]
    assert caplog.records[-1].exc_info is not None


async def test_every_awaits_a_function_that_is_async_asks_for_the_wait_each_time_and_can_begin_at_once() -> None:
    waits: list[float] = []
    rounds: list[str] = []

    async def poll() -> None:
        rounds.append("poll")

    def wait() -> float:
        waits.append(0.01)
        return waits[-1]

    ticker = asyncio.ensure_future(every(wait, poll, "the poll", at_start=True))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert rounds == ["poll"] and waits == [0.01]          # (the first round did not wait)
    await until(lambda: len(rounds) >= 3)
    ticker.cancel()
    assert len(waits) >= 2


async def test_every_waits_the_first_time_that_is_given_before_the_first_round_and_not_the_usual_wait() -> None:
    asked: list[str] = []
    rounds: list[str] = []

    def usual() -> float:
        asked.append("usual")
        return 0.01

    ticker = asyncio.ensure_future(every(usual, lambda: rounds.append("tick"), "the timer", first=3600.0))
    await asyncio.sleep(0.05)
    ticker.cancel()
    assert rounds == [] and asked == []
