"""The daemon the app shows: the one holding the data folder's lock, or one the app starts.

The app attaches to an existing daemon and leaves it running at Quit; otherwise it starts and
owns one, stops it at Quit, and ends if something else stops it."""

import logging
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from neoaprs.cli import opencmd, stopcmd
from neoaprs.cli.daemonstate import is_running
from neoaprs.cli.logfile import network_is_on, read_page
from neoaprs import stopfile
from .links import same_host
from .renew import AppFile

log = logging.getLogger("neoaprs.desktop")

START_TIMEOUT_SEC = 60.0
STOP_TIMEOUT_SEC = 30.0
WATCH_SEC = 2.0
# Consecutive polls without a daemon before it counts as gone (one may be a restart).
GONE_AFTER = 2


class NoPage(Exception):
    """No daemon came up on the data folder, or its page does not answer; the text says why."""


@dataclass(frozen=True)
class Session:
    data: Path
    url: str
    owned: bool  # the app started the daemon: Quit stops it


def _start_detached(data: Path, encryption: bool = False) -> "subprocess.Popen[bytes]":
    return opencmd.spawn(opencmd.daemon_argv(data, encryption), data)


@dataclass
class Daemon:
    """The operations on daemons, as functions that a test can replace."""

    running: Callable[[Path], bool] = is_running
    start: Callable[[Path], "subprocess.Popen[bytes]"] = _start_detached
    wait: Callable[[Path, "subprocess.Popen[bytes] | None", float], str | None] = opencmd.wait_for_page
    stop: Callable[[Path, float], bool] = stopcmd.stop_daemon
    restarting: Callable[[Path], bool] = stopfile.restarting
    address: Callable[[Path], str | None] = read_page
    network: Callable[[Path], bool] = network_is_on


def open_session(
    data: Path,
    daemon: Daemon | None = None,
    timeout: float = START_TIMEOUT_SEC,
    encryption: bool = False,
    owns: bool = False,
) -> Session:
    """Attach to the data folder's daemon, or start one. Raise NoPage if no page comes up.

    `owns`: the app was restarted by an update and owns the daemon it finds."""
    daemon = daemon or Daemon(start=lambda folder: _start_detached(folder, encryption))
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
    """A session opened in a thread; `result()` waits for it, `when_done` calls back. Failures become NoPage."""

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
        """Return an Opening that is already finished with `session`."""
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
            self._finish(
                None,
                NoPage(
                    f"the daemon could not be started on {self.data}: {e.strerror if isinstance(e, OSError) and e.strerror else e}"
                ),
            )

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
    """Stop the daemon at Quit, only if the app started it. Return True if it is not running afterwards."""
    daemon = daemon or Daemon()
    if not session.owned:
        return True
    ended = daemon.stop(session.data, STOP_TIMEOUT_SEC)
    if not ended:
        log.warning("the daemon on %s did not end within %g s", session.data, STOP_TIMEOUT_SEC)
    return ended


class DaemonWatch:
    """Poll the daemon in a thread and call back: `gone`, `moved(address)`, `network_moved()`, `renewed()`.

    Only the port may change: an address on another host is never followed."""

    def __init__(
        self,
        session: Session,
        gone: Callable[[], None],
        daemon: Daemon | None = None,
        every: float = WATCH_SEC,
        moved: Callable[[str], None] | None = None,
        app_file: AppFile | None = None,
        renewed: Callable[[], None] | None = None,
        network_moved: Callable[[], None] | None = None,
    ) -> None:
        self.session = session
        self.gone = gone
        self.moved = moved
        self.app_file = app_file if renewed is not None else None
        self.renewed = renewed
        self.url = session.url
        self.network_moved = network_moved
        self.network: bool | None = None  # served to the network at the last look
        self.refused: str | None = None  # an address not followed (logged once)
        self.daemon = daemon or Daemon()
        self.missing = 0  # consecutive looks that found the owned daemon gone
        self.every = every
        self._cancelled = threading.Event()
        self.thread = threading.Thread(target=self._run, name="neoaprs-app-watch", daemon=True)

    def start(self) -> None:
        if self.session.owned or self.moved is not None or self.network_moved is not None:
            if self.network_moved is not None:
                self.network = self.daemon.network(self.session.data)
            self.thread.start()

    def cancel(self) -> None:
        self._cancelled.set()

    def _run(self) -> None:
        while not self._cancelled.wait(self.every):
            try:
                if self._look():
                    return
            except Exception:
                log.exception("a look at the daemon on %s failed", self.session.data)

    def _look(self) -> bool:
        """Look at the daemon once; return True when the watch is over."""
        if self.session.owned:
            again = self.daemon.restarting(self.session.data)
            # While the daemon restarts the lock is not checked: the check holds it briefly, and
            # the new daemon would find it taken and exit.
            up = not again and self.daemon.running(self.session.data)
            self.missing = 0 if up or again else self.missing + 1
            if self.missing >= GONE_AFTER:
                log.info("the daemon on %s has ended: the app ends too", self.session.data)
                self.gone()
                return True
            if up and self._renewed():
                return True
        self._follow()
        self._follow_network()
        return False

    def _follow_network(self) -> None:
        """Call `network_moved` if the network note changed since the last look; the first look only records it."""
        if self.network_moved is None:
            return
        now = self.daemon.network(self.session.data)
        before, self.network = self.network, now
        if before is not None and before != now:
            log.info(
                "the page of the daemon on %s is %s the network now",
                self.session.data,
                "served to" if now else "no longer served to",
            )
            self.network_moved()

    def _renewed(self) -> bool:
        """Call `renewed` and return True when the app's file is new and the running daemon has no restart pending."""
        if (
            self.app_file is None
            or self.renewed is None
            or not self.app_file.replaced()
            or self.daemon.restarting(self.session.data)
        ):
            return False
        log.info(
            "the app's file %s is a new version and the daemon on %s runs it: the app starts again",
            self.app_file.path,
            self.session.data,
        )
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
                log.warning(
                    "the file of the daemon on %s names %s as its page, which is not on the host of %s: the app stays where it is",
                    self.session.data,
                    url,
                    self.session.url,
                )
                self.refused = url
            return
        log.info(
            "the page of the daemon on %s is at %s now (it was at %s): the app follows",
            self.session.data,
            url,
            self.url,
        )
        self.url = url
        self.moved(url)
