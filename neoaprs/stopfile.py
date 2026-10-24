"""How `neoaprs stop` ends a daemon on any system: a file called `neoaprs.stop` in the data folder. The command writes it, the daemon looks for it once a second, deletes it and ends the way it ends on SIGTERM.
Nothing is listened to and no key is needed: whoever can write into the data folder (private to the user: mode 0700 on POSIX, the profile's own ACL on Windows) can also kill the process, so the file gives
no one more power. A file that is left (the daemon was not running when it was written) is deleted when the next daemon starts, so that it does not end that one.

A daemon that ends to start again as a new version (Update now of an AppImage) leaves `neoaprs.restarting` beside it, which the new one deletes once it runs: the desktop app, which ends when its daemon does,
waits for the new daemon while the note is fresh."""
import asyncio
import contextlib
import time
from pathlib import Path

STOP_NAME = "neoaprs.stop"
POLL_SEC = 1.0
RESTART_NAME = "neoaprs.restarting"
RESTART_FRESH_SEC = 90.0                  # a note older than this is of a restart that did not come up


def path_in(data_dir: Path) -> Path:
    return data_dir / STOP_NAME


def request(data_dir: Path) -> None:
    """Asks the daemon that holds the data folder to end."""
    path_in(data_dir).write_text("stop\n", encoding="ascii")


def requested(data_dir: Path) -> bool:
    return path_in(data_dir).is_file()


def clear(data_dir: Path) -> None:
    with contextlib.suppress(OSError):
        path_in(data_dir).unlink(missing_ok=True)


async def watch(data_dir: Path, stop: asyncio.Event, poll_sec: float = POLL_SEC) -> None:
    """Sets `stop` (and takes the file away) as soon as a stop is requested; runs until cancelled."""
    while not stop.is_set():
        if requested(data_dir):
            clear(data_dir)
            stop.set()
            return
        await asyncio.sleep(poll_sec)


def mark_restart(data_dir: Path) -> None:
    """The daemon is about to end and start again."""
    (data_dir / RESTART_NAME).write_text("restart\n", encoding="ascii")


def restarting(data_dir: Path, now: float | None = None) -> bool:
    """Is a daemon of the folder starting again: is the note there, and fresh?"""
    try:
        age = (time.time() if now is None else now) - (data_dir / RESTART_NAME).stat().st_mtime
    except OSError:
        return False
    return age < RESTART_FRESH_SEC


def clear_restart(data_dir: Path) -> None:
    with contextlib.suppress(OSError):
        (data_dir / RESTART_NAME).unlink(missing_ok=True)
