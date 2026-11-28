"""The desktop app's watchdog of its own end (neoaprs/desktop/endafter.py): started when Quit is decided, it
ends the app from outside when the app cannot end itself. The real ones run with real child processes, on
Linux and on Windows alike, and each says on its stderr what came of it, which the tests read.
"""

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from neoaprs.desktop import endafter, webshell
from tests.support.proc import process_alive

ROOT = Path(__file__).resolve().parent.parent


def until(condition: object, seconds: float) -> bool:
    pause = threading.Event()
    for _ in range(int(seconds / 0.05)):
        if condition():  # type: ignore[operator]
            return True
        pause.wait(0.05)
    return False


def child(body: str) -> subprocess.Popen[str]:
    """A Python process of the test's own that plays the app as from a checkout, by the venv's python (on
    Windows a launcher with the interpreter as its child): `body` runs after the watchdog's module is imported."""
    script = (
        f"import sys, subprocess\nsys.path.insert(0, {str(ROOT)!r})\nfrom neoaprs.desktop import endafter\n{body}\n"
    )
    return subprocess.Popen(
        [sys.executable, "-c", script], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True, cwd=str(ROOT)
    )


def told_to(path: Path) -> str:
    """The popen of `watch` in a child: the watchdog as the app starts it, its stderr into `path`."""
    return f"lambda *a, **k: subprocess.Popen(*a, **{{**k, 'stderr': open({str(path)!r}, 'w')}})"


def said(path: Path) -> str:
    until(lambda: path.exists() and path.read_text(encoding="utf-8").strip() != "", 30.0)
    return path.read_text(encoding="utf-8").strip() if path.exists() else "(nothing)"


def test_the_command_line_is_the_frozen_programs_own_or_this_file_by_the_base_interpreter() -> None:
    assert endafter.argv_for(4321, 8.0, frozen=True, executable="C:/NeoAPRS/neoaprs-app.exe") == [
        "C:/NeoAPRS/neoaprs-app.exe",
        "--end-after",
        "4321",
        "8",
    ]
    assert endafter.argv_for(4321, 2.5, frozen=False, executable="python") == [
        "python",
        "-I",
        str(ROOT / "neoaprs" / "desktop" / "endafter.py"),
        "4321",
        "2.5",
    ]
    assert endafter.argv_for(4321, 2.5, frozen=False)[0] == getattr(sys, "_base_executable", sys.executable), (
        "the base interpreter, never a venv's launcher, whose child the watchdog would be"
    )
    entry = (ROOT / "packaging" / "windows" / "neoaprs_entry.py").read_text(encoding="utf-8")
    assert f'END_FLAG = "{endafter.FLAG}"' in entry and "endafter.main(argv[1:])" in entry


def test_a_bad_argument_and_a_process_that_is_not_its_parent_are_refused_with_a_line_that_says_why(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for argv in ([], ["x"], ["1"], ["none", "0"], ["12", "y"], ["0", "1"], ["12", "-1"], ["12", "1", "2"]):
        assert endafter.main(argv) == endafter.BAD_ARGUMENT, argv
    assert endafter.main([str(os.getpid()), "0"]) == endafter.NOT_PARENT, "this process is not its own parent"
    lines = capsys.readouterr().err.splitlines()
    assert lines[0] == "end-after : refused: the arguments are not PID SECONDS (exit 2)"
    assert lines[-1] == f"end-after {os.getpid()} 0: refused: that process is not this one's parent (exit 3)"


@pytest.mark.slow("starts the daemon, a script or pytest as a process of its own")
def test_an_app_stuck_for_good_is_ended_from_outside_within_the_bound(tmp_path: Path) -> None:
    """The app's own last resort is gone (here: never called) and its main thread holds the GIL in a loop:
    no thread of it can run, and the watchdog it started at Quit still ends it."""
    out = tmp_path / "watchdog.txt"
    stuck = child(
        f"endafter.watch(2.0, popen={told_to(out)})\n"
        "import os\nprint(os.getpid(), flush=True)\nsys.setswitchinterval(1000.0)\nwhile True:\n    pass"
    )
    app = 0
    code: int | None = None
    try:
        assert stuck.stdout is not None
        app = int(stuck.stdout.readline())
        code = stuck.wait(60)
    except subprocess.TimeoutExpired:
        pass
    finally:
        for pid in (app, stuck.pid):
            if pid and process_alive(pid):
                os.kill(pid, signal.SIGTERM)
        stuck.wait(30)
    text = said(out)
    assert text == f"end-after {app} 2: it did not end: ended it (exit 1)", f"the watchdog said: {text}"
    assert code == (endafter.END_CODE if sys.platform == "win32" else -getattr(signal, "SIGKILL", 9))


def test_the_watchdog_of_an_app_that_ends_by_itself_ends_quietly_at_once(tmp_path: Path) -> None:
    out = tmp_path / "watchdog.txt"
    app = child(f"print(endafter.watch(60.0, popen={told_to(out)}), flush=True)\nsys.exit(0)")
    assert app.stdout is not None and app.stdout.readline().strip() == "True"
    assert app.wait(30) == 0
    text = said(out)
    assert text.endswith(": it ended by itself (exit 0)"), f"the watchdog said: {text}"


def test_quit_starts_the_watchdog_once_whatever_way_quit_comes(no_watchdog_of_the_test_process: list[float]) -> None:
    frame = webshell.WebFrame(with_window=False)
    frame.quit()
    frame.quit()
    assert no_watchdog_of_the_test_process == [endafter.END_SEC]
    assert endafter.END_SEC > webshell.LEAVE_SEC + webshell.QUIT_GRACE_SEC, "after the app's own end, not before"
