"""Restart the app as the new version after an AppImage update.

Once the app's file is replaced, the app ends (daemon left running) and re-executes it."""
import contextlib
import logging
import os
import signal
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from neoaprs import selfreplace

log = logging.getLogger("neoaprs.desktop")

OWNS_DAEMON = "--owns-daemon"
# Programs the web engines start beside the app (bwrap and xdg-dbus-proxy serve WebKitGTK only).
HELPERS = ("QtWebEngineProcess", "WebKitWebProcess", "WebKitNetworkProcess", "WebKitGPUProcess",
           "bwrap", "xdg-dbus-proxy")
# The system keeps only this many characters of a program's name as the process name.
NAME_LEN = 15
HELPERS_END_SEC = 1.0
HELPERS_POLL_SEC = 0.05
PROC = "/proc"

Identity = tuple[int, int, int, int]


def identity(path: str) -> Identity | None:
    """Return (device, inode, size, mtime) of a file, or None if absent."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns


@dataclass
class AppFile:
    """The AppImage the app runs from; `replaced()` is True once a new, steady file is there."""
    path: str
    started: Identity
    look: Callable[[str], Identity | None] = identity
    seen: Identity | None = None

    @classmethod
    def of(cls, path: str | None, look: Callable[[str], Identity | None] = identity) -> "AppFile | None":
        """Return the file at `path` as it is now, or None."""
        if not path:
            return None
        now = look(path)
        return None if now is None else cls(path, now, look)

    def replaced(self) -> bool:
        now = self.look(self.path)
        if now is None or now == self.started:
            self.seen = None
            return False
        steady = now == self.seen
        self.seen = now
        return steady


def argv(appimage: str, data: Path, encryption: bool, debug: bool) -> list[str]:
    """Return the command line that restarts the app from the new file."""
    return [appimage, "app", "--data", str(data), OWNS_DAEMON, *(["--encryption"] if encryption else []), *(["--debug"] if debug else [])]


def start_again(command: list[str], reexec: Callable[..., None] = selfreplace.reexec) -> None:
    """Replace this process with `command`; return on failure."""
    log.info("NeoAPRS was updated: the app starts again as the new version (%s)", command[0])
    reexec(command, put_back=False)


def helpers(proc: str = PROC, parent: int | None = None) -> list[int]:
    """Return the web engine child processes of `parent` (zombies included); [] without /proc."""
    parent = os.getpid() if parent is None else parent
    names = {name[:NAME_LEN] for name in HELPERS}
    try:
        entries = os.listdir(proc)
    except OSError:
        return []
    found = []
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(os.path.join(proc, entry, "stat"), "rb") as f:
                line = f.read().decode("utf-8", errors="replace")
        except OSError:
            continue
        # "pid (name) state parent ...": the name may hold spaces and brackets.
        name, _, rest = line.partition(" (")[2].rpartition(") ")
        fields = rest.split()
        if name in names and len(fields) > 1 and fields[1] == str(parent):
            found.append(int(entry))
    return sorted(found)


def _waited_for(pid: int, block: bool = False) -> bool:
    """Return whether child `pid` has ended, reaping it."""
    if sys.platform == "win32":
        return True
    else:
        try:
            done, _ = os.waitpid(pid, 0 if block else os.WNOHANG)
        except ChildProcessError:
            return True
        return done == pid


def end_helpers(pids: Iterable[int] | None = None, kill: Callable[[int, int], None] = os.kill, waited_for: Callable[..., bool] = _waited_for, seconds: float = HELPERS_END_SEC,
                clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
    """End the web engine's processes before the exec (SIGTERM, then kill); no-op on Windows."""
    left = [] if sys.platform == "win32" else helpers() if pids is None else list(pids)
    if not left:
        return
    log.info("the web engine's %d processes are ended before the app starts again", len(left))
    for pid in left:
        with contextlib.suppress(OSError):
            kill(pid, signal.SIGTERM)
    deadline = clock() + seconds
    while True:
        left = [pid for pid in left if not waited_for(pid)]
        if not left or clock() >= deadline:
            break
        sleep(HELPERS_POLL_SEC)
    for pid in left:
        log.info("the web engine's process %d did not end within %g s: it is killed", pid, seconds)
        with contextlib.suppress(OSError):
            kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        waited_for(pid, True)
