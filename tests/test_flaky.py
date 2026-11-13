"""The hunt for tests that fail on some runs only (scripts/flaky) as far as it can be held without docker: which setting each run has, the command inside the container, what the log of a run says (the tests that failed with
their first line, the end of a run that did not reach the tests, the stack of a run that hung), the report, and the script from end to end on a stand-in for docker that answers each run as a list of rules says; and the
plugin that puts the tests in another order (tests/support/shuffle.py) on pytest run over test files of its own. A real run in the image is the coordinator's (docs/development.md)."""
import importlib.machinery
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from tests.conftest import ROOT
from tests.support.ptyline import posix_only
from tests.support.shuffle import shuffled

pytestmark = posix_only      # (a script of the repository that starts containers: a development check, not the product)

SCRIPT = ROOT / "scripts" / "flaky"
CONTAINER = ROOT / "scripts" / "check-in-container"
PATIENCE_SEC = 120.0          # for a wait that includes the start of programs
linux_only = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the container script reads the cores from /sys, which is Linux's")


@pytest.fixture(scope="module")
def flaky() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("flaky", str(SCRIPT))
    spec = importlib.util.spec_from_loader("flaky", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["flaky"] = module                       # (the dataclasses of the script look their module up by name)
    loader.exec_module(module)
    return module


CI = ("uv sync --frozen --extra app --extra ble", "scripts/check --stage lock", "scripts/check --stage ruff", "scripts/check --stage pytest")


# ---- the settings and the command ----

def test_the_runs_go_round_the_four_settings_and_every_four_have_each_once(flaky: ModuleType) -> None:
    runs = [flaky.plan(number) for number in range(20)]
    assert [run.setting for run in runs[:4]] == list(flaky.SETTINGS) == ["runner/file order", "runner/shuffled", "starved/file order", "starved/shuffled"]
    assert [(run.starved, run.seed is not None) for run in runs[:4]] == [(False, False), (False, True), (True, False), (True, True)]
    for setting in flaky.SETTINGS:
        assert sum(1 for run in runs if run.setting == setting) == 5, "twenty runs are five of each: half in file order and half shuffled, half in the runner's size and half starved"
    assert [run.seed for run in runs if run.seed is not None] == [1, 3, 5, 7, 9, 11, 13, 15, 17, 19], "the seed is the number of the run: another run is another order, and a run can be asked for again"


def test_the_command_inside_is_the_ci_install_and_the_ci_tests_with_the_plugin_only_where_the_order_is_a_seeds(flaky: ModuleType) -> None:
    in_order = flaky.command(flaky.plan(0), CI)
    assert in_order == ["bash", "-c", "uv sync --frozen --extra app --extra ble && COLUMNS=200 scripts/check --stage pytest"]
    shuffled_run = flaky.command(flaky.plan(5), CI)
    assert shuffled_run == ["bash", "-c", "uv sync --frozen --extra app --extra ble && COLUMNS=200 PYTEST_ADDOPTS='-p tests.support.shuffle --shuffle-seed 5' scripts/check --stage pytest"]


def test_the_commands_are_the_ones_the_container_script_holds_for_the_ci(flaky: ModuleType) -> None:
    container = flaky.load_container()
    assert container.CI_COMMANDS[0] == "uv sync --frozen --extra app --extra ble" and container.CI_COMMANDS[-1] == "scripts/check --stage pytest", "the first and the last of the CI's lines are the install and the tests"
    assert flaky.command(flaky.plan(0), container.CI_COMMANDS)[2].startswith(f"{container.CI_COMMANDS[0]} && ")


# ---- the log of a run ----

PYTEST_LOG = """\
FAIL  pytest       301.5s
      | ............F...........s.....F.............
      | =================================== FAILURES ===================================
      | /home/runner/work/neoaprs/tests/test_a.py:12: AssertionError: assert 3 < 1
      | =========================== short test summary info ============================
      | FAILED tests/test_a.py::test_one - assert 3 < 1
      | ERROR tests/test_b.py::test_two - OSError: [Errno 98] Address already in use
      | FAILED tests/test_c.py::test_three
      | FAILED tests/test_d.py::test_four[x - y] - worker 'gw3' crashed while running 'tests/test_d.py::test_four[x - y]'
      | tests/test_d.py::test_four[x - y] ran over its time limit of 600 s and is ended here (NEOAPRS_TEST_LIMIT_SEC); the stack of every thread:
      | 3 failed, 1 error, 6005 passed, 389 skipped in 301.52s (0:05:01)
"""


def read(flaky: ModuleType, text: str, hung: bool = False, code: int = 0) -> Any:
    result = flaky.Result(flaky.plan(0), hung=hung, code=code)
    flaky.read_log(text, result)
    return result


def test_the_failures_of_a_log_are_the_tests_with_their_first_line_and_a_test_that_ran_out_of_time_says_so(flaky: ModuleType) -> None:
    result = read(flaky, PYTEST_LOG)
    assert result.failures == {"tests/test_a.py::test_one": "assert 3 < 1", "tests/test_b.py::test_two": "OSError: [Errno 98] Address already in use", "tests/test_c.py::test_three": "no message",
                               "tests/test_d.py::test_four[x - y]": "ran over its time limit of 600 s"}
    assert result.summary == "3 failed, 1 error, 6005 passed, 389 skipped"


def test_a_run_that_did_not_get_to_the_tests_has_the_end_of_its_log_and_no_failures(flaky: ModuleType) -> None:
    text = "\n".join(f"line {number}" for number in range(40)) + "\nerror: Failed to install: no network\n"
    result = read(flaky, text, code=1)
    assert result.failures == {} and result.summary == "" and result.tail[-1] == "error: Failed to install: no network" and len(result.tail) == flaky.LOG_TAIL_LINES
    assert result.word == "not run"


def test_a_green_run_has_no_tail_though_the_log_of_a_green_stage_has_no_summary_line(flaky: ModuleType) -> None:
    """scripts/check prints the output of a stage only when it failed: the log of a green run is the uv lines and the result lines."""
    result = read(flaky, "Resolved 90 packages in 2ms\nok    pytest       612.3s\nall green in 612s\n")
    assert result.tail == [] and result.word == "ok"
    assert "did not get to the tests" not in "\n".join(flaky.report([result]))


def test_by_default_as_many_runs_side_by_side_as_the_machine_has_groups_of_four_threads(flaky: ModuleType) -> None:
    def parallel(*cores: tuple[int, ...]) -> int:
        return flaky.default_parallel(SimpleNamespace(read_cores=lambda: list(cores), RUNNER=SimpleNamespace(threads=4)))
    assert parallel(*((cpu,) for cpu in range(8))) == 2, "eight cores without siblings are eight threads: two runs of four, not four"
    assert parallel(*((cpu, cpu + 16) for cpu in range(16))) == 4 and parallel(*((cpu, cpu + 8) for cpu in range(8))) == 4
    assert parallel((0, 1)) == 1 and parallel() == 1


def test_a_stack_in_the_log_of_a_run_that_failed_is_kept_too(flaky: ModuleType) -> None:
    result = read(flaky, "      | Timeout (0:02:00)!\n      | Thread 0x1 (most recent call first):\n      |   File \"tests/test_x.py\", line 9 in test_waits\n      | \n      | FAILED tests/test_x.py::test_waits - boom\n")
    result.code = 1
    assert result.stack[0] == "Timeout (0:02:00)!" and result.stack[-1].endswith("in test_waits") and list(result.failures) == ["tests/test_x.py::test_waits"]
    assert "run 1 had a test that ran over two minutes (runner/file order); the stack that faulthandler_timeout printed last:" in "\n".join(flaky.report([result]))


def test_a_run_that_hung_has_the_last_stack_faulthandler_printed(flaky: ModuleType) -> None:
    text = "Timeout (0:02:00)!\nThread 0x1 (most recent call first):\n  File \"old.py\", line 1\nTimeout (0:02:00)!\nThread 0x2 (most recent call first):\n  File \"tests/test_x.py\", line 9 in test_waits\n"
    result = read(flaky, text, hung=True)
    assert result.stack[0] == "Timeout (0:02:00)!" and result.stack[-1] == "  File \"tests/test_x.py\", line 9 in test_waits" and "old.py" not in "".join(result.stack)
    assert result.word == "hung"


def test_the_word_of_a_run_is_ok_failed_hung_or_not_run(flaky: ModuleType) -> None:
    assert flaky.Result(flaky.plan(0)).word == "ok"
    assert flaky.Result(flaky.plan(0), code=1, summary="1 failed").word == "failed"
    assert flaky.Result(flaky.plan(0), code=125).word == "not run"
    assert flaky.Result(flaky.plan(0), hung=True, code=143).word == "hung"


# ---- the report ----

def result(flaky: ModuleType, number: int, *failed: tuple[str, str]) -> Any:
    made = flaky.Result(flaky.plan(number), code=1 if failed else 0, seconds=61.0, summary="1 failed, 5 passed" if failed else "6 passed", log=Path(f"run-{number:02d}.log"))
    made.failures = dict(failed)
    return made


def test_the_table_has_every_test_that_failed_with_its_count_its_settings_and_its_first_line_most_often_first(flaky: ModuleType) -> None:
    results = [result(flaky, 0), result(flaky, 1, ("tests/test_a.py::test_one", "assert 3 < 1")), result(flaky, 2, ("tests/test_b.py::test_two", "OSError"), ("tests/test_a.py::test_one", "assert 4 < 1")),
               result(flaky, 3, ("tests/test_a.py::test_one", "assert 5 < 1")), result(flaky, 4), result(flaky, 5, ("tests/test_a.py::test_one", "assert 6 < 1"))]
    lines = flaky.report(list(reversed(results)))
    assert [line.split()[1] for line in lines[:6]] == ["1", "2", "3", "4", "5", "6"], "the lines of the runs are in their order, whatever order they finished in"
    body = "\n".join(lines)
    header = next(line for line in lines if line.startswith("test "))
    rows = lines[lines.index(header) + 2:lines.index(header) + 4]
    assert [cell.strip() for cell in rows[0].split("|")] == ["tests/test_a.py::test_one", "4", "6", "runner/shuffled 2, starved/file order 1, starved/shuffled 1", "assert 3 < 1"]
    assert [cell.strip() for cell in rows[1].split("|")] == ["tests/test_b.py::test_two", "1", "6", "starved/file order 1", "OSError"]
    assert "2 of 6 runs green; 2 tests failed in at least one run" in body


def test_with_no_failure_the_report_says_so(flaky: ModuleType) -> None:
    lines = flaky.report([result(flaky, 0), result(flaky, 1)])
    assert "no test failed in any run" in lines and lines[-1] == "2 of 2 runs green; 0 tests failed in at least one run"
    assert not any(line.startswith("test ") for line in lines)


def test_a_hung_run_and_a_run_that_did_not_start_have_their_evidence_under_the_table(flaky: ModuleType) -> None:
    hung, stopped = result(flaky, 1), result(flaky, 2)
    hung.hung, hung.code, hung.stack = True, 143, ["Timeout (0:02:00)!", "  File \"x.py\", line 1"]
    stopped.code, stopped.summary, stopped.tail = 125, "", ["docker: no space left on device"]
    text = "\n".join(flaky.report([hung, stopped]))
    assert "run 2 hung (runner/shuffled); the stack that faulthandler_timeout printed last:\n    Timeout (0:02:00)!\n      File \"x.py\", line 1" in text
    assert "run 3 did not get to the tests (exit 125); the end of its log:\n    docker: no space left on device" in text


# ---- the script from end to end, on a stand-in for docker ----

FAKE_DOCKER = f"""#!{sys.executable}
\"\"\"Stands in for docker: answers `run` as the rules of $FAKE_DOCKER/rules.json say (the first rule that fits the run's memory and shuffle seed), and writes down every call.\"\"\"
import json, os, re, signal, sys, time
state = os.environ["FAKE_DOCKER"]
args = sys.argv[1:]
with open(state + "/calls", "a") as calls:
    calls.write(" ".join(args[:2]) + "\\n")
if args[0] == "image":
    sys.exit(0 if os.path.exists(state + "/has-image") else 1)
if args[0] == "build":
    sys.stdin.buffer.read()
    sys.exit(1 if os.path.exists(state + "/build-fails") else 0)
if args[0] == "ps":
    sys.exit(0)
if args[0] == "rm":
    try:
        os.kill(int(open(state + "/pid-" + args[-1]).read()), signal.SIGKILL)
    except (OSError, ValueError):
        pass
    sys.exit(0)
if args[0] == "run":
    cid = "c" + str(os.getpid())
    open(args[args.index("--cidfile") + 1], "w").write(cid)
    open(state + "/pid-" + cid, "w").write(str(os.getpid()))
    sys.stdin.buffer.read()
    line = args[-1]
    seed = re.search(r"--shuffle-seed (\\d+)", line)
    starved = args[args.index("--memory") + 1] == "7g"
    with open(state + "/runs", "a") as runs:
        runs.write(json.dumps({{"starved": starved, "seed": int(seed.group(1)) if seed else None, "line": line}}) + "\\n")
    for rule in json.load(open(state + "/rules.json")):
        if rule.get("starved") in (None, starved) and rule.get("seed", "any") in ("any", int(seed.group(1)) if seed else None):
            print(rule.get("stdout", ""), flush=True)
            if rule.get("hang"):
                time.sleep(600)
            sys.exit(rule.get("exit", 0))
    print("ok    pytest       1.0s\\nall green in 1s")
    sys.exit(0)
"""


class Rig:
    """The two scripts in a made-up repository of their own (the container script packs the repository it lies in), a stand-in for docker first on the PATH, and the rules it answers by."""

    def __init__(self, tmp_path: Path) -> None:
        self.repo, self.state, self.out = tmp_path / "repo", tmp_path / "docker", tmp_path / "out"
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / "packaging" / "ci").mkdir(parents=True)
        shutil.copy(SCRIPT, self.repo / "scripts" / "flaky")
        shutil.copy(CONTAINER, self.repo / "scripts" / "check-in-container")
        shutil.copy(ROOT / "packaging" / "ci" / "Dockerfile", self.repo / "packaging" / "ci" / "Dockerfile")
        home, self.bin, runtime, temp, self.started_in = tmp_path / "home", tmp_path / "bin", tmp_path / "runtime", tmp_path / "temp", tmp_path / "started-in"
        for made in (self.state, home, self.bin, runtime, temp, self.started_in):
            made.mkdir()
        (self.bin / "docker").write_text(FAKE_DOCKER)
        (self.bin / "docker").chmod(0o755)
        (self.state / "has-image").write_text("")
        self.env = {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "HOME": str(home), "TMPDIR": str(temp), "FAKE_DOCKER": str(self.state), "XDG_RUNTIME_DIR": str(runtime), "LC_ALL": "C.UTF-8"}
        self.rules(())
        git = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")} | {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CEILING_DIRECTORIES": str(tmp_path)}
        for line in (["init", "--quiet", "--initial-branch=master"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "--quiet", "-m", "x"]):
            assert subprocess.run(["git", "-C", str(self.repo), *line], env=git, capture_output=True).returncode == 0

    def rules(self, rules: tuple[dict[str, Any], ...]) -> None:
        (self.state / "rules.json").write_text(json.dumps(list(rules)))

    def run(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(self.repo / "scripts" / "flaky"), "--out", str(self.out), *args]
        return subprocess.run(command, cwd=self.started_in, env=env or self.env, capture_output=True, text=True, timeout=PATIENCE_SEC)

    def started(self) -> list[dict[str, Any]]:
        file = self.state / "runs"
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []

    def calls(self) -> list[str]:
        return (self.state / "calls").read_text().splitlines() if (self.state / "calls").exists() else []


@pytest.fixture
def rig() -> Callable[[Path], Rig]:
    if shutil.which("git") is None:
        pytest.skip("needs git")
    return Rig


@linux_only
def test_eight_runs_are_four_settings_twice_and_the_table_counts_what_failed_in_them(rig: Callable[[Path], Rig], tmp_path: Path) -> None:
    gate = rig(tmp_path)
    flaky_test = "tests/test_clock.py::test_the_second_is_exact"
    always = "tests/test_never.py::test_broken"
    gate.rules((
        {"starved": True, "seed": None, "stdout": f"FAILED {flaky_test} - assert 1.2 < 1\nFAILED {always} - boom\n1 failed in 5.00s", "exit": 1},
        {"starved": True, "seed": 3, "stdout": f"FAILED {flaky_test} - assert 1.3 < 1\nFAILED {always} - boom\n1 failed in 5.00s", "exit": 1},
        {"stdout": f"FAILED {always} - boom\n1 failed in 5.00s", "exit": 1},
    ))
    done = gate.run("--runs", "8", "--parallel", "3")
    assert done.returncode == 1, done.stdout + done.stderr
    started = gate.started()
    assert len(started) == 8 and sum(1 for each in started if each["starved"]) == 4 and sorted(each["seed"] for each in started if each["seed"] is not None) == [1, 3, 5, 7]
    for each in started:
        options = f"PYTEST_ADDOPTS='-p tests.support.shuffle --shuffle-seed {each['seed']}' " if each["seed"] is not None else ""
        assert shlex.split(str(each["line"])) == ["bash", "-c", f"uv sync --frozen --extra app --extra ble && COLUMNS=200 {options}scripts/check --stage pytest"]
    assert gate.calls().count("run --rm") == 8 and gate.calls()[:2] == ["image inspect", "image inspect"], "the image is asked for once before the runs (and once by each of them)"
    lines = done.stdout.splitlines()
    assert sum(1 for line in lines if line.startswith("run ")) == 8
    rows = {cells[0]: cells for cells in ([cell.strip() for cell in line.split("|")] for line in lines if "|" in line)}
    assert rows[always][1:3] == ["8", "8"] and rows[flaky_test][1:3] == ["3", "8"] and rows[flaky_test][3] == "starved/file order 2, starved/shuffled 1"
    assert rows[flaky_test][4] in ("assert 1.2 < 1", "assert 1.3 < 1"), "the first line of the first run that failed"
    assert "0 of 8 runs green; 2 tests failed in at least one run" in done.stdout
    assert (gate.out / "report.txt").read_text().rstrip().endswith("2 tests failed in at least one run") and len(list(gate.out.glob("run-*.log"))) == 8


@linux_only
def test_all_green_is_exit_code_0(rig: Callable[[Path], Rig], tmp_path: Path) -> None:
    gate = rig(tmp_path)
    done = gate.run("--runs", "4", "--parallel", "2")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "no test failed in any run" in done.stdout and "4 of 4 runs green" in done.stdout


@linux_only
def test_a_run_that_is_not_over_in_time_is_ended_with_its_container_and_listed_with_its_stack(rig: Callable[[Path], Rig], tmp_path: Path) -> None:
    gate = rig(tmp_path)
    gate.rules(({"seed": 1, "stdout": "Timeout (0:02:00)!\nThread 0x1 (most recent call first):\n  File \"tests/test_x.py\", line 9 in test_waits", "hang": True},))
    done = gate.run("--runs", "2", "--parallel", "2", "--limit-minutes", "0.05")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "run  2  runner/shuffled" in done.stdout and "hung" in done.stdout
    assert "run 2 hung (runner/shuffled); the stack that faulthandler_timeout printed last:\n    Timeout (0:02:00)!" in done.stdout and "in test_waits" in done.stdout
    assert "rm --force" in gate.calls(), "the container of the run that hung is taken away"


@linux_only
def test_a_run_that_fails_before_the_tests_is_listed_with_the_end_of_its_log(rig: Callable[[Path], Rig], tmp_path: Path) -> None:
    gate = rig(tmp_path)
    gate.rules(({"seed": None, "starved": False, "stdout": "error: Failed to install: no network", "exit": 2},))
    done = gate.run("--runs", "1")
    assert done.returncode == 1 and "not run" in done.stdout and "run 1 did not get to the tests (exit 2); the end of its log:\n" in done.stdout and "    error: Failed to install: no network\n\n0 of 1 runs green" in done.stdout


@linux_only
def test_without_the_image_nothing_is_run_and_without_docker_the_script_says_so(rig: Callable[[Path], Rig], tmp_path: Path) -> None:
    gate = rig(tmp_path)
    (gate.state / "has-image").unlink()
    (gate.state / "build-fails").write_text("")
    done = gate.run("--runs", "2")
    assert done.returncode == 1 and "flaky: the image could not be made: nothing was run" in done.stderr and gate.started() == []
    empty = tmp_path / "no-tools"
    empty.mkdir()
    nothing = gate.run(env={**gate.env, "PATH": str(empty)})
    assert nothing.returncode == 2 and nothing.stderr == "flaky: docker is not installed\n"


def test_a_number_of_runs_that_is_not_a_count_is_refused_before_docker_is_asked(rig: Callable[[Path], Rig], tmp_path: Path) -> None:
    gate = rig(tmp_path)
    assert gate.run("--runs", "0").returncode == 2 and gate.run("--parallel", "0").returncode == 2 and gate.run("--limit-minutes", "0").returncode == 2
    assert gate.calls() == []


# ---- the order of the tests (tests/support/shuffle.py) ----

class Item:
    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid


NODES = [f"tests/test_{module}.py::test_{number}" for module in "abcde" for number in range(6)]


def test_the_same_seed_is_the_same_order_whatever_order_the_tests_came_in() -> None:
    items = [Item(node) for node in NODES]
    one = [item.nodeid for item in shuffled(items, 7)]
    assert [item.nodeid for item in shuffled(list(reversed(items)), 7)] == one, "every xdist worker collects by itself, and the workers must agree"
    assert sorted(one) == sorted(NODES) and one != NODES and [item.nodeid for item in shuffled(items, 8)] != one


def test_the_tests_of_a_module_stay_together_in_a_shuffled_order() -> None:
    order = [item.nodeid for item in shuffled([Item(node) for node in NODES], 3)]
    modules = [node.split("::")[0] for node in order]
    assert all(len(set(modules[index:index + 6])) == 1 for index in range(0, 30, 6)) and len({modules[index] for index in range(0, 30, 6)}) == 5
    assert any(order[index:index + 6] != sorted(order[index:index + 6]) for index in range(0, 30, 6)), "and the tests inside each module are mixed too"


MODULES = {"test_a.py": "def test_1():\n    pass\n\n\ndef test_2():\n    pass\n\n\ndef test_3():\n    pass\n", "test_b.py": "def test_1():\n    pass\n\n\ndef test_2():\n    pass\n"}


def collected(folder: Path, *options: str) -> list[str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    done = subprocess.run([sys.executable, "-m", "pytest", "-p", "tests.support.shuffle", "-p", "no:cacheprovider", "--rootdir", str(folder), "--collect-only", "-q", str(folder), *options], cwd=folder, env=env,
                          capture_output=True, text=True, timeout=PATIENCE_SEC, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    return [line for line in done.stdout.splitlines() if "::" in line]


def test_pytest_asked_for_a_seed_collects_in_its_order_and_without_one_in_the_order_of_the_files(tmp_path: Path) -> None:
    for name, text in MODULES.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    plain = collected(tmp_path)
    assert plain == ["test_a.py::test_1", "test_a.py::test_2", "test_a.py::test_3", "test_b.py::test_1", "test_b.py::test_2"]
    orders = {tuple(collected(tmp_path, "--shuffle-seed", str(seed))) for seed in range(8)}
    assert len(orders) > 1 and all(sorted(order) == sorted(plain) for order in orders)
    assert collected(tmp_path, "--shuffle-seed", "5") == collected(tmp_path, "--shuffle-seed", "5")
