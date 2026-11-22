"""Open the database file and run its migrations.

A file of a newer NeoAPRS is refused. A non-empty file is copied whole into backup/ before the
first step. An applied migration is never edited: a change is a new migration."""
import hashlib
import inspect
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .backupfolder import cut_short, drop_older_copies, drop_still, file_version, litter, litter_wait, same_bytes, same_copies, same_second, sweep, taken_copies, way_back, whole
from .clock import Clock, from_unix, to_unix, utcnow
from .dberror import StoreError
from .dbfile import DEFAULT_BUSY_MS, configure, copy_database as _copy_database
from .instancelock import AlreadyRunning, InstanceLock
from .migrationlog import log
from .migrationsteps12to21 import _v12, _v13, _v14, _v15, _v16, _v17, _v18, _v19, _v20, _v21
from .migrationsteps1to11 import _v1, _v2, _v3, _v4, _v5, _v6, _v7, _v8, _v9, _v10, _v11
from .migrationsteps22on import _v22, _v23, _v24, _v25, _v26, _v27, _v28, _v29, _v30
from .migrationsteps31 import _v31
from .migrationsteps32 import _v32, _v33
from .migrationsteps34 import _v34
from .migrationsteps35 import _v35
from .stopfile import MIGRATE_LOCK_NAME, MigratingNote, clear_stale_migrating, migrating


def source_hash(step: Callable[[sqlite3.Connection], None]) -> str:
    """Return the sha256 of a migration function's source, or "unknown" if unavailable."""
    try:
        return hashlib.sha256(inspect.getsource(step).encode("utf-8")).hexdigest()
    except (OSError, TypeError):
        return "unknown"


# version N is reached by running MIGRATIONS[N - 1] on N - 1
MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_v1, _v2, _v3, _v4, _v5, _v6, _v7, _v8, _v9, _v10, _v11, _v12, _v13, _v14, _v15, _v16, _v17, _v18, _v19, _v20, _v21, _v22, _v23, _v24, _v25, _v26, _v27, _v28, _v29, _v30, _v31, _v32, _v33, _v34, _v35]
SCHEMA_VERSION = len(MIGRATIONS)
MIB = 1024 * 1024
# migration 32 rewrites the packet table, so the log holds it twice until it commits
REWRITE_BELOW = 32
COPY_MARGIN_BYTES = 8 * MIB  # disk needed beyond the database size


def schema_version(db: sqlite3.Connection) -> int:
    return int(db.execute("PRAGMA user_version").fetchone()[0])


def open_database(path: str | Path, busy_ms: int = DEFAULT_BUSY_MS, clock: Clock = utcnow) -> tuple[sqlite3.Connection | None, str]:
    """Return (connection, "") with the database up to date, or (None, reason).

    If the copy before a migration cannot be made, nothing is migrated."""
    db: sqlite3.Connection | None = None
    note = MigratingNote(Path(path).absolute().parent)  # written only while a migration runs
    lock: InstanceLock | None = None
    try:
        # isolation_level=None: transactions are explicit (BEGIN/COMMIT)
        db = sqlite3.connect(str(path), isolation_level=None, timeout=busy_ms / 1000.0)
        version = schema_version(db)  # read first: change nothing before it is known ours
        if _to_migrate(db, path, version):
            lock = _migration_lock(Path(path), busy_ms)  # waits for another migrator, then re-reads
            version = schema_version(db)

        if version > SCHEMA_VERSION:
            db.close()
            return None, f"{path} is of version {version}, made by a newer NeoAPRS than this one (it knows {SCHEMA_VERSION}); not touched; {way_back(Path(path).absolute().parent, SCHEMA_VERSION)}"

        configure(db, path, busy_ms)

        copy = _copy_first(db, path, version, clock, note)

        for number in range(version + 1, SCHEMA_VERSION + 1):
            if _step(db, number, clock) and version:
                log.info("the database %s is now version %d (was %d)", path, number, number - 1)
        if copy is not None:
            # only after every step: a failed or interrupted migration keeps every copy
            drop_older_copies(copy.parent, copy.name)
        for problem in _history_problems(db):
            log.warning("%s: %s", path, problem)
    except sqlite3.Error as e:
        return _refused(db, str(e))
    except (OSError, StoreError) as e:
        log.error("the database %s was not migrated: %s", path, e)
        return _refused(db, f"the database {path} was not migrated, and is as it was: {e}")
    except Exception as e:
        # a refusal makes the daemon exit with 2, which the service unit does not restart; a raw
        # exception would exit with 1 and loop, making a full copy each time
        log.error("the database %s was not migrated: %s: %s", path, type(e).__name__, e)
        return _refused(db, f"the database {path} was not migrated: {type(e).__name__}: {e} (the step that failed is rolled back; the copy taken before it is in backup/)")
    finally:
        note.stop()
        let_go(lock)  # after the note is gone: the next holder's note survives

    if str(path) != ":memory:":
        sweep(Path(path).absolute().parent / "backup", clock().timestamp())  # temp files of a killed copy
        clear_stale_migrating(Path(path).absolute().parent)  # note of a killed migration
    return db, ""


def _refused(db: sqlite3.Connection | None, why: str) -> tuple[None, str]:
    """Close the connection and return the refusal answer."""
    if db is not None:
        db.close()
    return None, why


def _to_migrate(db: sqlite3.Connection, path: str | Path, version: int) -> bool:
    """Return whether a migration with a copy must run: a non-empty file of an older version."""
    return version < SCHEMA_VERSION and str(path) != ":memory:" and db.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is not None


# longest wait for another NeoAPRS's migration; its note proves the process lives, not progress
MIGRATION_WAIT_SEC = 3600.0
WAIT_POLL_SEC = 0.25
_HELD_HERE: set[Path] = set()  # data folders whose migration lock this process holds
_HELD_GUARD = threading.Lock()


def _migration_lock(path: Path, busy_ms: int) -> InstanceLock | None:
    """Take the migration lock, waiting while the holder's note stays fresh.

    Raise StoreError if no fresh note shows or the wait runs out; None if already held here."""
    folder = path.absolute().parent
    lock = InstanceLock(folder, MIGRATE_LOCK_NAME)
    began = heard = time.monotonic()
    told = False
    while True:
        with _HELD_GUARD:
            if folder in _HELD_HERE:
                return None
            try:
                lock.acquire()
            except AlreadyRunning:
                pass
            except OSError:
                return None
            else:
                _HELD_HERE.add(folder)
                return lock
        now = time.monotonic()
        if migrating(folder):
            heard = now
            if not told:
                log.info("the database %s is being brought up to date by another NeoAPRS (a command, or a start beside this one): this one waits until that is done", path)
                told = True
        elif now - heard >= busy_ms / 1000.0:
            raise StoreError("another NeoAPRS has its migration in hand but shows no sign that it is still at it (stopped, or stuck); start this one again once that one has ended")
        if now - began >= MIGRATION_WAIT_SEC:
            raise StoreError(f"another NeoAPRS has been bringing it up to date for {_span(MIGRATION_WAIT_SEC)}, longer than a migration takes: this one waited no longer; "
                             "let that one end, or end it, and start again")
        _sleep(WAIT_POLL_SEC)


def hold_for_writing(folder: Path) -> InstanceLock | None:
    """Take the migration lock for a tool that writes the database outside the daemon.

    Raise AlreadyRunning if another NeoAPRS holds it; None if this process does."""
    folder = folder.absolute()
    lock = InstanceLock(folder, MIGRATE_LOCK_NAME)
    with _HELD_GUARD:
        if folder in _HELD_HERE:
            return None
        try:
            lock.acquire()
        except OSError:
            return None
        _HELD_HERE.add(folder)
    return lock


def let_go(lock: InstanceLock | None) -> None:
    if lock is not None:
        with _HELD_GUARD:
            _HELD_HERE.discard(lock.path.parent)
            lock.release()


def _span(seconds: float) -> str:
    return f"{round(seconds / 60)} minutes" if seconds >= 120 else f"{seconds:g} seconds"


def _step(db: sqlite3.Connection, number: int, clock: Clock) -> bool:
    """Run migration `number` and its history row in one transaction; False if already done."""
    db.execute("BEGIN IMMEDIATE")
    try:
        if schema_version(db) >= number:
            db.execute("ROLLBACK")
            return False
        MIGRATIONS[number - 1](db)
        db.execute(f"PRAGMA user_version = {number}")
        _record_step(db, number, clock)
        db.execute("COMMIT")
    except Exception:
        try:
            db.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    return True


def _copy_first(db: sqlite3.Connection, path: str | Path, version: int, clock: Clock, note: MigratingNote) -> Path | None:
    """Write the migrating note and return the copy the migration stands on; None if no step runs.

    Raise StoreError if no copy stands and none can be made."""
    if not _to_migrate(db, path, version):
        return None
    if not migrating(Path(path).absolute().parent):
        # nobody is migrating, so a temp copy file is dead
        drop_still(litter(Path(path).absolute().parent / "backup"))
    note.start()
    log.info("the database %s is of version %d, this NeoAPRS needs %d: it is brought up to date now (a large file takes minutes)", path, version, SCHEMA_VERSION)
    while version < SCHEMA_VERSION:
        standing = _standing_copy(db, Path(path), version)
        if standing is not None:
            _room(db, standing.parent, version, copy=False)
            why = "taken by a start that did not get through" if file_version(standing) != version else "and the file has not changed since it was taken"
            log.info("the database %s: the copy of it from before this migration is %s, %s; no other is made", path, standing, why)
            return standing
        try:
            copy = premigration_backup(db, Path(path), version, clock)
        except _Moved as moved:  # another process migrated the file since it was read
            log.info("the database %s was brought to version %d by another NeoAPRS meanwhile", path, moved.version)
            version = moved.version
            continue
        log.info("the database %s: a copy of it is in %s", path, copy)
        return copy
    if version > SCHEMA_VERSION:
        raise StoreError(f"the database {path} was brought to version {version} by a newer NeoAPRS meanwhile; not touched")
    return None


class _Moved(Exception):
    """Another process migrated the file since it was read."""

    def __init__(self, version: int) -> None:
        super().__init__(version)
        self.version = version


def _standing_copy(db: sqlite3.Connection, path: Path, version: int) -> Path | None:
    """Return the copy in backup/ this migration stands on (interrupted or identical), or None."""
    folder = path.absolute().parent / "backup"
    for below in cut_short(folder, version):
        if _went_on_from(db, below.path, below.old):
            return below.path
    for same in same_copies(folder, version, SCHEMA_VERSION):
        if _checkpointed(db) and same_bytes(path.absolute(), same.path):
            return same.path
    return None


def _went_on_from(db: sqlite3.Connection, copy: Path, old: int) -> bool:
    """Return whether the file was migrated on from the copy (at version `old`).

    The histories must match row for row; no clock is used, since a clock may step back."""
    try:
        mine = [(int(v), str(h), int(t)) for v, h, t in db.execute("SELECT version, sha256, applied FROM schema_history WHERE version <= ? ORDER BY version", (old + 1,))]
        theirs = _history_of(copy)
    except sqlite3.Error:
        return False
    return bool(theirs) and len(mine) == len(theirs) + 1 and mine[:-1] == theirs and mine[-1][0] == old + 1


def _history_of(copy: Path) -> list[tuple[int, str, int]]:
    """Return (version, sha256, applied) of each step in a copy's schema_history."""
    other = sqlite3.connect(f"{copy.absolute().as_uri()}?mode=ro&immutable=1", uri=True)
    try:
        return [(int(v), str(h), int(t)) for v, h, t in other.execute("SELECT version, sha256, applied FROM schema_history ORDER BY version")]
    finally:
        other.close()


def _checkpointed(db: sqlite3.Connection) -> bool:
    """Truncate the write-ahead log; False if another connection prevents it."""
    try:
        return int(db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]) == 0
    except sqlite3.Error:
        return False


def premigration_backup(db: sqlite3.Connection, path: Path, version: int, clock: Clock) -> Path:
    """Copy the file whole to backup/premigrate-v<from>-to-v<to>-<time>.sqlite; return the path.

    Raise StoreError if the copy cannot be made or the disk lacks room."""
    folder = path.absolute().parent / "backup"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        sweep(folder, clock().timestamp())  # a dead temp file takes room
        _room(db, folder, version, copy=True)
        dest = _copy_name(folder, version, clock)
        # one read transaction covers the version check and the copy
        db.execute("BEGIN")
        try:
            if (now := schema_version(db)) != version:
                raise _Moved(now)
            _copy_database(db, dest)
        finally:
            db.commit()  # read only: ends the read
        if not whole(dest, version):
            dest.unlink(missing_ok=True)
            raise sqlite3.DatabaseError(f"the copy is not the file at version {version}")
    except (sqlite3.Error, OSError) as e:
        raise StoreError(f"the copy of the database before the migration could not be made ({e}); nothing was changed") from e
    return dest


def _copy_name(folder: Path, version: int, clock: Clock) -> Path:
    """Return a new copy name, never one in use.

    A number follows the time if the clock is not past the newest copy."""
    when = clock().replace(microsecond=0)
    same = [t for t in taken_copies(folder) if t.old == version and t.new == SCHEMA_VERSION]
    n = 1
    if same and same[0].made >= when:
        when, n = same[0].made, same_second(same[0].path.name) + 1
    stem = f"premigrate-v{version}-to-v{SCHEMA_VERSION}-{when:%Y%m%d-%H%M%S}"
    while True:
        dest = folder / (f"{stem}.sqlite" if n == 1 else f"{stem}-{n}.sqlite")
        if not dest.exists() and not dest.with_name(dest.name + ".tmp").exists():
            return dest
        n += 1


_sleep = time.sleep  # replaced by tests


def _room(db: sqlite3.Connection, folder: Path, version: int, *, copy: bool) -> None:
    """Call `_require_room`; if it refuses and a dead temp copy exists, remove it and retry."""
    try:
        _require_room(db, folder, version, copy=copy)
    except StoreError:
        seen = litter(folder)
        if not seen:
            raise
        wait = litter_wait(seen, time.time())
        log.info("the disk of %s is short of room for the migration while the temporary file of a copy an earlier start did not end is there: it is removed in %d seconds, once it is known to be dead",
                 folder, round(wait))
        _sleep(wait)
        drop_still(seen)
        _require_room(db, folder, version, copy=copy)


def _require_room(db: sqlite3.Connection, folder: Path, version: int = SCHEMA_VERSION, *, copy: bool = True) -> None:
    """Raise StoreError if the disk has less free than the migration from `version` needs.

    With `copy=False` the copy already stands, so it is not counted."""
    size = int(db.execute("PRAGMA page_count").fetchone()[0]) * int(db.execute("PRAGMA page_size").fetchone()[0])
    need = size * ((1 if copy else 0) + (1 if version < REWRITE_BELOW else 0)) + COPY_MARGIN_BYTES
    free = shutil.disk_usage(folder).free
    if free < need:
        short = (need - free + MIB - 1) // MIB
        made = "for the copy of the database it makes first and for the database's log while it runs" if copy else "for the database's log while it runs"
        keep = "the copies in backup/ that are not wanted any more can go" if copy else "the copy in backup/ taken before this migration stays: it is the way back"
        raise StoreError(f"the disk of {folder} has {free // MIB} MB free and the migration needs {need // MIB} MB there {made}; free at least {short} MB there "
                         f"({keep}) and start again; nothing was changed")


def _record_step(db: sqlite3.Connection, number: int, clock: Clock) -> None:
    step = MIGRATIONS[number - 1]
    db.execute("INSERT INTO schema_history (version, name, sha256, applied) VALUES (?, ?, ?, ?)", (number, step.__name__, source_hash(step), to_unix(clock())))


def history(db: sqlite3.Connection) -> list[tuple[int, str, str, datetime, str]]:
    """Return (version, name, sha256, applied, note) per applied step."""
    try:
        return [(int(v), str(n), str(h), from_unix(int(t)), str(note)) for v, n, h, t, note
                in db.execute("SELECT version, name, sha256, applied, note FROM schema_history ORDER BY version")]
    except sqlite3.Error:
        return []


def _history_problems(db: sqlite3.Connection) -> list[str]:

    try:
        rows = db.execute("SELECT version, sha256 FROM schema_history ORDER BY version").fetchall()
    except sqlite3.Error:
        return []
    out: list[str] = []
    for version, digest in rows:
        if not 1 <= version <= len(MIGRATIONS):
            out.append(f"schema_history has a step {version} that this NeoAPRS does not know")
        elif digest != "unknown" and source_hash(MIGRATIONS[version - 1]) not in (digest, "unknown"):
            out.append(f"migration {version} ({MIGRATIONS[version - 1].__name__}) is not the code that was applied: its source has changed since")
    return out
