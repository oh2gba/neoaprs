"""The event loop of the tests on Windows is nudged from outside, so that it never sleeps without a limit while work waits for it.

What was seen (13 November 2026, a Windows 11 machine, Python 3.13.14, twice in six runs of the suite): a worker sat for ever in the loop's `_poll` during the setup or the teardown of a test, while the thread
that owed it an answer (the database's) had already given it with `call_soon_threadsafe` and was idle. The answer was in the loop's queue; the loop was never woken to look. A loop is woken from another
thread by a byte on its "self pipe", which the proactor loop reads with one pending read that it must arm again after every byte, and it arms it at the start of every run and cancels it at the end
(`ProactorEventLoop.run_forever`, `_loop_self_reading`). pytest-asyncio runs a loop many times, once for every fixture and every test, where a program runs it once: under that pattern asyncio logs "Error
on reading from the event loop self pipe" (WinError 995) now and then, and a read that ends so is not armed again before the next run. A daemon runs its loop once and 200 000 answers from a thread came
through without one being late; the fault is of the tests' way of running a loop, so the remedy is here and not in the program.

The remedy does not depend on that reader: a thread of the test process posts an empty completion packet to the loop's completion port a few times a second, which is what the loop sleeps on. `_poll`
returns, finds nothing of its own in the packet, and the loop goes round once: what is in its queue runs. A loop that has nothing to do goes back to sleep. The loop's clock is not touched, so the virtual
time of tests/support/virtualtime.py sees nothing of it (a real wait there only ends early and is begun again). On every other system the tests' loop is asyncio's own."""
import asyncio
import sys
import threading
import weakref

NUDGE_EVERY_SEC = 0.2
NO_OPERATION = 1         # the address the packet names as its operation: none of the loop's (it looks the address up, finds nothing and goes on), and not zero, which the loop's reading takes for an error of the port itself

if sys.platform == "win32":
    import _overlapped                      # type: ignore[import-not-found]  # (the standard library's own module of the proactor loop; it has no stub)

    _loops: "weakref.WeakSet[asyncio.AbstractEventLoop]" = weakref.WeakSet()
    _lock = threading.Lock()                 # a loop is not closed while it is nudged: the handle of a closed port may be another object's by then
    _nudger: threading.Thread | None = None

    def _nudge_for_ever() -> None:
        wait = threading.Event()
        while not wait.wait(NUDGE_EVERY_SEC):
            with _lock:
                for loop in list(_loops):
                    nudge(loop)

    class NudgedLoop(asyncio.ProactorEventLoop):
        def close(self) -> None:
            with _lock:
                _loops.discard(self)
                super().close()

    def new_loop() -> asyncio.AbstractEventLoop:
        """A loop of Windows that is nudged while it lives: what pytest-asyncio makes every test's loop with (the hook `pytest_asyncio_loop_factories` of conftest.py)."""
        global _nudger
        loop = NudgedLoop()
        with _lock:
            _loops.add(loop)
            if _nudger is None:
                _nudger = threading.Thread(target=_nudge_for_ever, name="neoaprs-test-loop-nudge", daemon=True)
                _nudger.start()
        return loop
else:
    new_loop = asyncio.new_event_loop        # (asyncio's own: nothing is changed where the fault is not)


def nudge(loop: asyncio.AbstractEventLoop) -> bool:
    """An empty packet to the loop's completion port; False when the loop has none (closed, or not a loop of Windows)."""
    posted = False
    if sys.platform == "win32":
        port = getattr(getattr(loop, "_proactor", None), "_iocp", None)
        if port is not None and not loop.is_closed():
            try:
                _overlapped.PostQueuedCompletionStatus(port, 0, 0, NO_OPERATION)
                posted = True
            except OSError:
                posted = False
    return posted
