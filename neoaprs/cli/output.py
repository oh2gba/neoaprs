"""What the commands print for a person to read: on stderr, so that what a command prints on stdout (a port to give the daemon, a table) can be taken by a script."""
import signal
import sys
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager

SETTLE_SEC = 0.5                    # after a client has opened the line: a port that opens may clear its input buffer as it does


def ctrl_break_is_ctrl_c() -> None:
    """Windows: Ctrl+Break is the signal a program in a process group of its own can be sent (a script that runs a command, a test), and by default it ends the program at once; here it is Ctrl+C."""
    number = getattr(signal, "SIGBREAK", None)
    if number is not None:
        signal.signal(number, signal.default_int_handler)


@contextmanager
def break_as_interrupt() -> Iterator[None]:
    """Windows: Ctrl+Break, while the loop runs, is handled as asyncio.run handles Ctrl+C, by cancelling what the command does at its next wait; raised as KeyboardInterrupt at whatever line the loop is on, it can land inside
    the loop's own wait for the system's completions, lose one of them, and the loop's close then waits for it for ever."""
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
    """`work()` awaited with Ctrl+Break handled as Ctrl+C is (`break_as_interrupt`): what a command that runs until it is interrupted gives asyncio.run."""
    with break_as_interrupt():
        return await work()


def say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)
