"""How long a test waits for what it expects before it fails (tests/README.md, "Waiting").

Generous: a wait ends as soon as the thing happens, and a busy runner can take seconds for one step.
"""

import time
from collections.abc import Callable

PATIENCE_SEC = 30.0


def poll(condition: Callable[[], object], what: str = "the condition", timeout_sec: float = PATIENCE_SEC) -> None:
    """Wait outside an event loop until the condition holds; fail after `timeout_sec`."""
    deadline = time.monotonic() + timeout_sec
    while not condition():
        assert time.monotonic() < deadline, f"{what} did not come true in {timeout_sec:g} s"
        time.sleep(0.01)
