"""The daemon the app shows: the one that holds the data folder's lock (a service, a `neoaprs run` in a terminal, an earlier `neoaprs open`), or, when none does, one the app starts. The app attaches to the
first kind and leaves it running at Quit; the second kind it owns: it starts it the way `neoaprs open` does (the same code: detached from the app, so that the daemon outlives a crash of the window; the app
stops it at Quit and, while it runs, notices when something else stops it, `neoaprs stop` for one, and ends too). What the app can find out about a daemon is what the commands can (neoaprs/cli/daemonstate.py)."""
import logging
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from neoaprs.cli import opencmd, stopcmd
from neoaprs.cli.daemonstate import is_running
from neoaprs import stopfile

log = logging.getLogger("neoaprs.desktop")

START_TIMEOUT_SEC = 60.0
STOP_TIMEOUT_SEC = 30.0
WATCH_SEC = 2.0
GONE_AFTER = 2                                    # polls in a row that find no daemon: one is a daemon that is restarting, two is one that ended


class NoPage(Exception):
    """No daemon came up on the data folder (or its page does not answer); the text says why."""


@dataclass(frozen=True)
class Session:
    data: Path
    url: str
    owned: bool                                   # the app started the daemon: Quit stops it, and its end is the app's end


def _start_detached(data: Path) -> "subprocess.Popen[bytes]":
    return opencmd.spawn(opencmd.daemon_argv(data), data)


@dataclass
class Daemon:
    """What the app does to the daemons, as functions that a test replaces: `running(data)`, `start(data)` (a detached daemon; the process object), `wait(data, child, seconds)` (the page's address once the page answers, else None) and `stop(data, seconds)`."""
    running: Callable[[Path], bool] = is_running
    start: Callable[[Path], "subprocess.Popen[bytes]"] = _start_detached
    wait: Callable[[Path, "subprocess.Popen[bytes] | None", float], str | None] = opencmd.wait_for_page
    stop: Callable[[Path, float], bool] = stopcmd.stop_daemon
    restarting: Callable[[Path], bool] = stopfile.restarting


def open_session(data: Path, daemon: Daemon | None = None, timeout: float = START_TIMEOUT_SEC) -> Session:
    """Attach to the daemon of the data folder, or start one. Raises NoPage when no page comes up. A daemon that someone else started while ours was starting wins the lock: ours ends at once, and the app does not own the one it shows."""
    daemon = daemon or Daemon()
    child = None
    if daemon.running(data):
        log.info("a daemon runs on %s: attaching", data)
    else:
        log.info("no daemon on %s: starting one", data)
        child = daemon.start(data)
    url = daemon.wait(data, child, timeout)
    if url is None:
        raise NoPage(f"no page came up on {data} within {timeout:g} s; see the log, neoaprs.log in that folder")
    owned = child is not None and child.poll() is None
    return Session(data, url, owned)


def stop_owned(session: Session, daemon: Daemon | None = None) -> bool:
    """Quit's half that is the daemon's: stops it when the app started it, and only then. True when the daemon is not running after it."""
    daemon = daemon or Daemon()
    if not session.owned:
        return True
    ended = daemon.stop(session.data, STOP_TIMEOUT_SEC)
    if not ended:
        log.warning("the daemon on %s did not end within %g s", session.data, STOP_TIMEOUT_SEC)
    return ended


class DaemonWatch:
    """Calls `gone` once when the daemon the app owns has ended without the app stopping it (`neoaprs stop`, the uninstaller, the Start menu's Stop). It looks every `every` seconds in a thread of its own; `cancel` stops it.
    A daemon that ends to start again as a new version (Update now of an AppImage: the note of neoaprs/stopfile.py) has not ended."""

    def __init__(self, session: Session, gone: Callable[[], None], daemon: Daemon | None = None, every: float = WATCH_SEC) -> None:
        self.session = session
        self.gone = gone
        self.daemon = daemon or Daemon()
        self.every = every
        self._cancelled = threading.Event()
        self.thread = threading.Thread(target=self._run, name="neoaprs-app-watch", daemon=True)

    def start(self) -> None:
        if self.session.owned:
            self.thread.start()

    def cancel(self) -> None:
        self._cancelled.set()

    def _run(self) -> None:
        missing = 0
        while not self._cancelled.wait(self.every):
            missing = 0 if self.daemon.running(self.session.data) or self.daemon.restarting(self.session.data) else missing + 1      # (a daemon that starts again as a new version is waited for)
            if missing >= GONE_AFTER:
                log.info("the daemon on %s has ended: the app ends too", self.session.data)
                self.gone()
                return
