"""The duplication ratchet of the Python half (scripts/dup-check and scripts/dup-compare.py): a new clone, a larger clone and more duplicated lines fail; a clone that is gone does not, and says the
baseline can be tightened. The real jscpd is run by `scripts/check --stage dup-py` (it needs node and ui/node_modules); here a stand-in writes the report, so that what is tested is our logic:
the pair of files as the identity of a clone, the comparison, --update, and what the script passes to jscpd."""
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from tests.support.ptyline import posix_only

pytestmark = posix_only      # (a bash stand-in for jscpd: a development check, not the product)

ROOT = Path(__file__).resolve().parent.parent


def load_compare() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dup_compare", ROOT / "scripts" / "dup-compare.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare = load_compare()


def clone(a: str, b: str, lines: int = 12, a_start: int = 10, b_start: int = 40) -> dict[str, object]:
    return {"format": "python", "lines": lines, "firstFile": {"name": a, "start": a_start}, "secondFile": {"name": b, "start": b_start}}


def report(*clones: dict[str, object], lines: int = 0, percentage: float = 0.0) -> dict[str, object]:
    return {"duplicates": list(clones), "statistics": {"total": {"duplicatedLines": lines, "percentage": percentage}}}


BASELINE = compare.summarize(report(clone("neoaprs/a.py", "neoaprs/b.py", 12), clone("neoaprs/a.py", "neoaprs/b.py", 15), clone("neoaprs/web/x.py", "neoaprs/y.py", 20), lines=45, percentage=0.4))


def test_a_clone_is_the_pair_of_files_and_line_numbers_do_not_matter() -> None:
    assert BASELINE["pairs"] == {"neoaprs/a.py <-> neoaprs/b.py": {"clones": 2, "lines": 27}, "neoaprs/web/x.py <-> neoaprs/y.py": {"clones": 1, "lines": 20}}
    moved = compare.summarize(report(clone("neoaprs/b.py", "neoaprs/a.py", 12, 300, 5), clone("neoaprs/a.py", "neoaprs/b.py", 15, 99, 7), clone("neoaprs/y.py", "neoaprs/web/x.py", 20), lines=45, percentage=0.4))
    assert compare.problems(moved, BASELINE) == []


def test_a_new_clone_a_larger_clone_and_more_duplicated_lines_are_found() -> None:
    new = compare.summarize(report(*[clone("neoaprs/a.py", "neoaprs/b.py", 12), clone("neoaprs/a.py", "neoaprs/b.py", 15), clone("neoaprs/web/x.py", "neoaprs/y.py", 20), clone("neoaprs/c.py", "neoaprs/d.py", 11)], lines=56, percentage=0.5))
    assert compare.problems(new, BASELINE) == ["new clone: neoaprs/c.py <-> neoaprs/d.py (1 clone(s), 11 lines): give the code one home", "duplicated lines went up: 56 (0.5%), baseline 45 (0.4%)"]
    larger = compare.summarize(report(clone("neoaprs/a.py", "neoaprs/b.py", 12), clone("neoaprs/a.py", "neoaprs/b.py", 18), clone("neoaprs/web/x.py", "neoaprs/y.py", 20), lines=45, percentage=0.4))
    assert compare.problems(larger, BASELINE) == ["larger clone: neoaprs/a.py <-> neoaprs/b.py is now 2 clone(s), 30 lines (baseline 2, 27)"]
    third = compare.summarize(report(clone("neoaprs/a.py", "neoaprs/b.py", 12), clone("neoaprs/a.py", "neoaprs/b.py", 15), clone("neoaprs/a.py", "neoaprs/b.py", 10), clone("neoaprs/web/x.py", "neoaprs/y.py", 20), lines=45, percentage=0.4))
    assert compare.problems(third, BASELINE)


def test_a_clone_that_is_gone_passes_and_the_baseline_can_be_tightened() -> None:
    fewer = compare.summarize(report(clone("neoaprs/web/x.py", "neoaprs/y.py", 20), lines=20, percentage=0.2))
    assert compare.problems(fewer, BASELINE) == []
    assert compare.tightenable(fewer, BASELINE) and not compare.tightenable(BASELINE, BASELINE)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    for name in ("dup-check", "dup-compare.py"):
        shutil.copy2(ROOT / "scripts" / name, tmp_path / "scripts" / name)
    (tmp_path / "neoaprs").mkdir()
    (tmp_path / "tests" / "support").mkdir(parents=True)
    return tmp_path


def stand_in(tmp_path: Path, rep: dict[str, object]) -> dict[str, str]:
    """A jscpd that records its arguments and writes `rep` where --output says."""
    (tmp_path / "report.json").write_text(json.dumps(rep))
    stub = tmp_path / "fake-jscpd"
    stub.write_text(f'#!/usr/bin/env bash\necho "$@" > "{tmp_path}/args"\nwhile [ $# -gt 0 ]; do [ "$1" = --output ] && out="$2"; shift; done\ncp "{tmp_path}/report.json" "$out/jscpd-report.json"\n')
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return {"NEOAPRS_JSCPD": str(stub), "NEOAPRS_PYTHON": sys.executable}


def dup_check(tree: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["scripts/dup-check", *args], cwd=tree, env={**os.environ, **env}, capture_output=True, text=True, timeout=60)


def test_the_script_writes_the_first_baseline_passes_on_the_same_clones_and_fails_on_a_new_one(tree: Path) -> None:
    env = stand_in(tree, report(clone("neoaprs/a.py", "neoaprs/b.py", 12), lines=12, percentage=0.1))
    assert dup_check(tree, env, "--update").returncode == 0
    saved = json.loads((tree / "scripts" / "dup-baseline.json").read_text(encoding="utf-8"))
    assert saved["pairs"] == {"neoaprs/a.py <-> neoaprs/b.py": {"clones": 1, "lines": 12}}
    assert dup_check(tree, env).returncode == 0

    env = stand_in(tree, report(clone("neoaprs/a.py", "neoaprs/b.py", 12), clone("neoaprs/c.py", "neoaprs/web/d.py", 30), lines=42, percentage=0.4))
    failed = dup_check(tree, env)
    assert failed.returncode == 1 and "new clone: neoaprs/c.py <-> neoaprs/web/d.py" in failed.stdout
    refused = dup_check(tree, env, "--update")                                          # the baseline is not made larger by --update
    assert refused.returncode == 1 and json.loads((tree / "scripts" / "dup-baseline.json").read_text(encoding="utf-8")) == saved


def test_the_script_asks_jscpd_for_the_agreed_limits_over_the_python_tree(tree: Path) -> None:
    env = stand_in(tree, report())
    (tree / "ui" / "src").mkdir(parents=True)                                           # (the page has its own check, the stage dup)
    assert dup_check(tree, env, "--update").returncode == 0
    args = (tree / "args").read_text(encoding="utf-8")
    assert args.startswith("neoaprs tests/support --min-lines 10 --min-tokens 100 ")
    assert "--reporters json" in args


def test_a_missing_report_or_a_bad_argument_is_an_error_not_a_pass(tree: Path) -> None:
    env = {"NEOAPRS_JSCPD": "false", "NEOAPRS_PYTHON": sys.executable}
    failed = dup_check(tree, env)
    assert failed.returncode == 1 and "jscpd did not produce a report" in failed.stderr
    assert dup_check(tree, env, "--bogus").returncode == 2
