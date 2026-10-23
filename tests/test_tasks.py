"""The tasks a part starts (neoaprs/tasks.py): cancelled and waited for, kept while they run, and an exception in one handed to the owner."""
import asyncio
import logging
from typing import Any

import pytest

from neoaprs.tasks import TaskSet, cancel_all


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
    await asyncio.sleep(0.01)
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
