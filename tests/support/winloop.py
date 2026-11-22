"""The event loop of the tests on Windows, nudged from outside so that it never sleeps without a
limit while work waits for it.

pytest-asyncio runs a loop many times; the proactor loop's self-pipe read can then fail and not be
armed again, so a thread's `call_soon_threadsafe` goes unnoticed. A thread of the test process
therefore posts an empty completion packet to the loop's port a few times a second. The loop's clock
is not touched.
"""
import asyncio
import sys
import threading
import weakref

NUDGE_EVERY_SEC = 0.2
# The address the packet names as its operation: none of the loop's (it looks the address up, finds
# nothing and goes on), and not zero, which the loop's reading takes for an error of the port itself
NO_OPERATION = 1

if sys.platform == "win32":
    import _overlapped                      # type: ignore[import-not-found]  # (the standard library's own module of the proactor loop; it has no stub)

    _loops: "weakref.WeakSet[asyncio.AbstractEventLoop]" = weakref.WeakSet()
    # A loop is not closed while it is nudged: the handle of a closed port may be another object's
    # by then
    _lock = threading.Lock()
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
        """A loop of Windows that is nudged while it lives: what pytest-asyncio makes every test's
        loop with (the hook `pytest_asyncio_loop_factories` of conftest.py)."""
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
    """An empty packet to the loop's completion port; False when the loop has none (closed, or not a
    loop of Windows)."""
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
