"""The runner of scripts/check, the gate, without its stages: NEOAPRS_CHECK_STAGES gives the script a file of stand-ins, each of which writes down when it began and when it ended, so that what is tested is the
runner: the order of the result lines, which stages run at once and which alone, what a failing stage does to the others and to the exit code, --serial, --stage, --list, ui/node_modules installed once, and a
run that is interrupted. The stages whose command line is what keeps them apart when they run at once are tried as the script has them, against made-up programs that only write down how they were called: the
two mypy runs and their cache folders, the three pytest runs (which files, which of them without the cache plugin, how many workers), vitest's workers, the security checks, the page that fails when it has
nothing to build with, lock (the lock file is compared even under UV_FROZEN) and smoke (the wheel installed in a folder of the run, the smoke test told to open no device).
The script runs as a copy in a folder of its own, so nothing of this tree is checked, built or installed; in a tree the script refuses the variable, which the first tests hold."""
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.support.files import text_if_readable
from tests.support.ptyline import SIGHUP, SIGKILL, is_root, posix_only

pytestmark = posix_only      # (a bash script with bash stand-ins: a development check, not the product)

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check"


def listed(name: str) -> list[str]:
    """The names in one of the lists of the script (`STAGES=(lock ruff ...)`)."""
    found = re.search(rf"^{name}=\(([^)]*)\)", SCRIPT.read_text(encoding="utf-8"), re.M)
    assert found, f"scripts/check has no list {name}"
    return found.group(1).split()


STAGES, EXTRA = listed("STAGES"), listed("EXTRA_STAGES")
FIRST, LAST = listed("ALONE_FIRST"), listed("ALONE_LAST")
AT_ONCE = [name for name in STAGES if name not in FIRST + LAST]
UI = ["ui-types", "ui-lint", "ui-tests", "ui-build", "page", "dup", "dup-py"]    # the stages that run from ui/node_modules, in the order of the list

# What every file of stand-ins begins with. `wait_for LINE` waits until a stage has written that line (half a minute at most): a stage that waits for the start of another passes only when the two run at once.
HELPERS = """
wait_for() {
    local tries=0
    until grep -qx "$1" "$events" 2>/dev/null; do
        tries=$((tries + 1))
        [ "$tries" -lt 600 ] || { echo "never came: $1"; return 1; }
        sleep 0.05
    done
}
"""
STAND_IN = """
body_{fn}() {{ {body}
}}
stage_{fn}() {{
    echo "start {name}" >> "$events"
    body_{fn}
    local status=$?
    echo "end {name}" >> "$events"
    return $status
}}
"""


def as_the_script_has_it(name: str) -> str:
    """The stage `name` of scripts/check, word for word, to put in the place of its stand-in: its one line, or its lines down to the closing brace."""
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith(f"stage_{name.replace('-', '_')}() "))
    last = first if not lines[first].endswith("{") else lines.index("}", first)
    return "\n".join(lines[first:last + 1]) + "\n"


class Gate:
    """A copy of scripts/check in a folder of its own, with a stand-in for every stage: `bodies` says what the stand-in of a stage does between its start and its end (shell; nothing by default), `left_out` names
    the stages that get no stand-in, `real` the ones that run as the script has them (against made-up programs: `programs`), and `also` is shell that the file of stand-ins ends with, to replace another
    function of the script."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        (folder / "scripts").mkdir()
        shutil.copy2(SCRIPT, folder / "scripts" / "check")
        self.events_file = folder / "events"
        self.bin = folder / "bin"
        self.bodies: dict[str, str] = {}
        self.left_out: set[str] = set()
        self.real: set[str] = set()
        self.also = ""

    def programs(self, **texts: str) -> dict[str, str]:
        """Writes made-up programs (name and shell text) into the folder of the copy that is first on the PATH of its stages; the environment that tells them where to write down how they were called."""
        self.bin.mkdir(exist_ok=True)
        for name, text in texts.items():
            (self.bin / name).write_text(text, encoding="utf-8")
            (self.bin / name).chmod(0o755)
        return {"EVENTS": str(self.events_file)}

    def environment(self, **env: str) -> dict[str, str]:
        """Writes the file of stand-ins and forgets the events of the run before; the environment to run the copy with. uv's cache is a folder of the copy, so that the script makes none in the home of whoever
        runs the tests."""
        stand_ins = self.folder / "stand-ins.sh"
        stages = "".join(STAND_IN.format(fn=name.replace("-", "_"), name=name, body=self.bodies.get(name, ":")) for name in STAGES + EXTRA if name not in self.left_out | self.real)
        real = "".join(as_the_script_has_it(name) for name in sorted(self.real))
        # The PATH is set in the file and not in the environment: the script puts the node of ~/.nvm before whatever it was given, and the real npx of that folder must never be the one a stage finds.
        stand_ins.write_text(f'events="{self.events_file}"\nPATH="{self.bin}:$PATH"\n{HELPERS}{stages}{real}{self.also}\n', encoding="utf-8")
        self.events_file.unlink(missing_ok=True)
        # (a gate that runs this test serially says nothing about the copy; and no setting of uv that the caller has, such as UV_FROZEN, UV_PYTHON or UV_NO_CACHE of the CI's setup-uv: the stages are told what they get)
        outside = {k: v for k, v in os.environ.items() if k not in ("NEOAPRS_TEST_WORKERS", "NEOAPRS_TEST_WORKERS_MAX") and not k.startswith("UV_")}
        return {**outside, "NEOAPRS_CHECK_STAGES": str(stand_ins), "NEOAPRS_PYTHON": sys.executable, "UV_CACHE_DIR": str(self.folder / "uv-cache"), **env}

    def run(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["scripts/check", *args], cwd=self.folder, env=self.environment(**env), capture_output=True, text=True, timeout=120)

    def events(self) -> list[str]:
        return self.events_file.read_text(encoding="utf-8").splitlines() if self.events_file.exists() else []

    def calls(self) -> list[str]:
        """What the made-up python and npx were called with, in the order of the calls."""
        return [event for event in self.events() if event.startswith(("python ", "npx "))]


@pytest.fixture
def gate(tmp_path: Path) -> Gate:
    return Gate(tmp_path)


def results(done: subprocess.CompletedProcess[str]) -> list[tuple[str, str]]:
    """The result lines of a run, each as the word and the name; every one is held to the form `ok    name            0.1s`."""
    found = []
    for line in done.stdout.splitlines():
        if line.startswith(("ok ", "FAIL ")):
            word, name = line.split()[:2]
            assert line.startswith(f"{word:<5} {name:<12} ") and re.fullmatch(r"[ \d]{3}\d\.\ds", line[19:]), f"not the form of a result line: {line!r}"
            found.append((word, name))
    return found


def all_begin_before_one_ends(gate: Gate) -> None:
    """Every stage of the middle step waits for the start of all the others: they end only when they run at once. Each also holds the script to its word that `at_once` is 1 then (a stage reads it to take less
    of the machine)."""
    for name in AT_ONCE:
        gate.bodies[name] = '[ "$at_once" = 1 ] && ' + " && ".join(f'wait_for "start {other}"' for other in AT_ONCE)


def each_is_told_it_runs_alone(gate: Gate) -> None:
    """Every stage fails unless the script's `at_once` is 0: one stage at a time is what the script says it does, and what the stage is told."""
    for name in STAGES + EXTRA:
        gate.bodies[name] = '[ "$at_once" = 0 ]'


def test_the_lists_of_the_script_are_what_these_tests_think_they_are() -> None:
    assert STAGES[0] == "lock" and FIRST == ["lock"] and LAST == ["smoke"] == STAGES[-1:], "lock alone first, smoke alone last"
    assert {"ruff", "mypy", "architecture", "pytest", "page", "security", *UI} <= set(AT_ONCE) and EXTRA == ["sim", "audit", "flaky"]
    assert len(set(STAGES + EXTRA)) == len(STAGES + EXTRA) and all(len(name) <= 12 for name in STAGES + EXTRA), "a name is written once and fits the column of the result lines"


REFUSED = "check: NEOAPRS_CHECK_STAGES is set, which puts stand-ins in the place of every stage and is for the tests of this script only: unset it and run again"


@pytest.mark.parametrize("sign", ["pyproject.toml", "neoaprs"])
@pytest.mark.parametrize("args", [(), ("--serial",), ("--stage", "ruff"), ("--list",)])
def test_the_stand_ins_are_refused_where_there_is_something_to_check(gate: Gate, sign: str, args: tuple[str, ...]) -> None:
    """With stand-ins every stage is green and nothing is checked, so the script takes them only in a folder that is no tree. One of the two signs of a tree beside scripts/ is enough, whatever it is (a file, a
    folder, a link to nothing), and whatever the script was asked."""
    if sign == "neoaprs":
        (gate.folder / sign).symlink_to("nowhere")
    else:
        (gate.folder / sign).touch()
    done = gate.run(*args)
    assert done.returncode == 2 and done.stdout == "" and done.stderr.strip() == REFUSED
    assert gate.events() == [], "no stand-in ran"


@pytest.mark.parametrize("args", [(), ("--stage", "ruff")])
def test_the_script_of_this_tree_stops_when_the_variable_of_its_tests_is_set(gate: Gate, args: tuple[str, ...]) -> None:
    """The script as scripts/release runs it, the one of this tree and not a copy: a NEOAPRS_CHECK_STAGES left in the shell does not turn the gate green, it stops it (exit code 2, which the release takes as a
    gate that failed). Nothing runs here either way: without the refusal every stage would be a stand-in that only writes a line down."""
    done = subprocess.run([str(SCRIPT), *args], cwd=ROOT, env=gate.environment(), capture_output=True, text=True, timeout=120)
    assert done.returncode == 2 and done.stdout == "" and done.stderr.strip() == REFUSED
    assert gate.events() == []


def test_a_variable_that_is_set_to_nothing_is_no_variable(gate: Gate) -> None:
    (gate.folder / "pyproject.toml").touch()
    done = gate.run("--list", NEOAPRS_CHECK_STAGES="")
    assert done.returncode == 0 and done.stdout.split() == STAGES + EXTRA


def test_the_stages_run_at_once_between_lock_and_smoke_and_the_lines_come_in_the_order_of_the_list(gate: Gate) -> None:
    all_begin_before_one_ends(gate)
    gate.bodies[AT_ONCE[0]] += "".join(f' && wait_for "end {name}"' for name in AT_ONCE[1:])            # the first of the list is the last to end (it waits for each of the others, in whatever order they end): its line is still the first
    done = gate.run()
    assert done.returncode == 0, done.stdout + done.stderr
    assert results(done) == [("ok", name) for name in STAGES]
    assert re.fullmatch(r"all green in \d+s", done.stdout.splitlines()[-1])
    events = gate.events()
    assert events[:2] == ["start lock", "end lock"] and events[-2:] == ["start smoke", "end smoke"], "lock before the others begin, smoke after they have ended"
    middle = events[2:-2]
    assert sorted(middle[:len(AT_ONCE)]) == sorted(f"start {name}" for name in AT_ONCE), f"every stage of the middle step begins before one of them ends: {middle}"
    assert middle[-1] == f"end {AT_ONCE[0]}"
    assert not [event for event in events if event.split()[1] in EXTRA], "a stage that runs only by name is not in the default run"


def test_a_failing_stage_does_not_stop_the_others_and_its_output_is_under_its_line(gate: Gate) -> None:
    all_begin_before_one_ends(gate)
    gate.bodies["lock"] = 'echo "the lock is stale"; return 1'
    gate.bodies["mypy"] += ' && { echo "neoaprs/x.py:3: error: one"; echo "Found 1 error" >&2; return 1; }'
    gate.bodies["smoke"] = 'echo "smoke: FAILED: no page"; exit 7'
    done = gate.run()
    assert done.returncode == 1 and "all green" not in done.stdout
    failed = ["lock", "mypy", "smoke"]
    assert results(done) == [("FAIL" if name in failed else "ok", name) for name in STAGES]
    assert sorted(e for e in gate.events() if e.startswith("start ")) == sorted(f"start {name}" for name in STAGES), "every stage ran"
    lines = done.stdout.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("FAIL  mypy "))
    assert lines[at + 1:at + 4] == ["      | neoaprs/x.py:3: error: one", "      | Found 1 error", next(line for line in lines if line.startswith("ok    architecture "))], "what the stage wrote, on either stream, and then the next line"
    assert lines[1] == "      | the lock is stale" and lines[-2] == "      | smoke: FAILED: no page"
    assert re.fullmatch(r"failed in \d+s: lock mypy smoke", lines[-1])


def test_the_output_of_a_failing_stage_that_does_not_end_its_last_line_leaves_the_next_line_whole(gate: Gate) -> None:
    """A program that is killed in the middle of a line, or prints its error without a line end: the result line of the next stage, and the last line of the run, still begin a line."""
    gate.bodies["ruff"] = 'printf "E501 no line end"; return 1'
    gate.bodies["smoke"] = 'printf "one\\ntwo"; return 1'
    done = gate.run()
    assert done.returncode == 1 and results(done) == [("FAIL" if name in ("ruff", "smoke") else "ok", name) for name in STAGES]
    lines = done.stdout.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("FAIL  ruff "))
    assert lines[at + 1] == "      | E501 no line end" and lines[at + 2].startswith("ok    mypy ")
    assert lines[-3:-1] == ["      | one", "      | two"] and re.fullmatch(r"failed in \d+s: ruff smoke", lines[-1])


def test_a_stage_whose_shell_was_killed_has_failed_though_it_left_no_result_line(gate: Gate) -> None:
    """The shell that runs a stage and writes its result line is killed from outside (the machine out of memory): the stage has a line all the same, which says FAIL and has no time, with what it wrote until
    then under it, and the run goes on."""
    gate.bodies["ruff"] = 'echo "as far as it got"; stage=$BASHPID; kill -KILL $(ps -o ppid= -p "$stage"); exit 0'              # (the parent of the stage's own shell is the one that writes the line)
    done = gate.run()
    lines = done.stdout.splitlines()
    assert done.returncode == 1 and lines[1:3] == ["FAIL  ruff        ", "      | as far as it got"] and lines[3].startswith("ok    mypy "), done.stdout + done.stderr
    assert re.fullmatch(r"failed in \d+s: ruff", lines[-1])


def test_serial_runs_one_stage_after_the_other_in_the_order_of_the_list(gate: Gate) -> None:
    each_is_told_it_runs_alone(gate)
    done = gate.run("--serial")
    assert done.returncode == 0 and results(done) == [("ok", name) for name in STAGES] and re.fullmatch(r"all green in \d+s", done.stdout.splitlines()[-1])
    assert gate.events() == [f"{what} {name}" for name in STAGES for what in ("start", "end")], "each has ended before the next begins"


@pytest.mark.parametrize("how", ["--serial", "NEOAPRS_TEST_WORKERS=0"])
def test_serial_stops_at_the_first_failure(gate: Gate, how: str) -> None:
    gate.bodies["mypy"] = 'echo "neoaprs/x.py:3: error: one"; return 1'
    done = gate.run("--serial") if how == "--serial" else gate.run(NEOAPRS_TEST_WORKERS="0")
    assert done.returncode == 1
    assert results(done) == [("ok", "lock"), ("ok", "ruff"), ("FAIL", "mypy")]
    assert done.stdout.splitlines()[-1] == "      | neoaprs/x.py:3: error: one", "the output of the stage that failed is the end of it"
    assert gate.events() == ["start lock", "end lock", "start ruff", "end ruff", "start mypy", "end mypy"], "nothing after it was started"


@pytest.mark.parametrize("name", ["ui-lint", "smoke", "sim", "audit", "flaky"])
def test_stage_runs_the_one_stage_that_is_named(gate: Gate, name: str) -> None:
    each_is_told_it_runs_alone(gate)
    done = gate.run("--stage", name)
    assert done.returncode == 0 and results(done) == [("ok", name)] and re.fullmatch(r"all green in \d+s", done.stdout.splitlines()[-1])
    assert gate.events() == [f"start {name}", f"end {name}"]


def test_a_named_stage_that_fails_is_exit_code_1_with_its_output(gate: Gate) -> None:
    gate.bodies["ruff"] = 'echo "E501 line too long"; return 1'
    done = gate.run("--stage", "ruff")
    assert done.returncode == 1 and results(done) == [("FAIL", "ruff")]
    assert done.stdout.splitlines()[1:] == ["      | E501 line too long"]


def test_a_named_stage_shows_its_output_as_it_is_written_and_a_green_one_too(gate: Gate) -> None:
    """The steps of the CI are named stages: one that hangs must show where, and one that is green shows its output (stderr: stdout is the result lines)."""
    gate.bodies["mypy"] = 'echo "checking 2"'
    done = gate.run("--stage", "mypy")
    assert done.returncode == 0 and results(done) == [("ok", "mypy")] and "checking 2" in done.stderr and "checking 2" not in done.stdout
    every = gate.run()
    assert every.returncode == 0 and "checking 2" not in every.stderr, "a run of every stage keeps each one's output until it has failed"


def test_list_prints_the_names_and_runs_nothing(gate: Gate) -> None:
    done = gate.run("--list")
    assert done.returncode == 0 and done.stdout.split() == STAGES + EXTRA
    assert gate.events() == []


@pytest.mark.parametrize("args", [("--stage", "nope"), ("--stage",), ("--everything",)])
def test_a_stage_that_does_not_exist_and_an_argument_nobody_knows_are_refused_before_anything_runs(gate: Gate, args: tuple[str, ...]) -> None:
    done = gate.run(*args)
    assert done.returncode == 2 and done.stdout == ""
    assert done.stderr.startswith("check: ") and gate.events() == []
    if args == ("--stage", "nope"):
        assert done.stderr.strip() == f"check: no stage called nope ({' '.join(STAGES + EXTRA)})"


def test_a_stage_without_a_stand_in_fails_and_the_real_one_does_not_run(gate: Gate) -> None:
    gate.left_out = {"ruff"}
    done = gate.run("--stage", "ruff")
    assert done.returncode == 1 and results(done) == [("FAIL", "ruff")]
    assert "stage_ruff: command not found" in done.stdout


# ---- an interrupted run ----

@pytest.mark.parametrize(("sent", "code"), [(signal.SIGTERM, 143), (signal.SIGINT, 130), (SIGHUP, 129)])
def test_an_interrupted_run_ends_what_its_stages_started_and_takes_its_folder_away(gate: Gate, sent: signal.Signals, code: int) -> None:
    """The signal reaches the script alone, as `kill` sends it, while the stages run at once: the stage that is still busy and the program it started (a daemon of the suite, in the real one) are ended, the stage
    does not go on, the temporary folder of the run is gone, and the exit code names the signal."""
    pids, temp = gate.folder / "pids", gate.folder / "tmp"
    temp.mkdir()
    gate.bodies["pytest"] = f'sleep 300 & echo "$BASHPID $!" > "{pids}"; wait'
    run = subprocess.Popen(["scripts/check"], cwd=gate.folder, env=gate.environment(TMPDIR=str(temp)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    started: list[int] = []
    try:
        until(lambda: len((text_if_readable(pids) or "").split()) == 2, "the stage pytest never started")
        started = [int(pid) for pid in pids.read_text().split()]
        assert list(temp.iterdir()), "the run has its folder in TMPDIR"
        run.send_signal(sent)
        output, _ = run.communicate(timeout=30)
        assert run.returncode == code, output
        until(lambda: not any(alive(pid) for pid in started), "the stage or what it started is still running")
    finally:
        run.kill()
        for pid in started:                # (a script that failed this test leaves nothing behind either)
            if alive(pid):
                os.kill(pid, SIGKILL)
    assert "start pytest" in gate.events() and "end pytest" not in gate.events() and "start smoke" not in gate.events()
    assert list(temp.iterdir()) == [] and "all green" not in output


def test_the_runner_has_no_command_substitution_for_a_signal_to_come_in_the_middle_of() -> None:
    """When a signal comes while bash 5.2 reads a `$(...)`, it cannot read the command of the signal's trap: the run ends with exit code 2 and a syntax error, about one interrupted run in fifty when the result
    lines were read with `$(cat ...)`. The test above meets that moment too seldom to hold it, so the text of the runner is held: what runs between the stages reads files with `read` and the clock from a
    variable. (The stages themselves run in shells of their own, which the traps do not reach.)"""
    runner = SCRIPT.read_text(encoding="utf-8").split("\n# --- the runner ---", 1)[1]
    found = [line for line in runner.splitlines() if not line.lstrip().startswith("#") and re.search(r"\$\((?!\()", line)]
    assert not found, f"a command substitution in the runner of scripts/check: {found}"


def until(true: Callable[[], bool], otherwise: str) -> None:
    """Waits until `true` is (half a minute at most)."""
    deadline = time.monotonic() + 30
    while not true():
        assert time.monotonic() < deadline, otherwise
        time.sleep(0.05)


def alive(pid: int) -> bool:
    """Whether the process still runs (one that has ended and waits for its parent to ask is not running)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = text_if_readable(Path(f"/proc/{pid}/stat"))                       # (None: it went between the two lookups)
    return stat is None or stat.rsplit(")", 1)[-1].split()[0] != "Z"


# ---- what keeps the stages apart when they run at once: their own command lines, against a python and an npx that only write down how they were called ----

# The made-up python (NEOAPRS_PYTHON) and npx: each writes its arguments down; the python fails when they are exactly FAIL_ON.
FAKE_PYTHON = """#!/bin/sh
echo "python $*" >> "$EVENTS"
[ "$*" != "${FAIL_ON-}" ] || { echo "boom"; exit 1; }
"""
FAKE_NPX = """#!/bin/sh
echo "npx $*" >> "$EVENTS"
"""
NODE = "\nnode_ok() { return 0; }\n"                                           # (the copy needs no node: nothing of the page runs)
MYPY, MYPY_WINDOWS = "python -m mypy", "python -m mypy --platform win32 --cache-dir .mypy_cache/win32"
THE_REST = "--ignore=tests/test_architecture.py --ignore=tests/test_size_ratchet.py --ignore=tests/test_page_build.py"
ARCHITECTURE = "python -m pytest -q -p no:cacheprovider tests/test_architecture.py tests/test_size_ratchet.py"
SUITE = f"python -m pytest -q -n auto --dist loadgroup --maxprocesses=12 {THE_REST}"
PAGE = "python -m pytest -q -p no:cacheprovider tests/test_page_build.py"
SECURITY = "python scripts/security-check"


def with_made_up_programs(gate: Gate, *stages: str, cores: int = 32) -> dict[str, str]:
    """The named stages as the script has them, in a copy that has ui/node_modules and a machine of `cores` threads; the environment to run the gate with."""
    gate.real = set(stages)
    gate.also += f"{NODE}cores() {{ echo {cores}; }}\n"
    (gate.folder / "ui" / "node_modules").mkdir(parents=True, exist_ok=True)
    env = gate.programs(python=FAKE_PYTHON, npx=FAKE_NPX)
    return {**env, "NEOAPRS_PYTHON": str(gate.bin / "python")}


def test_the_command_lines_of_the_stages_that_run_at_once_keep_them_apart(gate: Gate) -> None:
    """What the top of the script promises for the default run, held to the letter: the mypy run for Windows has a cache folder of its own; the suite leaves out the files of the stages architecture and page (so
    vite builds once for the page test and not in the suite too) and has 12 workers at most; architecture and page run without pytest's cache plugin, so .pytest_cache is the suite's alone; vitest has 8 workers
    at most; and the security stage is the checks that ask nobody."""
    env = with_made_up_programs(gate, "mypy", "architecture", "pytest", "ui-tests", "page", "security")
    done = gate.run(**env)
    assert done.returncode == 0 and results(done) == [("ok", name) for name in STAGES], done.stdout + done.stderr
    assert sorted(gate.calls()) == sorted([MYPY, MYPY_WINDOWS, ARCHITECTURE, SUITE, PAGE, SECURITY, "npx vitest run --maxWorkers 8"])
    assert [call for call in gate.calls() if "no:cacheprovider" not in call and "pytest" in call] == [SUITE], "one pytest run with the cache plugin"


@pytest.mark.parametrize(("cores", "workers"), [(32, 8), (9, 8), (8, 8), (4, 4), (1, 1)])
def test_beside_the_other_stages_vitest_has_eight_workers_at_most_and_no_more_than_the_machine_has_threads(gate: Gate, cores: int, workers: int) -> None:
    done = gate.run(**with_made_up_programs(gate, "ui-tests", cores=cores))
    assert done.returncode == 0 and gate.calls() == [f"npx vitest run --maxWorkers {workers}"], done.stdout + done.stderr


@pytest.mark.parametrize(("args", "env", "calls"), [
    (("--stage", "mypy"), {}, [MYPY, MYPY_WINDOWS]),
    (("--stage", "architecture"), {}, [ARCHITECTURE]),
    (("--stage", "pytest"), {}, [SUITE]),
    (("--stage", "pytest"), {"NEOAPRS_TEST_WORKERS_MAX": "5"}, [f"python -m pytest -q -n auto --dist loadgroup --maxprocesses=5 {THE_REST}"]),
    (("--stage", "pytest"), {"NEOAPRS_TEST_WORKERS": "3"}, [f"python -m pytest -q -n 3 --dist loadgroup {THE_REST}"]),
    (("--stage", "pytest"), {"NEOAPRS_TEST_WORKERS": "3", "NEOAPRS_TEST_WORKERS_MAX": "2"}, [f"python -m pytest -q -n 3 --dist loadgroup {THE_REST}"]),
    (("--stage", "pytest"), {"NEOAPRS_TEST_WORKERS": "0"}, [f"python -m pytest -q {THE_REST}"]),
    (("--stage", "ui-tests"), {}, ["npx vitest run"]),
    (("--stage", "page"), {}, [PAGE]),
    (("--stage", "security"), {}, [SECURITY]),
    (("--stage", "audit"), {}, [f"{SECURITY} --audit"]),
    (("--stage", "flaky"), {}, ["python scripts/flaky"]),
    (("--serial",), {}, [MYPY, MYPY_WINDOWS, ARCHITECTURE, SUITE, "npx vitest run", PAGE, SECURITY]),
])
def test_the_command_line_of_a_stage_that_runs_alone(gate: Gate, args: tuple[str, ...], env: dict[str, str], calls: list[str]) -> None:
    """One stage at a time: the same files and cache folders, the workers as the variables say (a number that is named has no ceiling, 0 is no workers at all), and vitest takes what it likes."""
    done = gate.run(*args, **with_made_up_programs(gate, "mypy", "architecture", "pytest", "ui-tests", "page", "security", "audit", "flaky"), **env)
    assert done.returncode == 0 and gate.calls() == calls, done.stdout + done.stderr


@pytest.mark.parametrize("fails", [MYPY, MYPY_WINDOWS])
def test_the_two_mypy_runs_both_run_beside_the_other_stages_and_either_fails_the_stage(gate: Gate, fails: str) -> None:
    """At once the two start together, so the one for Linux failing does not keep the one for Windows from running; what the second wrote comes after the first's, under its heading."""
    done = gate.run(**with_made_up_programs(gate, "mypy"), FAIL_ON=fails.removeprefix("python "))
    assert done.returncode == 1 and results(done) == [("FAIL" if name == "mypy" else "ok", name) for name in STAGES]
    assert sorted(gate.calls()) == sorted([MYPY, MYPY_WINDOWS])
    lines = done.stdout.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("FAIL  mypy "))
    under = ["boom", "mypy --platform win32:"] if fails == MYPY else ["mypy --platform win32:", "boom"]
    assert lines[at + 1:at + 4] == [*(f"      | {line}" for line in under), next(line for line in lines if line.startswith("ok    architecture "))]


@pytest.mark.parametrize(("fails", "calls"), [(MYPY, [MYPY]), (MYPY_WINDOWS, [MYPY, MYPY_WINDOWS])])
def test_alone_the_mypy_run_for_windows_follows_the_one_for_linux_when_that_passed(gate: Gate, fails: str, calls: list[str]) -> None:
    done = gate.run("--stage", "mypy", **with_made_up_programs(gate, "mypy"), FAIL_ON=fails.removeprefix("python "))
    assert done.returncode == 1 and results(done) == [("FAIL", "mypy")] and gate.calls() == calls


# ---- the two stages that go through uv, as the script has them, against a uv that only writes down how it was called ----

# The made-up uv: `build` leaves a wheel in the folder it is given, `venv` a folder whose python writes down its arguments and what it was told about devices, the update check and the caller's Python.
# With NO_CACHE=1 it fails whatever it is asked with --offline, as the real one does when its cache does not have everything.
FAKE_UV = r"""#!/bin/sh
echo "uv $* frozen=${UV_FROZEN-unset}" >> "$EVENTS"
case " $* " in *" --offline "*) [ -z "${NO_CACHE-}" ] || { echo "error: not in the cache" >&2; exit 2; } ;; esac
what="$1"
for last; do :; done
while [ $# -gt 0 ]; do [ "$1" = --out-dir ] && out="$2"; shift; done
case "$what" in
    build) mkdir -p "$out" && : > "$out/neoaprs-0-py3-none-any.whl" ;;
    venv)
        mkdir -p "$last/bin"
        printf '%s\n' '#!/bin/sh' 'echo "python $* devices=${NEOAPRS_NO_DEVICES-unset} update=${NEOAPRS_UPDATE_CHECK-unset} caller=${PYTHONPATH-unset},${VIRTUAL_ENV-unset}" >> "$EVENTS"' > "$last/bin/python"
        chmod +x "$last/bin/python" ;;
esac
"""


def with_fake_uv(gate: Gate, stage: str) -> dict[str, str]:
    """Puts the made-up uv first on the PATH of the run and the real stage in place of its stand-in; the environment to run the gate with."""
    gate.real = {stage}
    return gate.programs(uv=FAKE_UV)


def test_the_lock_stage_asks_uv_to_compare_the_lock_file_even_where_the_caller_froze_it(gate: Gate) -> None:
    """Under UV_FROZEN=1, which the CI and the container set, `uv lock --check` only reads the lock file and passes one that is out of date: the stage takes the variable away."""
    done = gate.run("--stage", "lock", UV_FROZEN="1", **with_fake_uv(gate, "lock"))
    assert done.returncode == 0 and results(done) == [("ok", "lock")], done.stdout + done.stderr
    assert gate.events() == ["uv lock --check frozen=unset"]


@pytest.mark.skipif(is_root(), reason="root writes to a folder whatever its rights are")
def test_uv_gets_a_cache_of_its_own_where_the_one_it_was_given_cannot_be_written(gate: Gate, tmp_path: Path) -> None:
    """A sandbox that keeps uv from ~/.cache/uv would make the stages lock and smoke say something about the cache and not about the tree."""
    shut = tmp_path / "shut"
    shut.mkdir()
    shut.chmod(0o500)
    try:
        env = gate.programs(uv='#!/bin/sh\necho "uv cache=$UV_CACHE_DIR" >> "$EVENTS"\n')
        gate.real = {"lock"}
        done = gate.run("--stage", "lock", UV_CACHE_DIR=str(shut / "cache"), TMPDIR=str(tmp_path), **env)
    finally:
        shut.chmod(0o700)
    assert done.returncode == 0 and results(done) == [("ok", "lock")], done.stdout + done.stderr
    assert gate.events() == [f"uv cache={tmp_path}/uv-cache"], "the folder it was given is not the one it was told to use"


@pytest.mark.parametrize("cache", ["has everything", "is empty"])
def test_the_smoke_stage_installs_the_built_wheel_into_a_folder_of_its_own_and_runs_the_smoke_test_with_every_door_shut(gate: Gate, cache: str) -> None:
    """The wheel is built and installed in the run's temporary folder, from uv's cache first and from the net only when the cache does not have everything; the smoke test runs with the Python of that folder
    against the command of that folder, is told to open no device and not to ask the version page, and gets nothing of the caller's Python. The folder is gone when the run ends."""
    env = with_fake_uv(gate, "smoke")
    caller = {"PYTHONPATH": "/somewhere/else", "VIRTUAL_ENV": "/a/venv", "NEOAPRS_NO_DEVICES": "0", "NEOAPRS_UPDATE_CHECK": "1"}         # what the stage must not leave as it finds it (nothing real is started here)
    done = gate.run("--stage", "smoke", **caller, **({"NO_CACHE": "1"} if cache == "is empty" else {}), **env)
    assert done.returncode == 0 and results(done) == [("ok", "smoke")], done.stdout + done.stderr
    found = re.search(r"--out-dir (.+)/smoke/dist", gate.events()[0])            # (the temporary folder of the machine may have a space in its name)
    assert found, gate.events()
    work = found.group(1)
    events = [event.replace(work, "WORK").replace(sys.executable, "PYTHON").removesuffix(" frozen=unset") for event in gate.events()]
    build, install = "uv build --wheel --out-dir WORK/smoke/dist", "uv pip install --python WORK/smoke/venv/bin/python WORK/smoke/dist/neoaprs-0-py3-none-any.whl"
    again = cache == "is empty"
    assert events == [f"{build} --offline", *([build] if again else []), "uv venv --python PYTHON WORK/smoke/venv", f"{install} --offline", *([install] if again else []),
                      "python scripts/smoke.py --command WORK/smoke/venv/bin/neoaprs devices=1 update=0 caller=unset,unset"]
    assert Path(work).name.startswith("tmp") and not Path(work).exists(), "what the stage built is taken away with the logs"


# ---- ui/node_modules is installed once, before the stages that run from it start ----

NODE_IS_THERE = '\nnode_ok() { return 0; }\nui_install() { echo "install" >> "$events"; mkdir ui/node_modules; }\n'
NO_NETWORK = '\nnode_ok() { return 0; }\nui_install() { echo "install" >> "$events"; echo "npm error network"; return 1; }\n'


def page_without_modules(gate: Gate) -> None:
    """A tree with ui/ and no ui/node_modules; the stand-ins of the page's stages go through the script's own `ui_run`, which installs what is missing."""
    (gate.folder / "ui").mkdir()
    for name in UI:
        gate.bodies[name] = "ui_run true"


def the_real_page_stage_without_modules(gate: Gate, also: str) -> dict[str, str]:
    """The same tree with the stage page as the script has it, against the made-up python; the environment to run the gate with."""
    page_without_modules(gate)
    gate.real, gate.also = {"page"}, also
    return {**gate.programs(python=FAKE_PYTHON), "NEOAPRS_PYTHON": str(gate.bin / "python")}


def test_missing_node_modules_are_installed_once_before_the_stages_start(gate: Gate) -> None:
    page_without_modules(gate)
    gate.also = NODE_IS_THERE
    done = gate.run()
    assert done.returncode == 0, done.stdout + done.stderr
    assert results(done) == [("ok", "lock"), ("ok", "npm-ci"), *[("ok", name) for name in STAGES[1:]]], "the install has a line of its own, after lock"
    assert gate.events()[:3] == ["start lock", "end lock", "install"] and gate.events().count("install") == 1

    again = gate.run()
    assert again.returncode == 0 and results(again) == [("ok", name) for name in STAGES] and "install" not in gate.events(), "nothing to install, no line"


def test_an_install_that_fails_is_tried_once_and_fails_the_stages_of_the_page_only(gate: Gate) -> None:
    page_without_modules(gate)
    gate.also = NO_NETWORK
    done = gate.run()
    assert done.returncode == 1 and gate.events().count("install") == 1
    assert results(done) == [("ok", "lock"), ("FAIL", "npm-ci"), *[("FAIL" if name in UI else "ok", name) for name in STAGES[1:]]]
    lines = done.stdout.splitlines()
    assert lines[2] == "      | npm error network"
    assert lines.count("      | ui/node_modules is not installed: npm ci failed (the line npm-ci)") == len(UI)
    assert re.fullmatch(rf"failed in \d+s: npm-ci {' '.join(UI)}", lines[-1])


def test_the_page_stage_fails_when_the_install_failed_and_does_not_run_a_test_that_would_be_skipped(gate: Gate) -> None:
    """The page test skips its build where ui/node_modules is missing; a stage that ran it then would say ok with nothing compared."""
    done = gate.run(**the_real_page_stage_without_modules(gate, NO_NETWORK))
    assert done.returncode == 1 and ("FAIL", "page") in results(done) and gate.calls() == []
    lines = done.stdout.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("FAIL  page "))
    assert lines[at + 1] == "      | ui/node_modules is not installed: npm ci failed (the line npm-ci)" and lines[at + 2].startswith("FAIL  dup ")


@pytest.mark.parametrize(("also", "word", "events"), [
    (NODE_IS_THERE, "ok", ["install", PAGE]),                                                     # by name the stage installs what is missing, as the page's other stages do, and then compares
    (NO_NETWORK, "FAIL", ["install"]),
    ("\nnode_ok() { return 1; }\n", "FAIL", []),                                                 # without node the test would skip its build too
])
def test_the_page_stage_by_name_installs_what_is_missing_first_and_fails_when_it_cannot(gate: Gate, also: str, word: str, events: list[str]) -> None:
    done = gate.run("--stage", "page", **the_real_page_stage_without_modules(gate, also))
    assert results(done) == [(word, "page")] and done.returncode == (0 if word == "ok" else 1), done.stdout + done.stderr
    assert gate.events() == events
    if not events:
        assert done.stdout.splitlines()[1] == "      | node 22.12 or newer is needed (on the PATH or in ~/.nvm)"


def test_serial_leaves_the_install_to_the_first_stage_that_needs_it(gate: Gate) -> None:
    page_without_modules(gate)
    gate.also = NODE_IS_THERE
    done = gate.run("--serial")
    assert done.returncode == 0 and results(done) == [("ok", name) for name in STAGES]
    events = gate.events()
    assert events.count("install") == 1 and events[events.index("install") - 1] == f"start {UI[0]}"
