"""The daemon the app shows: the one that holds the data folder's lock (a service, a `neoaprs run` in a terminal, an earlier `neoaprs open`), or, when none does, one the app starts. The app attaches to the
first kind and leaves it running at Quit; the second kind it owns: it starts it the way `neoaprs open` does (the same code: detached from the app, so that the daemon outlives a crash of the window; the app
stops it at Quit and, while it runs, notices when something else stops it, `neoaprs stop` for one, and ends too). What the app can find out about a daemon is what the commands can (neoaprs/cli/daemonstate.py).
The page's address is the one the daemon writes into the data folder (neoaprs/cli/logfile.py): the app reads it when it opens the session and goes on reading it, since a daemon that starts again
(Update now, a service's restart) may serve the page on another port than before, and the window follows it there."""
import logging
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from neoaprs.cli import opencmd, stopcmd
from neoaprs.cli.daemonstate import is_running
from neoaprs.cli.logfile import read_page
from neoaprs import stopfile
from .links import same_host
from .renew import AppFile

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


def _start_detached(data: Path, encryption: bool = False) -> "subprocess.Popen[bytes]":
    return opencmd.spawn(opencmd.daemon_argv(data, encryption), data)


@dataclass
class Daemon:
    """What the app does to the daemons, as functions that a test replaces: `running(data)`, `start(data)` (a detached daemon; the process object), `wait(data, child, seconds)` (the page's address once the page answers, else None), `stop(data, seconds)`,
    `restarting(data)` (it ended to start again) and `address(data)` (where its page is served now: what it wrote into the data folder, None while it serves none)."""
    running: Callable[[Path], bool] = is_running
    start: Callable[[Path], "subprocess.Popen[bytes]"] = _start_detached
    wait: Callable[[Path, "subprocess.Popen[bytes] | None", float], str | None] = opencmd.wait_for_page
    stop: Callable[[Path, float], bool] = stopcmd.stop_daemon
    restarting: Callable[[Path], bool] = stopfile.restarting
    address: Callable[[Path], str | None] = read_page


def open_session(data: Path, daemon: Daemon | None = None, timeout: float = START_TIMEOUT_SEC, encryption: bool = False, owns: bool = False) -> Session:
    """Attach to the daemon of the data folder, or start one. Raises NoPage when no page comes up. A daemon that someone else started while ours was starting wins the lock: ours ends at once, and the app does not own the one it shows.
    `owns`: the app is started again after Update now (renew.py) and owns the daemon it finds, as the app before it did; a daemon that is starting again as the new version is waited for, not started twice."""
    daemon = daemon or Daemon(start=lambda folder: _start_detached(folder, encryption))       # (a daemon the app starts has encrypted messages when the app was started with --encryption)
    child = None
    if daemon.running(data):
        log.info("a daemon runs on %s: attaching%s", data, " as its owner" if owns else "")
    elif owns and daemon.restarting(data):
        log.info("the daemon on %s is starting again: waiting for it, as its owner", data)
    else:
        log.info("no daemon on %s: starting one", data)
        child = daemon.start(data)
    url = daemon.wait(data, child, timeout)
    if url is None:
        raise NoPage(f"no page came up on {data} within {timeout:g} s; see the log, neoaprs.log in that folder")
    owned = child.poll() is None if child is not None else owns
    return Session(data, url, owned)


class Opening:
    """The session on its way: `opener` (an `open_session` with its arguments) runs in a thread of its own from `start` on, so that the app makes its window while the daemon comes up. `result()` waits for
    it and is the Session, or raises its NoPage; `when_done(callback)` calls back once it is there (at once when it is), in the thread that brought it. What else goes wrong on the way (the daemon's program
    cannot be started) is a NoPage that says so, with the traceback in the log: the window waits for no longer than the opener does."""

    def __init__(self, data: Path, opener: Callable[[], Session]) -> None:
        self.data = data
        self.opener = opener
        self._done = threading.Event()
        self._session: Session | None = None
        self._error: NoPage | None = None
        self._callbacks: list[Callable[[], None]] = []
        self._guard = threading.Lock()
        self.thread = threading.Thread(target=self._run, name="neoaprs-app-open", daemon=True)

    @classmethod
    def opened(cls, session: Session) -> "Opening":
        """One that is there already (a test's, a shell's that is given a session)."""
        opening = cls(session.data, lambda: session)
        opening._finish(session, None)
        return opening

    def start(self) -> "Opening":
        self.thread.start()
        return self

    def _run(self) -> None:
        try:
            self._finish(self.opener(), None)
        except NoPage as e:
            self._finish(None, e)
        except Exception as e:
            log.exception("the daemon on %s could not be started", self.data)
            self._finish(None, NoPage(f"the daemon could not be started on {self.data}: {e.strerror if isinstance(e, OSError) and e.strerror else e}"))

    def _finish(self, session: Session | None, error: NoPage | None) -> None:
        with self._guard:
            self._session, self._error = session, error
            self._done.set()
            callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            callback()

    def done(self) -> bool:
        return self._done.is_set()

    def when_done(self, callback: Callable[[], None]) -> None:
        with self._guard:
            if not self._done.is_set():
                self._callbacks.append(callback)
                return
        callback()

    def result(self) -> Session:
        self._done.wait()
        if self._error is not None:
            raise self._error
        assert self._session is not None
        return self._session


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
    A daemon that ends to start again as a new version (Update now of an AppImage: the note of neoaprs/stopfile.py) has not ended, and while the note is fresh the daemon's lock is not looked at.
    Calls `moved(address)` each time the daemon, the app's own or one it attached to, serves its page at another address than the app last knew (it started again and could not have the port it had): the
    address is read from the file the daemon writes, which is not there while it serves no page, and nothing is asked of the daemon's lock for it. Only the port may be another: an address of
    another host than the one the session was opened on is not the daemon's page, whatever the file says, and the window is never sent there.
    Calls `renewed()` once when the app's own AppImage file (`app_file`) is a new version and the daemon the app owns runs again (renew.py): the app is to start again as the new version."""

    def __init__(self, session: Session, gone: Callable[[], None], daemon: Daemon | None = None, every: float = WATCH_SEC, moved: Callable[[str], None] | None = None,
                 app_file: AppFile | None = None, renewed: Callable[[], None] | None = None) -> None:
        self.session = session
        self.gone = gone
        self.moved = moved
        self.app_file = app_file if renewed is not None else None
        self.renewed = renewed
        self.url = session.url                     # where the page is, as the app knows it
        self.refused: str | None = None            # an address the file named that the app did not follow (said once)
        self.daemon = daemon or Daemon()
        self.every = every
        self._cancelled = threading.Event()
        self.thread = threading.Thread(target=self._run, name="neoaprs-app-watch", daemon=True)

    def start(self) -> None:
        if self.session.owned or self.moved is not None:
            self.thread.start()

    def cancel(self) -> None:
        self._cancelled.set()

    def _run(self) -> None:
        missing = 0
        while not self._cancelled.wait(self.every):
            if self.session.owned:
                again = self.daemon.restarting(self.session.data)
                up = not again and self.daemon.running(self.session.data)          # (the lock is not looked at while the daemon starts again: the look takes it for a moment, and the new daemon that takes it then would find it held and end)
                missing = 0 if up or again else missing + 1                       # (a daemon that starts again as a new version is waited for)
                if missing >= GONE_AFTER:
                    log.info("the daemon on %s has ended: the app ends too", self.session.data)
                    self.gone()
                    return
                if up and self._renewed():
                    return
            self._follow()

    def _renewed(self) -> bool:
        """The app's file is a new version and its daemon, running, has no restart pending (it runs the new file): `renewed` is called, and the watch is over."""
        if self.app_file is None or self.renewed is None or not self.app_file.replaced() or self.daemon.restarting(self.session.data):
            return False
        log.info("the app's file %s is a new version and the daemon on %s runs it: the app starts again", self.app_file.path, self.session.data)
        self.renewed()
        return True

    def _follow(self) -> None:
        if self.moved is None:
            return
        url = self.daemon.address(self.session.data)
        if url is None or url == self.url:
            return
        if not same_host(url, self.session.url):
            if url != self.refused:
                log.warning("the file of the daemon on %s names %s as its page, which is not on the host of %s: the app stays where it is", self.session.data, url, self.session.url)
                self.refused = url
            return
        log.info("the page of the daemon on %s is at %s now (it was at %s): the app follows", self.session.data, url, self.url)
        self.url = url
        self.moved(url)
