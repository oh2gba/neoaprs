"""A time limit for every test. `faulthandler_timeout` (pyproject.toml) writes the stack of every thread of a test that is still running after two minutes and lets it go on; no plugin in the project ends one, so a test that hangs
would cost the job its half hour and name nobody. Here a watchdog thread arms for each test: when the test has run over the limit it writes the test's name and the stack of every thread to stderr and ends the process
(under pytest-xdist the worker is lost, and the run says which test it was running and goes on with a new one). The limit is NEOAPRS_TEST_LIMIT_SEC seconds (600 when unset; 0 is no limit): the slowest test of the suite
takes minutes on a busy machine, a hung one takes all the time there is."""
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
        capture.suspend_global_capture(in_=False)           # (what a test writes to stderr is held by pytest until it ends: this goes to the real one)
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
