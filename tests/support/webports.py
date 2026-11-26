"""The port a test's page is served on: a block of each pytest-xdist worker's own, below the
ephemeral ranges.

With port 0 the page took a port the system handed out, and its secure side the ten after it, where
other workers' pages and their clients' outgoing sockets are too.
"""

import itertools
import os

# 12000 to 19199: below the modems' 20000 (tests/support/modemports.py) and every ephemeral range,
# above the real modems' own ports (nodevices.modem_port)
FIRST = 12000
WORKER_SPAN = 600
WORKERS = 12
# a page tries its port and the ten after it, its secure side the ten after the one it got
TEST_SPAN = 24
_pages = itertools.count()


def worker() -> int:
    return int("".join(c for c in os.environ.get("PYTEST_XDIST_WORKER", "") if c.isdigit()) or 0) % WORKERS


def next_web_port() -> int:
    """The next page port of this worker's block, round its block again when it is used up."""
    return FIRST + WORKER_SPAN * worker() + TEST_SPAN * (next(_pages) % (WORKER_SPAN // TEST_SPAN))
