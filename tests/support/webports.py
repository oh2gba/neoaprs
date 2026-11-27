"""The port a test's page is served on: a free one in a block of each pytest-xdist worker's own, below
the ephemeral ranges.

With port 0 the page took a port the system handed out, and its secure side the ten after it, where
other workers' pages and their clients' outgoing sockets are too.
"""

import os
import random
import socket
import sys
from collections.abc import Callable

# 12000 to 19999: below the modems' 20000 (tests/support/modemports.py) and every ephemeral range,
# above the real modems' own ports (nodevices.modem_port)
FIRST = 12000
WORKER_SPAN = 250
WORKERS = 32
# a page tries its port and the ten after it, its secure side the ten after the one it got
TEST_SPAN = 24
SLOTS = WORKER_SPAN // TEST_SPAN


def worker() -> int | None:
    """This xdist worker's number, 0 without xdist; None past the last block."""
    number = int("".join(c for c in os.environ.get("PYTEST_XDIST_WORKER", "") if c.isdigit()) or 0)
    return number if number < WORKERS else None


def _free(port: int) -> bool:
    """Whether nothing listens on the port, on the loopback or on every address (Windows lets the two
    be bound side by side, so both are tried)."""
    for host in ("127.0.0.1", ""):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if sys.platform != "win32":
                # as Tornado binds there: a port with only connections in TIME_WAIT on it is free
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError:  # taken, or in a range the system keeps out (Windows' excluded ports)
                return False
    return True


def next_web_port(free: Callable[[int], bool] | None = None) -> int:
    """A port of this worker's block whose TEST_SPAN ports are all free, from a random slot (another
    pytest run on this machine has the same worker numbers); 0, a port the system picks, when none is."""
    probe = _free if free is None else free
    number = worker()
    if number is None:
        return 0
    first = FIRST + WORKER_SPAN * number
    start = random.randrange(SLOTS)
    for slot in range(SLOTS):
        port = first + TEST_SPAN * ((start + slot) % SLOTS)
        if all(probe(p) for p in range(port, port + TEST_SPAN)):
            return port
    return 0
