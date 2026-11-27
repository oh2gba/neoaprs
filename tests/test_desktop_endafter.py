"""The desktop app's watchdog of its own end (neoaprs/desktop/endafter.py): started when Quit is decided, it
ends the app from outside when the app cannot end itself. The real ones run with real child processes, on
Linux and on Windows alike.
"""

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

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
    """A Python process of the test's own that plays the app: `body` runs after the watchdog's module is imported."""
    script = (
        f"import sys, subprocess\nsys.path.insert(0, {str(ROOT)!r})\nfrom neoaprs.desktop import endafter\n{body}\n"
    )
    return subprocess.Popen(
        [sys.executable, "-c", script], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True, cwd=str(ROOT)
    )


def test_the_command_line_is_the_frozen_programs_own_or_the_module_and_the_entry_routes_it() -> None:
    assert endafter.argv_for(4321, 8.0, frozen=True, executable="C:/NeoAPRS/neoaprs-app.exe") == [
        "C:/NeoAPRS/neoaprs-app.exe",
        "--end-after",
        "4321",
        "8",
    ]
    assert endafter.argv_for(4321, 2.5, frozen=False, executable="python") == [
        "python",
        "-m",
        "neoaprs.desktop.endafter",
        "4321",
        "2.5",
    ]
    entry = (ROOT / "packaging" / "windows" / "neoaprs_entry.py").read_text(encoding="utf-8")
    assert f'END_FLAG = "{endafter.FLAG}"' in entry and "endafter.main(argv[1:])" in entry


def test_a_bad_argument_and_a_process_that_is_not_its_parent_are_refused() -> None:
    for argv in ([], ["x"], ["1"], ["none", "0"], ["12", "y"], ["0", "1"], ["12", "-1"], ["12", "1", "2"]):
        assert endafter.main(argv) == endafter.BAD_ARGUMENT, argv
    assert endafter.main([str(os.getpid()), "0"]) == endafter.NOT_PARENT, "this process is not its own parent"


def test_an_app_stuck_for_good_is_ended_from_outside_within_the_bound() -> None:
    """The app's own last resort is gone (here: never called) and its main thread holds the GIL in a loop:
    no thread of it can run, and the watchdog it started at Quit still ends it."""
    stuck = child(
        "endafter.watch(2.0)\nprint('ready', flush=True)\nsys.setswitchinterval(1000.0)\nwhile True:\n    pass"
    )
    try:
        assert stuck.stdout is not None and stuck.stdout.readline().strip() == "ready"
        code = stuck.wait(60)
    finally:
        if stuck.poll() is None:
            stuck.kill()
            stuck.wait(30)
    assert code == (endafter.END_CODE if sys.platform == "win32" else -getattr(signal, "SIGKILL", 9))


def test_the_watchdog_of_an_app_that_ends_by_itself_ends_quietly_at_once() -> None:
    app = child(
        "endafter.watch(60.0, popen=lambda *a, **k: print(subprocess.Popen(*a, **k).pid, flush=True))\nsys.exit(0)"
    )
    assert app.stdout is not None
    watchdog = int(app.stdout.readline())
    assert app.wait(30) == 0
    assert until(lambda: not process_alive(watchdog), 30.0), "gone long before its 60 s"


def test_quit_starts_the_watchdog_once_whatever_way_quit_comes(no_watchdog_of_the_test_process: list[float]) -> None:
    frame = webshell.WebFrame(with_window=False)
    frame.quit()
    frame.quit()
    assert no_watchdog_of_the_test_process == [endafter.END_SEC]
    assert endafter.END_SEC > webshell.LEAVE_SEC + webshell.QUIT_GRACE_SEC, "after the app's own end, not before"
