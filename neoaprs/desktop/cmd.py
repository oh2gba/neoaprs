"""`neoaprs app [--data DIR] [--tray]` and `neoaprs-app`: the desktop app. It shows the page of the daemon that holds the data folder in a window (attaching to it), or starts a daemon of its own the way
`neoaprs open` does and stops it at Quit; the tray icon is where it lives when the window is closed. `--tray` starts with the window hidden (what start at sign-in runs), `--quit` ends the app that is running
(the uninstaller does). A second app on the same data folder raises the first one's window and ends.
Exit code 0: it ran and ended; 1: no page came up, or the toolkit could not start; 2: wrong arguments."""
import argparse
import importlib
import logging
import os
import sys
import time
import webbrowser
from pathlib import Path

from neoaprs.cli import opencmd, uncaught
from neoaprs.cli.output import say
from neoaprs.paths import default_data_dir

from . import appstate, shell, splash
from .autostart import autostart_for
from .session import NoPage, Opening, Session, open_session
from .shell import Choice, Launch
from .single import SingleApp, process_alive

log = logging.getLogger("neoaprs.desktop")
QUIT_WAIT_SEC = 40.0                              # a little more than the daemon is given to end (session.STOP_TIMEOUT_SEC)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neoaprs app", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default=str(default_data_dir()), help="the data folder of the daemon; default %(default)s")
    p.add_argument("--tray", action="store_true", help="start with the window hidden, in the tray (what start at sign-in runs)")
    p.add_argument("--quit", action="store_true", help="end the app that is running on the data folder (and the daemon too, if the app started it), wait until it has, and exit")
    p.add_argument("--timeout", type=float, default=60.0, metavar="SEC", help="how long to wait for the daemon's page; default %(default)s")
    p.add_argument("--debug", action="store_true", help="log more")
    p.add_argument("--encryption", action="store_true", help="a daemon the app starts allows encrypted messages (the daemon's --encryption), and so does start at sign-in once it is ticked in the tray menu")
    return p


def browser_only(session: Session, choice: Choice, tray: bool) -> int:
    """No shell can run (no toolkit installed, or the display is not there): the page goes to the browser and the daemon is left as it is, as `neoaprs open` leaves it. There is no app left to stop it, so it says how."""
    log.warning("%s", choice.describe())
    if choice.why:
        say(f"app: no window ({choice.why[0]}); `pip install \"neoaprs[app]\"` adds what it needs")
    if not tray and not webbrowser.open(session.url):
        say(f"app: no browser could be started; open {session.url} yourself")
    print(session.url, flush=True)
    if session.owned:
        say("app: NeoAPRS keeps running; `neoaprs stop` ends it")
    return 0


def run_shell(choice: Choice, launch: Launch) -> int:
    """Runs the shell the choice names; 1 when it fails to start, with the page in the browser so that the run is not wasted (once the page is there; when it never comes, that is said instead)."""
    assert choice.module is not None
    try:
        return int(importlib.import_module(choice.module).run(launch))
    except Exception:
        log.exception("the desktop shell %s could not run", choice.module)
        splash.done()
        say(f"app: the window could not be started ({choice.module}; see {launch.data / appstate.LOG_NAME}): opening the page in the browser instead")
        try:
            session = launch.opening.result()
        except NoPage as e:
            return launch.no_page(e)
        browser_only(session, Choice(None, False), launch.hidden)
        return 1


def quit_the_app(data: Path, wait_sec: float) -> int:
    """`--quit`: says `quit` to the app that holds the folder and waits until it has let go of it (it stops its own daemon first, which takes a moment) and its process is gone. 0 when none runs (any more)."""
    single = SingleApp(data)
    if not single.running():
        say(f"app: NeoAPRS app is not running on {data}")
        return 0
    pid = single.pid()
    single.tell_the_other("quit")
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        if not single.running() and (pid is None or not process_alive(pid)):   # (the lock goes before the process: the window's engine unloads after it, and a file of the app is in use until then)
            say("app: NeoAPRS app has ended")
            return 0
        time.sleep(0.2)
    say(f"app: NeoAPRS app on {data} did not end within {wait_sec:g} s")
    return 1


def run(args: argparse.Namespace) -> int:
    """The daemon is attached to or started first, without waiting for it: the toolkit is looked for (imported) and the shell makes its window while the daemon comes up."""
    data = Path(args.data).expanduser().resolve()
    single = SingleApp(data)
    if not single.acquire():
        splash.done()
        if not args.tray:
            single.tell_the_other("show")
        return 0
    opening = Opening(data, lambda: open_session(data, timeout=args.timeout, encryption=args.encryption)).start()
    choice = shell.choose()
    launch = Launch(data, opening, args.tray, choice.window, autostart_for(data, encryption=args.encryption), single, describe=choice.describe())
    try:
        if choice.module is None:
            splash.done()
            try:
                session = launch.context(opening.result()).session
            except NoPage as e:
                return launch.no_page(e)
            single.close()
            return browser_only(session, choice, args.tray)
        return run_shell(choice, launch)
    finally:
        launch.close()


def main(argv: list[str] | None = None) -> int:
    """The app's run; the splash of Windows (splash.py) goes when it ends, however it ends, if the window has not taken it away before."""
    try:
        return _main(argv)
    finally:
        splash.done()


def _main(argv: list[str] | None) -> int:
    args = parser().parse_args(sys.argv[1:] if argv is None else argv)
    data = Path(args.data).expanduser().resolve()
    if args.quit:
        return quit_the_app(data, QUIT_WAIT_SEC)
    try:
        data.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        splash.done()                               # (before the message box, which the splash would cover)
        opencmd.tell_the_user(f"app: the data folder {data} cannot be made or used: {e.strerror or e}")
        return 1
    appstate.setup_logging(data, args.debug)
    uncaught.install(log, chain=True)
    return run(args)


def gui_main() -> int:
    """`neoaprs-app`: the same for a program that has no console (Windows): the streams that are not there are replaced, so that a print or a usage error cannot fail."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    return main()
