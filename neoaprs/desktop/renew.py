"""The app after Update now of an AppImage: the daemon puts the new file in the place of the old one and starts it again in its own process, and the app, a process of its own started from the same file, would go
on as the old version (its window, its tray and its menu) until it is quit. So the app that started its daemon watches its own file too (`AppFile`, looked at by session.DaemonWatch): once the file is another
one than the app was started from, the same other one at two looks in a row, and the daemon runs again as the new version (it holds the data folder and has no restart pending), the app ends as Quit would but
leaves the daemon running (menu.AppActions.renew), lets go of the data folder (its one-app lock, the port and the window's size and place), and is started again from the new file in its own place
(`start_again`: the same process, so nothing is left behind), with `--owns-daemon`, which makes it the owner of the daemon it finds: its Quit stops it, as it did before.
Only an app that started its daemon does this: one that attached to a daemon (a service, one started by hand) is left as it is. Windows needs none of it: the installer of Update now ends the app and starts
it again (packaging/windows/neoaprs.iss). When the new file cannot be started, nothing is put back (the daemon runs the new file already) and the daemon is stopped as Quit would stop it, so that no daemon is
left without the app that owned it."""
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from neoaprs import selfreplace

log = logging.getLogger("neoaprs.desktop")

OWNS_DAEMON = "--owns-daemon"

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
