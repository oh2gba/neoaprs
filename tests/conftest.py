import os
import random
import sys
import tempfile
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


# No test may ask the version page on the internet (the daily update check of the daemon, services/updatecheck.py): the check of every daemon, in this process and in the processes the tests start, is off. A test of the check
# gives its own address on the loopback and its own environment.
os.environ["NEOAPRS_UPDATE_CHECK"] = "0"


# No test may read the sound cards of the machine it runs on (neoaprs/mercuryhelper.py, alsa_card_names): the cards' names come from a folder that is not there. A test of the names gives its own folder.
os.environ["NEOAPRS_ALSA_ROOT"] = "/nonexistent/neoaprs-test-asound"


# No test may play sound on the developer's speakers: a daemon a test starts on the Dummy HF radio plays what it sends as Mercury's real audio through the system's player (neoaprs/mercuryspeaker.py), which John heard
# from his speakers as the beacons of the suite (4 Nov 2026). The players are looked for in a folder that is not there; a test of the speaker gives its own player.
os.environ["NEOAPRS_PLAYER_PATH"] = "/nonexistent/neoaprs-test-players"


# No test may reach the developer's desktop: a daemon a test starts that gets a message runs the default alert command (notify-send, else kdialog's pop-up, and a sound), which showed John a stream of pop-ups while the suite and
# the simulators ran (3 Nov 2026). Without the session's display and message bus the command finds no desktop and does nothing visible; a test of the alert command gives its own command.
for _name in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY"):
    os.environ.pop(_name, None)


# No process a test starts may open a real device or talk to a real service, whatever settings it is given: every one inherits the no-devices switch (neoaprs/nodevices.py), which shuts the doors the variables above leave open (a
# serial port that is named, the Mercury program on a sound card, APRS-IS, a Bluetooth address, a server on another computer). In the test's own process the fixture devices_are_fakes, below, lifts it.
os.environ["NEOAPRS_NO_DEVICES"] = "1"


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
from tests.support.fixtures import clock, no_shipped_world, protocol_violations, search_pattern_from_settings, tmp_data, ui_port_near_the_pair  # noqa: E402, F401
from tests.support import guards, markers  # noqa: E402
from tests.support.guards import isolated_machine, logging_restored, no_leaked_db_threads, no_leaked_tasks, no_unexpected_errors  # noqa: E402, F401
from tests.support.ptyline import ptys  # noqa: E402, F401


@pytest.fixture(autouse=True)
def devices_are_fakes(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """In the test's own process the no-devices switch is lifted. There the guards of tests/support/guards.py watch the same doors and fail the test that reaches a real device, and behind those doors stand the fakes
    that the tests of them use (a pseudo-terminal for a serial port, the made-up Mercury program, a socket pair for Bluetooth), which the switch would refuse as it refuses the real things. The variable stays in the
    environment, so every process the test starts runs under the switch. A test of the switch itself asks for the fixture `under_the_switch` (tests/test_no_devices.py) and keeps it on."""
    if "under_the_switch" not in request.fixturenames:
        monkeypatch.setattr("neoaprs.nodevices.on", lambda: False)


@pytest.fixture
def switch_lifted_for_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test starts a process behind one of whose doors a fake of the test stands (the made-up pmtiles program on its PATH, which is given the address of a map server that does not exist): NEOAPRS_NO_DEVICES, which
    tests/conftest.py sets for every process a test starts, is taken out of the environment that process inherits. Nothing but the test then keeps the process from a real device or service: it gives it fakes only."""
    monkeypatch.delenv("NEOAPRS_NO_DEVICES")


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


def pytest_configure(config: pytest.Config) -> None:
    """No run makes its scratch folders in the repository. Where the system's temporary folder cannot be written and TMPDIR names none, Python's last resort is the current folder, and pytest (under -n,
    before any test or fixture) makes its `pytest-of-<user>` there: such a run is refused before it starts."""
    if config.option.basetemp is None:
        scratch = Path(tempfile.gettempdir()).resolve()
        if scratch == ROOT or ROOT in scratch.parents:
            raise pytest.UsageError(f"the temporary folder is {scratch}, inside the repository (the system's cannot be written): set TMPDIR to a folder outside it")
