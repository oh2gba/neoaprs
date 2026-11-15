"""How `neoaprs stop` ends a daemon on any system: a file called `neoaprs.stop` in the data folder. The command writes it, the daemon looks for it once a second, deletes it and ends the way it ends on SIGTERM.
Nothing is listened to and no key is needed: whoever can write into the data folder (private to the user: mode 0700 on POSIX, the profile's own ACL on Windows) can also kill the process, so the file gives
no one more power. A file that is left (the daemon was not running when it was written) is deleted when the next daemon starts, so that it does not end that one.

A daemon that ends to start again as a new version (Update now of an AppImage) leaves `neoaprs.restarting` beside it, which the new one deletes once it runs: the desktop app, which ends when its daemon does,
waits for the new daemon while the note is fresh.

While the database is brought up to date (a migration: minutes for a large file on a slow card) `neoaprs.migrating` is beside it, written again every few seconds and deleted at the end: what waits
for the daemon's page (`neoaprs open`, the desktop app) waits as long as the note is fresh, and a note that a kill left goes stale by itself. The migration also holds the lock `neoaprs.migrate.lock`
(the kind of instancelock.py, which the system lets go of when its process ends, however it ends): a second NeoAPRS that is to migrate the file waits for it (migrations.py)."""
import asyncio
import contextlib
import threading
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


MIGRATING_NAME = "neoaprs.migrating"
MIGRATING_BEAT_SEC = 5.0                  # how often the note is written again while the migration runs
MIGRATING_FRESH_SEC = 30.0                # a note older than this is of a migration that a kill ended
MIGRATE_LOCK_NAME = "neoaprs.migrate.lock"   # held by the process that migrates, from before its copy to its last step, by `neoaprs db set` for its whole run and by a restore (the file stays, as every lock file of the folder does)


class MigratingNote:
    """The note of a migration that runs: `start` writes it and has a thread of its own write it again every `beat_sec`, `stop` ends that and deletes it (both may be called more than once; `stop`
    without `start` does nothing). A folder that cannot be written gets no note, and the migration goes on."""

    def __init__(self, data_dir: Path, beat_sec: float = MIGRATING_BEAT_SEC) -> None:
        self.path = data_dir / MIGRATING_NAME
        self.beat_sec = beat_sec
        self._done = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None:
            self._write()
            self._thread = threading.Thread(target=self._beat, name="neoaprs-migrating", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._done.set()
            self._thread.join()
            self._thread = None
            with contextlib.suppress(OSError):
                self.path.unlink(missing_ok=True)

    def _beat(self) -> None:
        while not self._done.wait(self.beat_sec):
            self._write()

    def _write(self) -> None:
        with contextlib.suppress(OSError):
            self.path.write_text("migrating\n", encoding="ascii")


def migrating(data_dir: Path, now: float | None = None) -> bool:
    """Is the database of the folder being brought up to date: is the note there, and fresh? A note whose time is far ahead of `now` was written before the clock went back, by a migration that
    a kill ended (a running one writes it again every few seconds): it is not fresh."""
    try:
        age = (time.time() if now is None else now) - (data_dir / MIGRATING_NAME).stat().st_mtime
    except OSError:
        return False
    return abs(age) < MIGRATING_FRESH_SEC


def clear_stale_migrating(data_dir: Path) -> None:
    """Removes the note of a migration that a kill ended (one that is not fresh); a fresh one, which another process keeps writing, stays."""
    with contextlib.suppress(OSError):
        if (data_dir / MIGRATING_NAME).exists() and not migrating(data_dir):
            (data_dir / MIGRATING_NAME).unlink()
