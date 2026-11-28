"""The ports a test's Mercury modem is started on: a base of the test's own for `free_ports`.

A pytest-xdist worker has its own range, so two tests never find the same pair free, and a modem
that restarts on its pair is not handed that pair's ports by another test.
"""

import itertools
import os
import socket
import sys
import tempfile
from pathlib import Path
from typing import IO

import pytest

from neoaprs import mercurymodem
from neoaprs.mercury import BROADCAST_PORT
from neoaprs.mercuryhelper import PORT_TRIES, free_ports

# The ports of a pytest-xdist worker: its own thousand from 20000 up, all below the ephemeral ranges
# (Linux from 32768, Windows from 49152), so that nothing the system hands out lies in them
WORKER_SPAN = 1000
# scripts/check runs at most twelve; more wrap round to a worker that is not likely to run beside
# them
WORKERS = 12
_tests_run = itertools.count()
# The lane of this process: its range, held by a lock of its own so that two runs of the suite on one
# machine (whose workers have the same numbers) never share one
_lane: int | None = None
_held: list[IO[bytes]] = []


def claim_lane(worker: int, folder: Path) -> tuple[int, IO[bytes] | None]:
    """Return the first lane from the worker's own that no other process holds, and its held lock file
    (None where locks cannot be taken: Windows, whose runners run one suite at a time)."""
    if sys.platform != "win32":
        import fcntl

        for step in range(WORKERS):
            lane = (worker + step) % WORKERS
            held = (folder / f"neoaprs-test-modem-lane-{lane}.lock").open("ab")
            try:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                held.close()
                continue
            return lane, held
    return worker % WORKERS, None


def _this_lane() -> int:
    global _lane
    if _lane is None:
        worker = int("".join(c for c in os.environ.get("PYTEST_XDIST_WORKER", "") if c.isdigit()) or 0)
        _lane, held = claim_lane(worker, Path(tempfile.gettempdir()))
        if held is not None:
            _held.append(held)  # kept open for the process's life
    return _lane


def base_of_this_test() -> int:
    """The port this test's modem asks for free ports from: the lane's range, its halves in turn."""
    return 20000 + WORKER_SPAN * _this_lane() + WORKER_SPAN // 2 * (next(_tests_run) % 2)


def own_ports(monkeypatch: pytest.MonkeyPatch) -> int:
    """Makes the modem ask for free ports from this test's base (what an autouse fixture of a test
    file calls); the base."""
    base = base_of_this_test()
    monkeypatch.setattr(
        mercurymodem, "free_ports", lambda first=BROADCAST_PORT, tries=PORT_TRIES: free_ports(base, tries)
    )
    return base


def free_port(first: int, tries: int = 50, udp: bool = False) -> int:
    """The first port from `first` up that nothing holds now (TCP, or UDP), for a real program that a
    test starts on a port of its own; raise OSError if none of `tries` is."""
    for port in range(first, first + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise OSError(f"no free port from {first} to {first + tries}")
