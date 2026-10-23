import os
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# every message the daemon sends to a page is checked against neoaprs/web/protocol.py during the tests, and a mismatch fails the test (also when it happens in a signal handler, where an exception is only
# logged: see the fixture protocol_violations)
os.environ.setdefault("NEOAPRS_VALIDATE_OUT", "1")           # NEOAPRS_VALIDATE_OUT=0 pytest runs the tests the way production runs
os.environ.setdefault("NEOAPRS_VALIDATE_RAISE", "1")


# No test may open a serial device of the machine (a development board resets when its port is opened, a radio may be keyed): the search of every daemon, in this process and in the processes the tests start (they inherit the
# variable), looks at a pattern that matches nothing. A test of the search names the folder of its pseudo-terminals, or clears the variable (the fixture search_pattern_from_settings).
os.environ["NEOAPRS_SERIAL_PATTERN"] = "/dev/neoaprs-test-no-such-port*"


# Hypothesis is in the dev group. 'ci' is the default so that a run is reproducible (derandomize: the same examples every time, no example database);
# HYPOTHESIS_PROFILE=dev explores far more, with a random seed, and keeps what it finds in .hypothesis/ to replay.
try:
    from hypothesis import settings as _hypothesis_settings
except ImportError:
    pass
else:
    _hypothesis_settings.register_profile("ci", max_examples=200, deadline=None, derandomize=True, database=None)
    _hypothesis_settings.register_profile("dev", max_examples=2000, deadline=None)
    _hypothesis_settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))

# Everything the tests are built from is in tests/support. A fixture is found by pytest where this file imports it.
from tests.support.clock import FixedClock  # noqa: E402, F401
from tests.support.files import FIXTURES, fixture_bytes, fixture_text  # noqa: E402, F401
from tests.support.fixtures import clock, protocol_violations, search_pattern_from_settings, tmp_data  # noqa: E402, F401
from tests.support import guards, markers  # noqa: E402
from tests.support.guards import isolated_machine, logging_restored, no_leaked_db_threads, no_leaked_tasks, no_unexpected_errors  # noqa: E402, F401
from tests.support.ptyline import ptys  # noqa: E402, F401


def reorder_files(items: "list[pytest.Item]", order: str) -> None:
    """NEOAPRS_TEST_ORDER=reverse|shuffle[:SEED] runs the test FILES in another order (the tests of a file stay in theirs): a test that only passes because of what an earlier
    file left behind fails in one of the two (tests/README.md)."""
    files: dict[Path, list[pytest.Item]] = {}
    for item in items:
        files.setdefault(item.path, []).append(item)
    paths = list(files)
    if order == "reverse":
        paths.reverse()
    elif order.startswith("shuffle"):
        random.Random(order.partition(":")[2] or "0").shuffle(paths)
    items[:] = [item for path in paths for item in files[path]]


def pytest_collection_modifyitems(items: "list[pytest.Item]") -> None:
    markers.apply(items)
    guards.add_leak_guard(items)
    if os.environ.get("NEOAPRS_TEST_ORDER"):
        reorder_files(items, os.environ["NEOAPRS_TEST_ORDER"])
