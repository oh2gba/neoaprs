"""Messages for people go to stderr, so that stdout (a port, a table) stays usable by scripts."""
import signal
import sys
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager

SETTLE_SEC = 0.5                    # opening a serial port may clear its input buffer


def ctrl_break_is_ctrl_c() -> None:
    """Treat Ctrl+Break as Ctrl+C on Windows, where it would otherwise end the program at once.

    A program in its own process group can only be sent Ctrl+Break."""
    number = getattr(signal, "SIGBREAK", None)
    if number is not None:
        signal.signal(number, signal.default_int_handler)


@contextmanager
def break_as_interrupt() -> Iterator[None]:
    """On Windows, handle Ctrl+Break like asyncio.run handles Ctrl+C (cancel at the next wait).

    A KeyboardInterrupt on any line can lose an I/O completion and hang closing the loop."""
    number = getattr(signal, "SIGBREAK", None)
    on_interrupt = signal.getsignal(signal.SIGINT)
    if number is None or not callable(on_interrupt):
        yield
        return
    before = signal.signal(number, on_interrupt)
    try:
        yield
    finally:
        signal.signal(number, before)


async def interruptible[T](work: Callable[[], Awaitable[T]]) -> T:
    """Await `work()` with Ctrl+Break handled as Ctrl+C (`break_as_interrupt`)."""
    with break_as_interrupt():
        return await work()


def say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)
