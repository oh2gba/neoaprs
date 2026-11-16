"""How `neoaprs stop` ends a daemon on any system: a file called `neoaprs.stop` in the data folder. The command writes it, the daemon looks for it once a second, deletes it and ends the way it ends on SIGTERM.
Nothing is listened to and no key is needed: whoever can write into the data folder (private to the user: mode 0700 on POSIX, the profile's own ACL on Windows) can also kill the process, so the file gives
no one more power. A file that is left (the daemon was not running when it was written) is deleted when the next daemon starts, so that it does not end that one.

A daemon that ends to start again as a new version (Update now of an AppImage) leaves `neoaprs.restarting` beside it, which the new one deletes once it runs: the desktop app, which ends when its daemon does,
waits for the new daemon while the note is fresh.

Beside it the daemon leaves `neoaprs.restart-port`, the port its page is served on, and the daemon that starts while that note is fresh serves the page there again (`noted_port`): the page that is
open in a browser or in the app's window waits at that address, and the port of the settings may have been taken, or come free, since the first start. A daemon that the Windows installer ends and
starts again (Update now there) leaves the port's note for the same reason, and no `neoaprs.restarting`: the app there is ended by the installer, and must not wait for a daemon. The port is a note
and not an argument of the restart: the command line is the operator's or a service manager's and is repeated at every later start, the note is read once and gone; and the installer, which starts the
daemon on Windows, has no part in it.

While the database is brought up to date (a migration: minutes for a large file on a slow card) `neoaprs.migrating` is beside it, written again every few seconds and deleted at the end: what waits
for the daemon's page (`neoaprs open`, the desktop app) waits as long as the note is fresh, and a note that a kill left goes stale by itself. The migration also holds the lock `neoaprs.migrate.lock`
(the kind of instancelock.py, which the system lets go of when its process ends, however it ends): a second NeoAPRS that is to migrate the file waits for it (migrations.py)."""
import asyncio
import contextlib
import stat
import threading
import time
from pathlib import Path

STOP_NAME = "neoaprs.stop"
POLL_SEC = 1.0
RESTART_NAME = "neoaprs.restarting"
RESTART_FRESH_SEC = 90.0                  # a note older than this is of a restart that did not come up
PORT_NAME = "neoaprs.restart-port"
PORT_FRESH_SEC = 900.0                    # how long the port's note is believed: the Windows installer puts every file in place between the daemon's end and its start
PORT_NOTE_BYTES = 16                      # a note longer than this is not the daemon's (a port and a line end are at most seven)


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


def note_port(data_dir: Path, port: int) -> None:
    """The daemon is about to end and be started again (by itself, or by the Windows installer): `port` is where its page is served, for the one that starts in its place. A daemon without a page
    (`port` 0) leaves no note, and takes away one that was there."""
    path = data_dir / PORT_NAME
    if port:
        path.write_text(f"{port}\n", encoding="ascii")
    else:
        path.unlink(missing_ok=True)


def noted_port(data_dir: Path, now: float | None = None) -> int | None:
    """The port the page was served on by the daemon that left the note, while the note is fresh; None when there is no note (no restart, a daemon that had no page, one of 0.20.1 or before), it is
    old, or it is not a port. Only a small ordinary file is read: whatever else has the name (a link, a pipe, a file of any length) is no note, and neither holds the daemon up nor ends it."""
    path = data_dir / PORT_NAME
    try:
        found = path.lstat()
        if not stat.S_ISREG(found.st_mode) or found.st_size > PORT_NOTE_BYTES or abs((time.time() if now is None else now) - found.st_mtime) >= PORT_FRESH_SEC:
            return None
        with path.open("rb") as f:
            text = f.read(PORT_NOTE_BYTES).decode("ascii").strip()
    except (OSError, ValueError):
        return None
    return int(text) if text.isdigit() and len(text) <= 5 and 0 < int(text) <= 65535 else None


def clear_restart(data_dir: Path) -> None:
    """The restart is over: the daemon runs. Both notes go."""
    for name in (RESTART_NAME, PORT_NAME):
        with contextlib.suppress(OSError):
            (data_dir / name).unlink(missing_ok=True)


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
