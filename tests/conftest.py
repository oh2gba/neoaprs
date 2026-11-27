import os
import random
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Every message the daemon sends to a page is checked against neoaprs/web/protocol.py;
# a mismatch fails the test, also in a signal handler (see the fixture protocol_violations).
# NEOAPRS_VALIDATE_OUT=0 pytest runs the tests the way production runs.
os.environ.setdefault("NEOAPRS_VALIDATE_OUT", "1")
os.environ.setdefault("NEOAPRS_VALIDATE_RAISE", "1")


# No test may open a serial device of the machine: a board resets when its port is opened and a
# radio may be keyed. The search of every daemon, also in the processes a test starts, looks at
# a pattern that matches nothing. A test of the search names the folder of its pseudo-terminals
# or clears the variable (fixture search_pattern_from_settings).
os.environ["NEOAPRS_SERIAL_PATTERN"] = "/dev/neoaprs-test-no-such-port*"


# No test may ask the version page on the internet: the daily update check (services/updatecheck.py)
# is off in every daemon. A test of the check gives its own address and environment.
os.environ["NEOAPRS_UPDATE_CHECK"] = "0"
# Nor PSK Reporter (services/pskreporter.py): with the check off and no stand-in nothing is reported,
# so a developer's own NEOAPRS_PSKREPORTER is taken away. A test of the reports gives its own.
os.environ.pop("NEOAPRS_PSKREPORTER", None)


# No test may read the machine's sound cards (neoaprs/mercuryhelper.py, alsa_card_names): the card
# names come from a folder that is not there. A test of the names gives its own folder.
os.environ["NEOAPRS_ALSA_ROOT"] = "/nonexistent/neoaprs-test-asound"
# Nor the USB devices (neoaprs/usbtie.py).
os.environ["NEOAPRS_SYS_ROOT"] = "/nonexistent/neoaprs-test-sys"


# No test may play sound on the developer's speakers: a daemon on the Dummy HF radio plays what it
# sends through the system's player (neoaprs/mercuryspeaker.py). The players are looked for in a
# folder that is not there; a test of the speaker gives its own player.
os.environ["NEOAPRS_PLAYER_PATH"] = "/nonexistent/neoaprs-test-players"


# No test may reach the developer's desktop: a daemon that gets a message runs the default alert
# command (notify-send or kdialog, and a sound). Without the session's display and message bus it
# finds no desktop; a test of the alert command gives its own command.
for _name in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY"):
    os.environ.pop(_name, None)


# No process a test starts may open a real device or reach a real service, whatever its settings:
# every one inherits the no-devices switch (neoaprs/nodevices.py), which closes the doors the
# variables above leave open (a named serial port, Mercury on a sound card, APRS-IS, a Bluetooth
# address, another computer). The fixture devices_are_fakes lifts it in the test's own process.
os.environ["NEOAPRS_NO_DEVICES"] = "1"


# 'ci' is the default profile so that a run is reproducible (derandomized, no example database).
# HYPOTHESIS_PROFILE=dev explores far more and keeps what it finds in .hypothesis/.
try:
    from hypothesis import settings as _hypothesis_settings
except ImportError:
    pass
else:
    _hypothesis_settings.register_profile("ci", max_examples=200, deadline=None, derandomize=True, database=None)
    _hypothesis_settings.register_profile("dev", max_examples=2000, deadline=None)
    _hypothesis_settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))

from tests.support.clock import FixedClock  # noqa: E402, F401
from tests.support.files import FIXTURES, fixture_bytes, fixture_text  # noqa: E402, F401
from tests.support.fixtures import (  # noqa: E402
    clock,  # noqa: F401
    no_shipped_world,  # noqa: F401
    pauses_are_zero,  # noqa: F401
    protocol_violations,  # noqa: F401
    real_pauses,  # noqa: F401
    search_pattern_from_settings,  # noqa: F401
    tmp_data,  # noqa: F401
    ui_port_near_the_pair,  # noqa: F401
)
from tests.support import guards, markers  # noqa: E402
from tests.support.guards import (  # noqa: E402
    doors_of_the_module,  # noqa: F401
    doors_of_the_session,  # noqa: F401
    isolated_machine,  # noqa: F401
    logging_restored,  # noqa: F401
    no_leaked_db_threads,  # noqa: F401
    no_leaked_tasks,  # noqa: F401
    no_unexpected_errors,  # noqa: F401
)
from tests.support.ptyline import ptys  # noqa: E402, F401
from tests.support.timelimit import a_test_has_a_time_limit  # noqa: E402, F401
from tests.support import winloop  # noqa: E402


if sys.platform == "win32":

    def pytest_asyncio_loop_factories(config: pytest.Config, item: pytest.Item) -> dict[str, object]:
        """The event loop of every test on Windows: nudged from outside so that it cannot sleep
        forever while work waits (tests/support/winloop.py). Elsewhere the hook is absent."""
        return {"nudged": winloop.new_loop}


@pytest.fixture(autouse=True)
def devices_are_fakes(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Lift the no-devices switch in the test's own process.

    The guards of tests/support/guards.py watch the same doors, and the fakes behind them (a
    pseudo-terminal, the made-up Mercury, a socket pair) would be refused by the switch. The
    variable stays in the environment for processes the test starts. Tests of the switch itself use
    the fixture `under_the_switch` (tests/test_no_devices.py).
    """
    if "under_the_switch" not in request.fixturenames:
        monkeypatch.setattr("neoaprs.nodevices.on", lambda: False)


@pytest.fixture(autouse=True)
def no_watchdog_of_the_test_process(monkeypatch: pytest.MonkeyPatch) -> "list[float]":
    """The app's watchdog of its own end (neoaprs/desktop/endafter.py) would end this test process: a
    Quit only records the bound it would have given. A test of the watchdog starts it for a child of its own."""
    asked: list[float] = []
    monkeypatch.setattr("neoaprs.desktop.endafter.watch", lambda seconds, *a, **k: asked.append(seconds) or True)
    return asked


def reorder_files(items: "list[pytest.Item]", order: str) -> None:
    """NEOAPRS_TEST_ORDER=reverse|shuffle[:SEED] runs the test files in another order (the tests of
    a file keep theirs), to expose a test that depends on what an earlier file left
    (tests/README.md)."""
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
    """Refuse a run that would make its scratch folders in the repository.

    Without a writable temporary folder and with no TMPDIR, Python falls back to the current folder.
    """
    if config.option.basetemp is None:
        scratch = Path(tempfile.gettempdir()).resolve()
        if scratch == ROOT or ROOT in scratch.parents:
            raise pytest.UsageError(
                f"the temporary folder is {scratch}, inside the repository (the system's cannot be written): set TMPDIR to a folder outside it"
            )
