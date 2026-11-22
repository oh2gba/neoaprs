"""`neoaprs app [--data DIR] [--tray]` and `neoaprs-app`: the desktop app.

It shows the page of the daemon that holds the data folder in a window, starting a daemon as
`neoaprs open` does and stopping it at Quit. `--tray` starts hidden; `--quit` ends the running app.
A second app on the same data folder raises the first one's window and ends.
Exit code 0: it ran and ended; 1: no page came up or the toolkit failed; 2: wrong arguments."""
import argparse
import importlib
import logging
import os
import sys
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path

from neoaprs.cli import opencmd, uncaught
from neoaprs.cli.output import say
from neoaprs.cli.servicecmd import appimage_file
from neoaprs.paths import default_data_dir

from . import appstate, renew, shell, splash
from .autostart import autostart_for
from .session import NoPage, Opening, Session, open_session, stop_owned
from .shell import Choice, Launch
from .single import SingleApp, process_alive

log = logging.getLogger("neoaprs.desktop")
# A little more than the daemon is given to end (session.STOP_TIMEOUT_SEC).
QUIT_WAIT_SEC = 40.0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neoaprs app", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default=str(default_data_dir()), help="the data folder of the daemon; default %(default)s")
    p.add_argument("--tray", action="store_true", help="start with the window hidden, in the tray (what start at sign-in runs)")
    p.add_argument("--quit", action="store_true", help="end the app that is running on the data folder (and the daemon too, if the app started it), wait until it has, and exit")
    p.add_argument("--timeout", type=float, default=60.0, metavar="SEC", help="how long to wait for the daemon's page; default %(default)s")
    p.add_argument("--debug", action="store_true", help="log more")
    p.add_argument("--encryption", action="store_true", help="a daemon the app starts allows encrypted messages (the daemon's --encryption), and so does start at sign-in once it is ticked in the tray menu")
    # Passed when the app restarts itself after Update now (renew.py).
    p.add_argument(renew.OWNS_DAEMON, dest="owns_daemon", action="store_true", help=argparse.SUPPRESS)
    return p


def browser_only(session: Session, choice: Choice, tray: bool) -> int:
    """Open the page in the browser when no shell can run (no toolkit, or no display).

    The daemon is left running, as `neoaprs open` leaves it; no app remains to stop it, so say how.
    """
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
    """Run the chosen shell; if it fails to start, open the page in the browser and return 1."""
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
    """`--quit`: tell the app holding the folder to quit and wait until it and its process are gone.

    The app stops its own daemon first, which takes a moment. Return 0 if none runs.
    """
    single = SingleApp(data)
    if not single.running():
        say(f"app: NeoAPRS app is not running on {data}")
        return 0
    pid = single.pid()
    single.tell_the_other("quit")
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        # The lock goes before the process; the web engine unloads later and holds app files.
        if not single.running() and (pid is None or not process_alive(pid)):
            say("app: NeoAPRS app has ended")
            return 0
        time.sleep(0.2)
    say(f"app: NeoAPRS app on {data} did not end within {wait_sec:g} s")
    return 1


def run(args: argparse.Namespace) -> int:
    """Attach to or start the daemon without waiting; the shell makes its window meanwhile."""
    data = Path(args.data).expanduser().resolve()
    single = SingleApp(data)
    try:
        first = single.acquire()
    except OSError as e:
        return data_unusable(data, e)
    if not first:
        splash.done()
        if not args.tray:
            single.tell_the_other("show")
        return 0
    app_file = renew.AppFile.of(appimage_file())
    opening = Opening(data, lambda: open_session(data, timeout=args.timeout, encryption=args.encryption, owns=args.owns_daemon)).start()
    choice = shell.choose()
    launch = Launch(data, opening, args.tray, choice.window, autostart_for(data, encryption=args.encryption), single, describe=choice.describe(), tray=choice.tray, app_file=app_file)
    try:
        if choice.module is None:
            splash.done()
            try:
                session = launch.context(opening.result()).session
            except NoPage as e:
                return launch.no_page(e)
            single.close()
            return browser_only(session, choice, args.tray)
        code = run_shell(choice, launch)
    finally:
        launch.close()
    return start_again(launch, app_file, args) if launch.ctx is not None and launch.ctx.renewing() and app_file is not None else code


def start_again(launch: Launch, app_file: renew.AppFile, args: argparse.Namespace, start: Callable[[list[str]], None] | None = None) -> int:
    """Replace this process with the new version; return only if that failed (the daemon stops)."""
    assert launch.ctx is not None
    session = launch.ctx.session
    renew.end_helpers()
    (start or renew.start_again)(renew.argv(app_file.path, session.data, args.encryption, args.debug))
    say("app: the new version of NeoAPRS could not be started; NeoAPRS stops")
    stop_owned(session, launch.ctx.daemon)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run the app; the Windows splash (splash.py) is closed however the run ends."""
    try:
        return _main(argv)
    finally:
        splash.done()


def data_unusable(data: Path, error: OSError) -> int:
    # Close the splash first: it would cover the message box.
    splash.done()
    opencmd.tell_the_user(f"app: the data folder {data} cannot be made or used: {error.strerror or error}")
    return 1


def _main(argv: list[str] | None) -> int:
    args = parser().parse_args(sys.argv[1:] if argv is None else argv)
    data = Path(args.data).expanduser().resolve()
    if args.quit:
        return quit_the_app(data, QUIT_WAIT_SEC)
    try:
        data.mkdir(parents=True, exist_ok=True)
        appstate.setup_logging(data, args.debug)
    except OSError as e:
        return data_unusable(data, e)
    uncaught.install(log, chain=True)
    return run(args)


def gui_main() -> int:
    """`neoaprs-app`: as `main`, without a console (Windows). Missing streams are replaced."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    return main()
