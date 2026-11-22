"""A time limit for every test: a watchdog thread arms for each test and, when the test runs over
the limit, writes its name and every thread's stack to stderr and ends the process.
"""
import faulthandler
import os
import sys
import threading
from collections.abc import Iterator
from typing import Any

import pytest

LIMIT_SEC = 600.0
EXIT_CODE = 70


def limit_sec() -> float:
    try:
        return float(os.environ.get("NEOAPRS_TEST_LIMIT_SEC", LIMIT_SEC))
    except ValueError:
        return LIMIT_SEC


def _over(test: str, seconds: float, capture: Any) -> None:
    if capture is not None:
        # What a test writes to stderr is held by pytest until it ends: this goes to the real one
        capture.suspend_global_capture(in_=False)
    err = sys.__stderr__ or sys.stderr
    err.write(f"\n{test} ran over its time limit of {seconds:g} s and is ended here (NEOAPRS_TEST_LIMIT_SEC); the stack of every thread:\n")
    err.flush()
    faulthandler.dump_traceback(file=err, all_threads=True)
    err.flush()
    os._exit(EXIT_CODE)


@pytest.fixture(autouse=True)
def a_test_has_a_time_limit(request: pytest.FixtureRequest) -> Iterator[None]:
    seconds = limit_sec()
    if seconds <= 0:
        yield
        return
    watchdog = threading.Timer(seconds, _over, args=(request.node.nodeid, seconds, request.config.pluginmanager.getplugin("capturemanager")))
    watchdog.daemon = True
    watchdog.start()
    try:
        yield
    finally:
        watchdog.cancel()
