"""The time limit of a test (tests/support/timelimit.py), on pytest run as a process over a test file of its own: a test that hangs ends the run, with its name and the stacks, and a test inside its limit is as it was."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import ROOT
from tests.support import timelimit

HUNG = "import time\n\n\ndef test_hangs():\n    time.sleep(600)\n"
FAST = "def test_passes():\n    assert True\n"


def run_pytest(folder: Path, limit: str) -> "subprocess.CompletedProcess[str]":
    env = {**os.environ, "NEOAPRS_TEST_LIMIT_SEC": limit, "PYTHONPATH": str(ROOT)}
    return subprocess.run([sys.executable, "-m", "pytest", "-p", "tests.support.timelimit", "-p", "no:cacheprovider", "--rootdir", str(folder), str(folder)], cwd=folder, env=env, capture_output=True, text=True, timeout=120, check=False)


def test_a_test_that_hangs_ends_the_run_with_its_name_and_the_stack_where_it_waits(tmp_path: Path) -> None:
    (tmp_path / "test_hung.py").write_text(HUNG, encoding="utf-8")
    done = run_pytest(tmp_path, "2")
    assert done.returncode == timelimit.EXIT_CODE
    assert "test_hung.py::test_hangs ran over its time limit of 2 s" in done.stderr and "in test_hangs" in done.stderr, done.stderr


def test_a_test_inside_its_limit_passes_and_a_limit_of_zero_is_none(tmp_path: Path) -> None:
    (tmp_path / "test_fast.py").write_text(FAST, encoding="utf-8")
    assert run_pytest(tmp_path, "30").returncode == 0
    assert run_pytest(tmp_path, "0").returncode == 0


def test_a_limit_that_is_not_a_number_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEOAPRS_TEST_LIMIT_SEC", "soon")
    assert timelimit.limit_sec() == timelimit.LIMIT_SEC
    monkeypatch.delenv("NEOAPRS_TEST_LIMIT_SEC")
    assert timelimit.limit_sec() == timelimit.LIMIT_SEC
