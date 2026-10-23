"""scripts/install.sh, the wrapper of a clone, in a copy of the tree: it calls `neoaprs service install` of the clone's venv with the clone's data folder and enables lingering, and
`--remove` calls `service remove`. A HOME of the test's own and a systemctl and loginctl that only write down their arguments: the unit written is the reference unit of the clone, nothing here reaches
the user's systemd. The command itself is held in tests/test_service.py."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs.cli import servicesystemd
from tests.conftest import ROOT
from tests.support.faketools import FakeTools
from tests.test_service import reference_unit
from tests.support.ptyline import posix_only

pytestmark = posix_only      # (install.sh, a shell script of a clone: a development check, not the product)


class Setup:
    def __init__(self, tmp_path: Path, folder: str = "clone") -> None:
        self.clone = tmp_path / folder
        self.home = tmp_path / "home"
        (self.clone / "scripts").mkdir(parents=True)
        (self.clone / ".venv" / "bin").mkdir(parents=True)
        (self.clone / ".venv" / "bin" / "python").symlink_to(sys.executable)           # (the clone's venv python: the interpreter of the test, under the clone's path)
        shutil.copy(ROOT / "scripts" / "install.sh", self.clone / "scripts" / "install.sh")
        self.home.mkdir()
        self.tools = FakeTools(tmp_path / "bin", tmp_path / "calls", ("systemctl", "loginctl"))
        self.unit = self.home / ".config" / "systemd" / "user" / "neoaprs.service"

    def run(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        environment = {"PATH": f"{self.tools.folder}:{os.environ['PATH']}", "HOME": str(self.home), "USER": "tester", "FAKE_CALLS": str(self.tools.calls_file), "FAKE_FAIL": "", "FAKE_LINGER": "no",
                       "LC_ALL": "C.UTF-8", "PYTHONPATH": str(ROOT), "NEOAPRS_SERIAL_PATTERN": os.environ["NEOAPRS_SERIAL_PATTERN"], **env}
        return subprocess.run([str(self.clone / "scripts" / "install.sh"), *args], cwd=self.clone.parent, env=environment, capture_output=True, text=True, timeout=60)


@pytest.fixture
def s(tmp_path: Path) -> Setup:
    return Setup(tmp_path)


def test_install_writes_the_reference_unit_for_the_clone_and_enables_lingering(s: Setup) -> None:
    done = s.run()
    assert done.returncode == 0, done.stdout + done.stderr
    text = s.unit.read_text(encoding="utf-8")
    assert servicesystemd.effect(text) == servicesystemd.effect(reference_unit(s.clone)), "the same unit in effect: the clone's python, the clone's data, the clone as working directory"
    assert f"ExecStart={s.clone}/.venv/bin/python -m neoaprs --data {s.clone}/data\n" in text and f"WorkingDirectory={s.clone}\n" in text and f"Documentation=file://{s.clone}/README.md\n" in text
    calls = s.tools.calls()
    assert [c for c in calls if c.startswith("systemctl ")] == ["systemctl --user daemon-reload", "systemctl --user enable --now neoaprs.service"]
    assert (s.clone / "data").is_dir()
    assert "loginctl enable-linger tester" in calls, "the script always enabled lingering"


def test_running_it_again_after_a_pull_changes_nothing_when_the_unit_is_the_same(s: Setup) -> None:
    assert s.run().returncode == 0
    before = s.unit.stat().st_mtime_ns
    done = s.run()
    assert done.returncode == 0 and s.unit.stat().st_mtime_ns == before and "wrote" not in done.stdout and "restarted" not in done.stdout


def test_remove_stops_disables_and_deletes_the_written_file(s: Setup) -> None:
    assert s.run().returncode == 0
    s.tools.calls()
    done = s.run("--remove")
    assert done.returncode == 0, done.stdout + done.stderr
    assert not s.unit.exists() and s.tools.calls("systemctl ") == ["systemctl --user disable --now neoaprs.service", "systemctl --user daemon-reload"] and (s.clone / "data").is_dir()


def test_a_unit_it_did_not_write_is_never_touched_and_the_exit_code_says_so(s: Setup) -> None:
    s.unit.parent.mkdir(parents=True)
    s.unit.write_text("[Service]\nExecStart=/old/python\n")
    done = s.run()
    assert done.returncode == 1 and "was not written by neoaprs" in done.stdout and s.unit.read_text(encoding="utf-8") == "[Service]\nExecStart=/old/python\n"
    assert s.tools.calls("systemctl ") == []


def test_without_a_venv_it_says_so_and_writes_nothing(s: Setup) -> None:
    (s.clone / ".venv" / "bin" / "python").unlink()
    done = s.run()
    assert done.returncode == 1 and "uv sync --frozen" in done.stdout and not s.unit.exists() and s.tools.calls("systemctl ") == []


def test_a_wrong_argument_is_refused(s: Setup) -> None:
    done = s.run("--frobnicate")
    assert done.returncode == 2 and "unknown argument" in done.stderr and not s.unit.exists()


def test_help_prints_the_comment_and_does_nothing_else(s: Setup) -> None:
    done = s.run("--help")
    assert done.returncode == 0 and "--remove" in done.stdout and "thin wrapper" in done.stdout
    assert not s.home.joinpath(".config").exists() and s.tools.calls() == []
