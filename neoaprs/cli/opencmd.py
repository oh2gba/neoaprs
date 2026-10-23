"""`neoaprs open [--data DIR] [--no-browser] [--timeout SEC]`: opens NeoAPRS's page in the default browser, starting the daemon first when none holds the data folder (the instance lock). The new daemon is
detached from this command and from its terminal: on Windows it is `neoaprsw.exe run` with no console window, elsewhere a child in a session of its own whose output goes to the log, `neoaprs.log`. The page's
port is the one the daemon logs (7303, or the next free one), so the command waits for the log line and for the page to answer before it opens anything. This is what the Start menu's "NeoAPRS" runs.
Exit code 0: the page is up (and was opened); 1: it did not come up, with the reason. The address is printed on stdout."""
import argparse
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from neoaprs.paths import default_data_dir

from . import servicecmd, servicewindows
from .daemonstate import LOG_NAME, is_running, page_answers, page_url
from .output import say

POLL_SEC = 0.25


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neoaprs open", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default=str(default_data_dir()), help="the data folder of the daemon; default %(default)s")
    p.add_argument("--no-browser", action="store_true", help="start the daemon and print the page's address, but open no browser")
    p.add_argument("--timeout", type=float, default=60.0, metavar="SEC", help="how long to wait for the page; default %(default)s")
    return p


def daemon_argv(data: Path) -> list[str]:
    """The command that runs the daemon on `data`: the windowless program on Windows, the AppImage file in an AppImage (the daemon outlives this process, and the folder the AppImage is mounted at does not),
    else this interpreter (or, in a frozen program, itself)."""
    gui, pythonw = servicecmd.windowless_programs()
    plan = servicecmd.Plan(os.path.abspath(sys.executable), data, None, False, gui, pythonw, servicecmd.appimage_file())
    if sys.platform == "win32":
        return servicewindows.launch_argv(plan)
    elif plan.appimage:
        return [plan.appimage, "run", "--data", str(data)]
    else:
        frozen = getattr(sys, "frozen", False)
        return [plan.python, "run", "--data", str(data)] if frozen else [plan.python, "-m", "neoaprs", "run", "--data", str(data)]


def spawn(argv: list[str], data: Path) -> "subprocess.Popen[bytes]":
    """Starts the daemon detached from this process; its stdout and stderr go to the log (nowhere on Windows, where the daemon has no console and logs to the file itself)."""
    data.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        return subprocess.Popen(argv, creationflags=servicewindows.DETACHED, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        with (data / LOG_NAME).open("ab") as log:
            return subprocess.Popen(argv, start_new_session=True, close_fds=True, stdin=subprocess.DEVNULL, stdout=log, stderr=log)


def wait_for_page(data: Path, child: "subprocess.Popen[bytes] | None", seconds: float) -> str | None:
    """The page's address once a daemon holds the folder and its page answers; None when `seconds` pass, or the daemon we started ended and none holds the folder."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if is_running(data):
            url = page_url(data)
            if url is not None and page_answers(url):
                return url
        elif child is not None and child.poll() is not None:
            return None
        time.sleep(POLL_SEC)
    return None


def tell_the_user(text: str) -> None:
    """A program without a console (neoaprsw.exe from the Start menu) has nowhere to say why nothing happened: a message box does."""
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
        child = spawn(daemon_argv(data), data)
    url = wait_for_page(data, child, args.timeout)
    if url is None:
        why = f"the daemon ended with exit code {child.returncode}" if child is not None and child.poll() is not None else f"no page within {args.timeout:g} s (is the port taken? see the log)"
        tell_the_user(f"open: NeoAPRS did not come up: {why}. The log is {data / LOG_NAME}")
        return 1
    print(url, flush=True)
    if not args.no_browser and not webbrowser.open(url):
        say(f"open: no browser could be started; open {url} yourself")
    return 0
