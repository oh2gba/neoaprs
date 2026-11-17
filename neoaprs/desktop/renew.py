"""The app after Update now of an AppImage: the daemon puts the new file in the place of the old one and starts it again in its own process, and the app, a process of its own started from the same file, would go
on as the old version (its window, its tray and its menu) until it is quit. So the app that started its daemon watches its own file too (`AppFile`, looked at by session.DaemonWatch): once the file is another
one than the app was started from, the same other one at two looks in a row, and the daemon runs again as the new version (it holds the data folder and has no restart pending), the app ends as Quit would but
leaves the daemon running (menu.AppActions.renew), lets go of the data folder (its one-app lock, the port and the window's size and place), and is started again from the new file in its own place
(`start_again`: the same process, so nothing is left behind), with `--owns-daemon`, which makes it the owner of the daemon it finds: its Quit stops it, as it did before.
Only an app that started its daemon does this: one that attached to a daemon (a service, one started by hand) is left as it is. Windows needs none of it: the installer of Update now ends the app and starts
it again (packaging/windows/neoaprs.iss). When the new file cannot be started, nothing is put back (the daemon runs the new file already) and the daemon is stopped as Quit would stop it, so that no daemon is
left without the app that owned it. Before the exec the processes the window's engine started beside the app are ended and waited for (`end_helpers`)."""
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
HELPERS = ("QtWebEngineProcess", "WebKitWebProcess", "WebKitNetworkProcess", "WebKitGPUProcess",     # the programs a web engine of the app starts beside it, Qt's and WebKitGTK's; with the
           "bwrap", "xdg-dbus-proxy")    # sandbox on (gtkenv.py) WebKitGTK starts its web process through bubblewrap and its D-Bus proxy, which the app starts for nothing else
NAME_LEN = 15                                     # how much of a program's name the system keeps as the process's name
HELPERS_END_SEC = 5.0
HELPERS_POLL_SEC = 0.05
PROC = "/proc"

Identity = tuple[int, int, int, int]


def identity(path: str) -> Identity | None:
    """What tells one file at `path` from another put in its place: the device, the inode, the size and the time it was written; None when there is no file."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns


@dataclass
class AppFile:
    """The AppImage file the app runs from, as it was when the app started. `replaced()` is True once another file is in its place and has stayed the same since the last look (a file that is still being
    written is not started)."""
    path: str
    started: Identity
    look: Callable[[str], Identity | None] = identity
    seen: Identity | None = None

    @classmethod
    def of(cls, path: str | None, look: Callable[[str], Identity | None] = identity) -> "AppFile | None":
        """The file at `path` as it is now; None outside an AppImage (`path` None) or when it cannot be looked at."""
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
    """The command line of the app started again from the new file: the same data folder and flags, the owner of the daemon. The window comes back shown, as it does after the installer of Windows."""
    return [appimage, "app", "--data", str(data), OWNS_DAEMON, *(["--encryption"] if encryption else []), *(["--debug"] if debug else [])]


def start_again(command: list[str], reexec: Callable[..., None] = selfreplace.reexec) -> None:
    """Runs `command` in the place of this process, which has let go of everything (cmd.py); the old file is never put back. Returns only when the new file could not be started."""
    log.info("NeoAPRS was updated: the app starts again as the new version (%s)", command[0])
    reexec(command, put_back=False)


def helpers(proc: str = PROC, parent: int | None = None) -> list[int]:
    """The processes of the web engine that are children of this process (`parent`), running or ended and not yet waited for: the window is gone, and what its engine started may not be. [] where there is
    no /proc to list them in."""
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
        name, _, rest = line.partition(" (")[2].rpartition(") ")          # "pid (name) state parent ...": the name may hold spaces and brackets of its own
        fields = rest.split()
        if name in names and len(fields) > 1 and fields[1] == str(parent):
            found.append(int(entry))
    return sorted(found)


def _waited_for(pid: int, block: bool = False) -> bool:
    """Whether the child `pid` has ended, and is waited for now (one that is no child of this process any more counts as ended)."""
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
    """Ends the web engine's processes (`helpers()`) and waits for them, before the new file takes the place of this process: they would run on from the old version's files (the mount of the old file
    stays while they do) and hold the window's profile in the data folder that the new window opens, and once ended they would stay as processes nobody waits for, the new program knowing nothing of them.
    They are asked to end (SIGTERM) and given `seconds`; the rest are killed. Nothing on Windows, where the installer ends the app."""
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
            kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))          # (never on Windows, which has none)
        waited_for(pid, True)
