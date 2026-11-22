"""Decide whether `neoaprs db` may open the database now, beside other users of the data folder.

No command runs while a migration is in progress. A write (`set`) holds the migration lock,
and is refused while a daemon holds the folder and the file is older than this version."""
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from neoaprs.instancelock import LOCK_NAME, AlreadyRunning, InstanceLock, is_file, is_held
from neoaprs.migrations import SCHEMA_VERSION, hold_for_writing, let_go
from neoaprs.stopfile import migrating
from neoaprs.supportsql import live_version

MIGRATING = "NeoAPRS is bringing it up to date now (a large file takes minutes); try again when that is done"
WRITING = "another `neoaprs db` command is writing it now; try again when that is done"
BEFORE = ("NeoAPRS is running with this folder and the database is not up to date yet: if it has just started, it is bringing it up to date, so try again in a minute; if it is the version "
          "before, stop it (`neoaprs stop`), and the new one brings it up to date at its start")
TURN_POLL_SEC = 0.05            # retry interval while another write holds the lock


@contextmanager
def held(path: Path, writing: bool, wait_ms: int) -> Iterator[str]:
    """Yield "" if the command may go on (a write holds the lock until the block ends), else the refusal text.

    `wait_ms` is how long a write waits for another writer's lock (`_turn`)."""
    if migrating(path.parent):
        yield MIGRATING
        return
    if not writing:
        yield ""
        return
    try:
        lock = _turn(path.parent, wait_ms)
    except AlreadyRunning:
        yield MIGRATING if migrating(path.parent) else WRITING
        return
    try:
        yield BEFORE if older_beside_daemon(path) else ""
    finally:
        let_go(lock)


def _turn(folder: Path, wait_ms: int) -> InstanceLock | None:
    """Return the `hold_for_writing` lock, retrying for at most `wait_ms` while another holder has it.

    Raise AlreadyRunning after that, or at once while a migration runs."""
    end = time.monotonic() + wait_ms / 1000.0
    while True:
        try:
            return hold_for_writing(folder)
        except AlreadyRunning:
            if migrating(folder) or time.monotonic() >= end:
                raise
        time.sleep(TURN_POLL_SEC)


def older_beside_daemon(path: Path) -> bool:
    """Return whether a daemon holds the folder while the file is older than this version.

    The version is read through the write-ahead log: the file header may lag."""
    if not is_file(path) or not is_held(path.parent, LOCK_NAME):
        return False
    version = live_version(path)
    return version is not None and version < SCHEMA_VERSION
