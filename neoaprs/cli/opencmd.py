"""`neoaprs open [--data DIR] [--no-browser] [--timeout SEC]`: open the page in the default browser.

The daemon is started first, detached, if none holds the data folder. The command waits for the
page to answer before it opens anything. This is what the Start menu's "NeoAPRS" runs.

Exit code 0: the page is up (and was opened); 1: it did not come up, with the reason. The address
is printed on stdout."""

import argparse
import os
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path

from neoaprs import selfreplace, stopfile
from neoaprs.paths import default_data_dir

from . import servicecmd, servicewindows
from .daemonstate import is_running, page_answers, page_url
from .logfile import LAUNCH_NAME, LOG_NAME
from .output import say

POLL_SEC = 0.05


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="neoaprs open", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--data", default=str(default_data_dir()), help="the data folder of the daemon; default %(default)s")
    p.add_argument(
        "--no-browser", action="store_true", help="start the daemon and print the page's address, but open no browser"
    )
    p.add_argument(
        "--timeout", type=float, default=60.0, metavar="SEC", help="how long to wait for the page; default %(default)s"
    )
    return p


def daemon_argv(data: Path, encryption: bool = False) -> list[str]:
    """Return the command that runs the daemon on `data`, with `--encryption` if asked.

    In an AppImage it is the AppImage file: the daemon outlives the image's mount."""
    gui, pythonw = servicecmd.windowless_programs()
    plan = servicecmd.Plan(os.path.abspath(sys.executable), data, None, False, gui, pythonw, servicecmd.appimage_file())
    extra = ["--encryption"] if encryption else []
    if sys.platform == "win32":
        return [*servicewindows.launch_argv(plan), *extra]
    elif plan.appimage:
        return [plan.appimage, "run", "--data", str(data), *extra]
    else:
        frozen = getattr(sys, "frozen", False)
        return (
            [plan.python, "run", "--data", str(data), *extra]
            if frozen
            else [plan.python, "-m", "neoaprs", "run", "--data", str(data), *extra]
        )


def spawn(argv: list[str], data: Path) -> "subprocess.Popen[bytes]":
    """Start the daemon detached; off Windows its output goes to a fresh `launch.log` in `data`."""
    data.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        return subprocess.Popen(
            argv,
            creationflags=servicewindows.DETACHED,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        env = dict(os.environ)
        # An AppImage running unpacked must start the daemon unpacked: without FUSE it cannot mount.
        selfreplace.keep_extract_and_run(env)
        # The unpacked daemon shares this process's folder, which this runtime removes on exit.
        selfreplace.leave_the_folder(env, argv[0])
        with (data / LAUNCH_NAME).open("wb") as log:
            return subprocess.Popen(
                argv, start_new_session=True, close_fds=True, stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env
            )


def wait_for_page(
    data: Path,
    child: "subprocess.Popen[bytes] | None",
    seconds: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    *,
    told: Callable[[], None] | None = None,
) -> str | None:
    """Return the page's address once a daemon holds the folder and its page answers, else None.

    The page is asked before the lock: checking the lock must not collide with the starting daemon.
    """
    deadline = clock() + seconds
    while clock() < deadline:
        if stopfile.migrating(data):
            deadline = clock() + seconds
            if told is not None:
                told()
                told = None
        url = page_url(data)
        if url is not None and page_answers(url) and is_running(data):
            return url
        if child is not None and child.poll() is not None and not is_running(data):
            return None
        sleep(POLL_SEC)
    return None


def tell_the_user(text: str) -> None:
    """Say the text, and on Windows also in a message box when there is no console."""
    say(text)
    if sys.platform == "win32":
        import ctypes

        if ctypes.windll.kernel32.GetConsoleWindow() == 0:
            ctypes.windll.user32.MessageBoxW(None, text, "NeoAPRS", 0x10)


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    data = Path(args.data).expanduser().resolve()
    child = None
    if not is_running(data):
        try:
            child = spawn(daemon_argv(data), data)
        except OSError as e:
            tell_the_user(f"open: the daemon could not be started on {data}: {e.strerror or e}")
            return 1
    url = wait_for_page(
        data,
        child,
        args.timeout,
        told=lambda: say("open: NeoAPRS is bringing its database up to date; the page opens when that is done"),
    )
    if url is None:
        before = "" if sys.platform == "win32" else f" (what it said before it had a log is in {data / LAUNCH_NAME})"
        why = (
            f"the daemon ended with exit code {child.returncode}{before}"
            if child is not None and child.poll() is not None
            else f"no page within {args.timeout:g} s (is the port taken? see the log)"
        )
        tell_the_user(f"open: NeoAPRS did not come up: {why}. The log is {data / LOG_NAME}")
        return 1
    print(url, flush=True)
    if not args.no_browser and not webbrowser.open(url):
        say(f"open: no browser could be started; open {url} yourself")
    return 0
