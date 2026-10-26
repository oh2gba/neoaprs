"""A clock for the event loop that a test holds: while every task waits for a timer and nothing else is ready, the loop's time jumps to the next timer instead of the loop sleeping until it. A test of code
that waits (a pause between two steps, a quiet period, a back-off) runs at once, and what it asserts on is the time that passed, not a wait it had to sit through. Only a wait on timers is skipped: the loop still
looks at its sockets and threads first, so a test with real I/O in it (a thread that delivers bytes) should not use this; one whose fakes are in memory should."""
import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any


class VirtualTime:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._real_time: Callable[[], float] = loop.time
        self.skipped = 0.0                                  # seconds of waiting the loop did not do

    def time(self) -> float:
        return self._real_time() + self.skipped

    def select(self, real_select: Callable[[float | None], Any], timeout: float | None) -> Any:
        """What the loop's selector does instead: anything ready is returned as it is, else the next timer is brought forward."""
        if events := real_select(0):
            return events
        if timeout is None:
            return real_select(None)
        self.skipped += max(timeout, 0.0)
        return []


@asynccontextmanager
async def virtual_time() -> AsyncIterator[VirtualTime]:
    """Inside the block the running loop's timers are skipped over (`.skipped` says how much); the loop is as it was afterwards."""
    loop = asyncio.get_running_loop()
    clock = VirtualTime(loop)
    selector = loop._selector  # type: ignore[attr-defined]
    real_select = selector.select
    loop.time = clock.time  # type: ignore[method-assign]
    selector.select = lambda timeout=None: clock.select(real_select, timeout)
    try:
        yield clock
    finally:
        selector.select = real_select
        loop.time = clock._real_time  # type: ignore[method-assign]
