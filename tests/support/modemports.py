"""The ports a test's Mercury modem is started on: a base of the test's own for `free_ports`.

The modem asks for free ports from Mercury's defaults up. Two tests side by side (pytest-xdist) must not both find the same pair free between the probe and the bind, and a test that has its modem die and
come back on the pair it had (tests/test_mercury_relaunch.py) must not have that pair handed to another test's modem while its own is down. So a worker has a range of its own, and its tests, which run one
after the other, take its two halves in turn: no two workers share a port, and a test does not start where the one before it may still hold a port (Windows keeps the port of a process that was killed for
a moment)."""
import itertools
import os

import pytest

from neoaprs import mercurymodem
from neoaprs.mercury import BROADCAST_PORT
from neoaprs.mercuryhelper import PORT_TRIES, free_ports

WORKER_SPAN = 1000                      # the ports of a pytest-xdist worker: its own thousand from 20000 up, all below the ephemeral ranges (Linux from 32768, Windows from 49152), so that nothing the system hands out lies in them
WORKERS = 12                            # (scripts/check runs at most twelve; more wrap round to a worker that is not likely to run beside them)
_tests_run = itertools.count()


def base_of_this_test() -> int:
    """The port this test's modem asks for free ports from: the worker's range, its halves in turn."""
    worker = int("".join(c for c in os.environ.get("PYTEST_XDIST_WORKER", "") if c.isdigit()) or 0) % WORKERS
    return 20000 + WORKER_SPAN * worker + WORKER_SPAN // 2 * (next(_tests_run) % 2)


def own_ports(monkeypatch: pytest.MonkeyPatch) -> int:
    """Makes the modem ask for free ports from this test's base (what an autouse fixture of a test file calls); the base."""
    base = base_of_this_test()
    monkeypatch.setattr(mercurymodem, "free_ports", lambda first=BROADCAST_PORT, tries=PORT_TRIES: free_ports(base, tries))
    return base
