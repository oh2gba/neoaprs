"""Note files in the data folder for `neoaprs stop`, restarts and migrations on any system.

Files: `neoaprs.stop`, `neoaprs.restarting`, `neoaprs.restart-port` (the page's port, so an open
browser page keeps its address) and `neoaprs.migrating` (goes stale by itself after a kill).
"""
import asyncio
import contextlib
import stat
import threading
import time
from pathlib import Path

STOP_NAME = "neoaprs.stop"
POLL_SEC = 1.0
RESTART_NAME = "neoaprs.restarting"
# an older note is of a restart that did not come up
RESTART_FRESH_SEC = 90.0
PORT_NAME = "neoaprs.restart-port"
# the Windows installer replaces every file between the daemon's end and its start
PORT_FRESH_SEC = 900.0
# a longer note is not the daemon's
PORT_NOTE_BYTES = 16


def path_in(data_dir: Path) -> Path:
    return data_dir / STOP_NAME


def request(data_dir: Path) -> None:
    path_in(data_dir).write_text("stop\n", encoding="ascii")


def requested(data_dir: Path) -> bool:
    return path_in(data_dir).is_file()


def clear(data_dir: Path) -> None:
    with contextlib.suppress(OSError):
        path_in(data_dir).unlink(missing_ok=True)


async def watch(data_dir: Path, stop: asyncio.Event, poll_sec: float = POLL_SEC) -> None:
    """Set `stop` and delete the file once a stop is requested."""
    while not stop.is_set():
        if requested(data_dir):
            clear(data_dir)
            stop.set()
            return
        await asyncio.sleep(poll_sec)


def mark_restart(data_dir: Path) -> None:
    (data_dir / RESTART_NAME).write_text("restart\n", encoding="ascii")


def restarting(data_dir: Path, now: float | None = None) -> bool:
    try:
        age = (time.time() if now is None else now) - (data_dir / RESTART_NAME).stat().st_mtime
    except OSError:
        return False
    return age < RESTART_FRESH_SEC


def note_port(data_dir: Path, port: int) -> None:
    """Note the port of the page for the next daemon; `port` 0 removes the note."""
    path = data_dir / PORT_NAME
    if port:
        path.write_text(f"{port}\n", encoding="ascii")
    else:
        path.unlink(missing_ok=True)


def noted_port(data_dir: Path, now: float | None = None) -> int | None:
    """Return the port noted by the previous daemon, or None; only a small regular file is read."""
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
    for name in (RESTART_NAME, PORT_NAME):
        with contextlib.suppress(OSError):
            (data_dir / name).unlink(missing_ok=True)


MIGRATING_NAME = "neoaprs.migrating"
MIGRATING_BEAT_SEC = 5.0
# an older note is of a migration that a kill ended
MIGRATING_FRESH_SEC = 30.0
# lock held by a migrating process, `neoaprs db set` and a restore; the file stays
MIGRATE_LOCK_NAME = "neoaprs.migrate.lock"


class MigratingNote:
    """The note of a running migration: rewritten every `beat_sec` until `stop`."""

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
    """Return whether the migration note is there and fresh."""
    try:
        age = (time.time() if now is None else now) - (data_dir / MIGRATING_NAME).stat().st_mtime
    except OSError:
        return False
    return abs(age) < MIGRATING_FRESH_SEC


def clear_stale_migrating(data_dir: Path) -> None:
    """Remove a stale migration note; a fresh one stays."""
    with contextlib.suppress(OSError):
        if (data_dir / MIGRATING_NAME).exists() and not migrating(data_dir):
            (data_dir / MIGRATING_NAME).unlink()
