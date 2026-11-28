"""The processes a test starts (tests/support/children.py): found under the test's process and ended
when they outlive it, and a stand-in that ends by itself when the run's process is gone."""

import os
import subprocess
import sys
import time

import pytest

from tests.conftest import ROOT
from tests.support import children
from tests.support.patience import PATIENCE_SEC, poll

linux_only = pytest.mark.skipif(not children.supported(), reason="the children of a task are read from Linux's /proc")
SLEEPER = [sys.executable, "-c", "import time; time.sleep(600)"]


@linux_only
def test_a_child_and_its_child_are_found_and_a_child_that_ended_is_not() -> None:
    before = children.descendants()
    parent = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import subprocess, sys, time; subprocess.Popen(sys.argv[1:]); time.sleep(600)",
            *SLEEPER,
        ]
    )
    try:
        poll(lambda: len(children.descendants() - before) == 2, "the child and its child")
        assert parent.pid in children.descendants() - before
        assert children.left_since(before, seconds=0.2) == children.descendants() - before
    finally:
        left = children.descendants() - before
        children.end(left)
        parent.wait(PATIENCE_SEC)
    poll(lambda: not children.descendants() - before, "the end of both")
    quick = subprocess.Popen([sys.executable, "-c", "pass"])
    quick.wait(PATIENCE_SEC)
    assert quick.pid not in children.descendants()


def test_a_stand_in_ends_by_itself_when_the_process_of_the_run_is_gone(tmp_path: os.PathLike[str]) -> None:
    """The run's process here is a made-up one that the test ends; the stand-in under it is told of
    the run by NEOAPRS_TEST_RUN_PID, as the stand-ins of the suite are."""
    run = subprocess.Popen(SLEEPER)
    marker = os.path.join(str(tmp_path), "stand-in.pid")
    code = (
        f"import os, sys, time; sys.path.insert(0, {str(ROOT)!r}); from tests.support import children; "
        f"children.end_with_the_run(); open({marker!r}, 'w').write(str(os.getpid())); time.sleep(600)"
    )
    stand_in = subprocess.Popen([sys.executable, "-c", code], env={**os.environ, children.RUN_PID: str(run.pid)})
    try:
        poll(lambda: os.path.exists(marker), "the stand-in's start")
        time.sleep(0.3)  # (a window in which it must still run: a stall only lengthens it)
        assert stand_in.poll() is None, "it runs while the run's process does"
        run.kill()
        run.wait(PATIENCE_SEC)
        assert stand_in.wait(PATIENCE_SEC) == 0, "it ended by itself once the run's process was gone"
    finally:
        for process in (run, stand_in):
            if process.poll() is None:
                process.kill()
                process.wait(PATIENCE_SEC)
