"""The tasks a part starts, shared by every part that runs on the loop: `cancel_all` ends tasks and waits for each, `TaskSet` is the tasks one owner starts."""
import asyncio
import logging
from collections.abc import Callable, Coroutine, Iterable, Iterator
from typing import Any

log = logging.getLogger("neoaprs.tasks")


async def cancel_all(tasks: Iterable[asyncio.Task[Any]]) -> None:
    """Cancels the tasks and waits until each has ended, whatever it ended with: the shutdown goes on. The task that asks is left alone (a task that stops its
    owner would otherwise cancel itself), and one that fails while it is cancelled is told in the debug log, not lost."""
    me = asyncio.current_task()
    mine = [t for t in tasks if t is not me and not t.done()]
    for t in mine:
        t.cancel()
    for t in mine:
        try:
            await t
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.debug("task %s ended with %r while it was cancelled", t.get_name(), e)


class TaskSet:
    """The tasks one owner starts: each is kept (the loop holds its tasks only weakly, a task nobody holds can vanish half way), forgotten when it ends, and an exception in it is
    handed to `failed` instead of lying in the task until the shutdown. cancel_all() ends them in the order they were made."""

    def __init__(self, failed: Callable[[asyncio.Task[Any]], None]) -> None:
        self._failed = failed
        self._tasks: dict[asyncio.Task[Any], None] = {}

    def spawn(self, coro: Coroutine[Any, Any, None], name: str | None = None) -> asyncio.Task[None]:
        task = asyncio.get_running_loop().create_task(coro, name=name)
        self._tasks[task] = None
        task.add_done_callback(self._done)
        return task

    def _done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.pop(task, None)
        if not task.cancelled() and task.exception() is not None:
            self._failed(task)

    async def cancel_all(self) -> None:
        await cancel_all(list(self._tasks))               # the done callbacks edit the dict while these are awaited
        for task in [t for t in self._tasks if t.done()]:
            del self._tasks[task]

    def __contains__(self, task: object) -> bool:
        return task in self._tasks

    def __iter__(self) -> Iterator[asyncio.Task[Any]]:
        return iter(list(self._tasks))

    def __len__(self) -> int:
        return len(self._tasks)
