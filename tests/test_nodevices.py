"""No test opens a serial device of the machine: NEOAPRS_SERIAL_PATTERN (neoaprs/serialprobe.py), which tests/conftest.py sets for every test and every process a test starts, makes the search of any daemon look at a
pattern that matches nothing; and the guards of tests/support/guards.py fail the test that opens a device file anyway or starts neoaprs with an environment that lacks the variable."""
import os
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import serialprobe
from neoaprs.config import DEFAULTS
from neoaprs.serialprobe import PATTERN_ENV, candidate_ports, search_pattern
from neoaprs.tnc import Tnc
from neoaprs.wiring import tnc_settings
from tests.conftest import ROOT
from tests.support import guards
from tests.support.ptyline import make_pty, posix_only


def test_every_test_starts_with_a_pattern_that_matches_nothing() -> None:
    pattern = os.environ[PATTERN_ENV]
    assert pattern.startswith("/dev/") and candidate_ports(pattern) == []
    assert search_pattern() == pattern and search_pattern("/dev/ttyACM*") == pattern


def test_the_variable_wins_over_the_setting_and_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PATTERN_ENV, "/x/one_* /x/two_*")
    assert tnc_settings(DEFAULTS).pattern == "/x/one_* /x/two_*"
    assert tnc_settings(replace(DEFAULTS, serial_pattern="/dev/brainbox_*")).pattern == "/x/one_* /x/two_*"
    assert Tnc().pattern == "/x/one_* /x/two_*", "a Tnc made with no pattern searches the variable's, not the default"
    assert Tnc(pattern="/y/*").pattern == "/y/*", "a pattern that is given is the caller's choice"


def test_a_pattern_given_for_this_run_wins_over_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PATTERN_ENV, "/x/one_*")
    assert tnc_settings(DEFAULTS, pattern_override="/tmp/probe_*").pattern == "/tmp/probe_*"


def test_an_empty_variable_leaves_the_setting_and_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("", "   "):
        monkeypatch.setenv(PATTERN_ENV, value)
        assert tnc_settings(DEFAULTS).pattern == DEFAULTS.serial_pattern == serialprobe.DEFAULT_PATTERN
        assert tnc_settings(replace(DEFAULTS, serial_pattern="/dev/brainbox_*")).pattern == "/dev/brainbox_*"
        assert Tnc().pattern == serialprobe.DEFAULT_PATTERN
    monkeypatch.delenv(PATTERN_ENV)
    assert tnc_settings(DEFAULTS).pattern == serialprobe.DEFAULT_PATTERN


def test_a_named_port_is_not_touched_by_the_variable() -> None:
    assert tnc_settings(DEFAULTS, "/dev/pts/4").port == "/dev/pts/4"
    assert tnc_settings(replace(DEFAULTS, serial_port="/dev/ttyUSB0")).port == "/dev/ttyUSB0"


def test_a_process_a_test_starts_inherits_the_variable_and_searches_no_port(tmp_path: Path) -> None:
    """`neoaprs capture` with no port lists the ports its search would listen to: here there are none, so it says so and ends at once, without a look at /dev."""
    out = tmp_path / "out.kiss"
    done = subprocess.run([sys.executable, "-m", "neoaprs", "capture", str(out)], cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, capture_output=True, text=True, timeout=60)
    assert done.returncode == 1 and "no USB serial port to look at here" in done.stderr + done.stdout, done
    assert not out.exists()


# ---- the guards

@pytest.mark.parametrize("path", ["/dev/ttyACM0", "/dev/ttyUSB3", "/dev/ttyS0", "/dev/brainbox_2", "/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit-if00", "/dev/rfcomm0", "/dev/cu.usbserial-1410", b"/dev/ttyACM1"])
def test_the_serial_guard_refuses_the_serial_devices(path: str | bytes) -> None:
    radio = guards.SerialGuard()
    with pytest.raises(guards.RadioTouched):
        radio.check(path)
    assert radio.refused == [os.fsdecode(path)]


@posix_only
def test_the_serial_guard_looks_through_a_link_and_knows_a_device_by_its_number(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    link = tmp_path / "mine"
    link.symlink_to("/dev/ttyACM0")
    radio = guards.SerialGuard()
    with pytest.raises(guards.RadioTouched):
        radio.check(link)
    node = SimpleNamespace(st_mode=stat.S_IFCHR | 0o660, st_rdev=os.makedev(188, 3))
    real_stat = os.stat
    monkeypatch.setattr(guards.os, "stat", lambda path, *a, **k: node if path == "/dev/my-adapter" else real_stat(path, *a, **k))
    with pytest.raises(guards.RadioTouched):
        radio.check("/dev/my-adapter")
    assert radio.refused == [str(link), "/dev/my-adapter"]


@posix_only
def test_the_serial_guard_lets_a_pseudo_terminal_through() -> None:
    master, slave = make_pty()
    try:
        radio = guards.SerialGuard()
        radio.check(slave)
        radio.check("/dev/null")
        radio.check("/dev/pts/ptmx")
        assert radio.refused == []
    finally:
        os.close(master)


@pytest.mark.parametrize("args", [
    [sys.executable, "-m", "neoaprs", "--data", "d"], [sys.executable, "-m", "neoaprs.services.mapfetch"], ["/venv/bin/neoaprs", "run"], ["neoaprs"], ["C:\\venv\\Scripts\\neoaprs.exe"], ["/x/neoaprs-app"], "neoaprs run"])
def test_the_process_guard_refuses_neoaprs_with_an_environment_that_lacks_the_variable(args: object) -> None:
    processes = guards.ProcessGuard()
    for env in ({}, {"HOME": "/h"}, {guards.SEARCH_VARIABLE: ""}):
        with pytest.raises(guards.RadioTouched):
            processes.check(args, env)
    assert len(processes.refused) == 3


def test_the_process_guard_lets_through_what_cannot_search() -> None:
    processes = guards.ProcessGuard()
    processes.check([sys.executable, "-m", "neoaprs", "--data", "d"], None)                        # (the environment of this process, which has the variable)
    processes.check([sys.executable, "-m", "neoaprs", "--data", "d"], {guards.SEARCH_VARIABLE: "/dev/none*"})
    processes.check(["git", "status"], {})
    processes.check([sys.executable, "-m", "pytest"], {})
    processes.check(["/x/neoaprs-tool/other"], {})
    assert processes.refused == []


def test_the_process_guard_is_in_place_for_every_test() -> None:
    assert subprocess.Popen.__init__.__name__ == "guarded_init"
