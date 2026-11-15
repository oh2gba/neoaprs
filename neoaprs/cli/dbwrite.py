"""Whether `neoaprs db` may open the database now, beside the other NeoAPRS that use the data folder: no command while a migration runs (its note `neoaprs.migrating` is fresh: a read would find
the version before, a write would migrate the file beside it), and for a write (`set`) the folder's migration lock (`neoaprs.migrate.lock`) held from before the open, which may migrate the file, to
after the close (migrations.hold_for_writing): a restore beside it is refused, and a second write waits its turn, as long as it would wait for SQLite's write lock (a migration is not waited for). A
write is also refused while a daemon holds the folder and the file is of an older version than this NeoAPRS: a daemon of the version before, whose statements a migration made here would break until it
is restarted, or one of this version that has just started and is about to bring the file up to date."""
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from neoaprs.instancelock import LOCK_NAME, AlreadyRunning, InstanceLock, is_held
from neoaprs.migrations import SCHEMA_VERSION, hold_for_writing, let_go
from neoaprs.stopfile import migrating
from neoaprs.supportsql import live_version

MIGRATING = "NeoAPRS is bringing it up to date now (a large file takes minutes); try again when that is done"
WRITING = "another `neoaprs db` command is writing it now; try again when that is done"
BEFORE = ("NeoAPRS is running with this folder and the database is not up to date yet: if it has just started, it is bringing it up to date, so try again in a minute; if it is the version "
          "before, stop it (`neoaprs stop`), and the new one brings it up to date at its start")
TURN_POLL_SEC = 0.05            # how often a write tries the lock again while another write holds it


@contextmanager
def held(path: Path, writing: bool, wait_ms: int) -> Iterator[str]:
    """For the command on the database `path`: "" while it may go on (for a write, with the lock held until the end of the block), or the sentence of its refusal, with nothing held. `wait_ms`: how
    long a write waits for another that holds the lock (`_turn`)."""
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
    """The lock of `hold_for_writing`, tried again while another NeoAPRS holds it and no migration runs (a second `db set`, which ends in a moment; a restore), for at most `wait_ms`. Raises
    AlreadyRunning past that, or at once when the note of a migration is fresh: a tool does not wait for a migration."""
    end = time.monotonic() + wait_ms / 1000.0
    while True:
        try:
            return hold_for_writing(folder)
        except AlreadyRunning:
            if migrating(folder) or time.monotonic() >= end:
                raise
        time.sleep(TURN_POLL_SEC)


def older_beside_daemon(path: Path) -> bool:
    """Whether a daemon holds the data folder while the file is of an older version than this NeoAPRS. The version is SQLite's, through the write-ahead log (the file's header can be older than a
    migration that has not reached a checkpoint yet); a file that is not there or cannot be read says no (the open says what is wrong)."""
    if not path.is_file() or not is_held(path.parent, LOCK_NAME):
        return False
    version = live_version(path)
    return version is not None and version < SCHEMA_VERSION
