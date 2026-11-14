"""The opening of the one database file and its migrations' runner: the file is versioned (SQLite's user_version) and brought up to date by the steps (migrationsteps*.py, listed in
MIGRATIONS below), one after the other; a file from
a newer NeoAPRS than this one is refused, not damaged. Before the first migration step that is going to run on a file that holds anything, the file is copied whole into backup/ next to it
(premigrate-v<from>-to-v<to>-<time>.sqlite), unless the copy this migration stands on is there already from a start that was cut short (backupfolder.py has the rule); once the whole migration has
succeeded every other copy taken before a migration is removed, so the folder holds that one: a migration that fails, or is cut short, removes none. If no copy stands and none can be made, or the
disk has no room for the migration, nothing is migrated. While a migration runs, the note `neoaprs.migrating` beside the file says so (stopfile.py). Every step that ran is written to the table
schema_history (version, name, a checksum of the function's source, the time). A migration that has been applied is never edited: a change is a new migration (the checksum of the
source of each step is pinned by tests/test_migrations.py; the steps keep the names and the annotations they were written with, which is why they name sqlite3 and not dberror.py's aliases).

This is run on the thread that calls it, before the database thread (db.py) opens the file for good, and by the tools that own a connection of their own; the statements of the daemon
are not made through it. The settings and the other rows are store.py's, through the database thread."""
import hashlib
import inspect
import shutil
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .backupfolder import cut_short, drop_older_copies, drop_still, file_version, litter, litter_wait, same_bytes, same_copies, same_second, sweep, taken_copies, way_back, whole
from .clock import Clock, from_unix, to_unix, utcnow
from .dberror import StoreError
from .dbfile import DEFAULT_BUSY_MS, configure, copy_database as _copy_database
from .migrationlog import log
from .migrationsteps12to21 import _v12, _v13, _v14, _v15, _v16, _v17, _v18, _v19, _v20, _v21
from .migrationsteps1to11 import _v1, _v2, _v3, _v4, _v5, _v6, _v7, _v8, _v9, _v10, _v11
from .migrationsteps22on import _v22, _v23, _v24, _v25, _v26, _v27, _v28, _v29, _v30
from .migrationsteps31 import _v31
from .migrationsteps32 import _v32, _v33
from .stopfile import MigratingNote, clear_stale_migrating, migrating


def source_hash(step: Callable[[sqlite3.Connection], None]) -> str:
    """sha256 of the source text of a migration function; "unknown" when the source is not to be had (compiled only)."""
    try:
        return hashlib.sha256(inspect.getsource(step).encode("utf-8")).hexdigest()
    except (OSError, TypeError):
        return "unknown"


# one function per version, in order: version N is reached by running MIGRATIONS[N - 1] on version N - 1
MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_v1, _v2, _v3, _v4, _v5, _v6, _v7, _v8, _v9, _v10, _v11, _v12, _v13, _v14, _v15, _v16, _v17, _v18, _v19, _v20, _v21, _v22, _v23, _v24, _v25, _v26, _v27, _v28, _v29, _v30, _v31, _v32, _v33]
SCHEMA_VERSION = len(MIGRATIONS)
MIB = 1024 * 1024
REWRITE_BELOW = 32                                   # a file below this version has migration 32 before it, which writes the packet table again where it lies: until that step is committed the write-ahead log holds the table once more (0.92 of a gigabyte's file, measured)
COPY_MARGIN_BYTES = 8 * MIB                          # what the disk needs beyond the size of the database for its copy (the journal of the copy, the folder's entry)


def schema_version(db: sqlite3.Connection) -> int:
    return int(db.execute("PRAGMA user_version").fetchone()[0])


def open_database(path: str | Path, busy_ms: int = DEFAULT_BUSY_MS, clock: Clock = utcnow) -> tuple[sqlite3.Connection | None, str]:
    """The connection to the database file, brought up to date, and "" -- or None and the reason when the file cannot be opened or is of a newer version. ":memory:" for tests.
    `busy_ms`: how long a write waits for another writer; the daemon asks for a few seconds (it must not stand still), the tools for longer. This runs on the thread that calls
    it, before the database thread (db.py) opens the file for good, and in the tools; it is the migrations' own, the daemon's statements are not made through it.

    When a migration is going to run on a file that holds anything, the file is copied whole first, unless a copy it stands on is there already (see `_copy_first`); if no copy stands and
    none can be made, nothing is migrated and the file is as it was."""
    db: sqlite3.Connection | None = None
    note = MigratingNote(Path(path).absolute().parent)      # (written only while a migration runs: what waits for the daemon waits as long as the note is fresh)
    try:
        db = sqlite3.connect(str(path), isolation_level=None, timeout=busy_ms / 1000.0)         # the transactions are ours: BEGIN and COMMIT where a write needs more than one statement
        version = schema_version(db)                        # first: nothing of a file is changed before it is known to be ours

        if version > SCHEMA_VERSION:
            db.close()
            return None, f"{path} is of version {version}, made by a newer NeoAPRS than this one (it knows {SCHEMA_VERSION}); not touched; {way_back(Path(path).absolute().parent, SCHEMA_VERSION)}"

        configure(db, path, busy_ms)                        # WAL, synchronous=FULL, the busy time, the bound of the log, the file private (dbfile.py)

        copy = _copy_first(db, path, version, clock, note)

        for number in range(version + 1, SCHEMA_VERSION + 1):
            if _step(db, number, clock) and version:
                log.info("the database %s is now version %d (was %d)", path, number, number - 1)
        if copy is not None:
            drop_older_copies(copy.parent, copy.name)        # (only now, every step in: a migration that fails or is cut short keeps every copy; a start killed after the last step, before or while they are removed, leaves some to the next migration)
        for problem in _history_problems(db):
            log.warning("%s: %s", path, problem)
    except sqlite3.Error as e:
        return _refused(db, str(e))
    except (OSError, StoreError) as e:
        log.error("the database %s was not migrated: %s", path, e)
        return _refused(db, f"the database {path} was not migrated, and is as it was: {e}")
    except Exception as e:
        # whatever else a step raises (a corrupt row ...) is a refusal with a reason, and the daemon ends with 2 (the unit does not restart that). A raw exception
        # out of here would end it with 1, which the unit restarts every five seconds, and each start would make another full copy of the file
        log.error("the database %s was not migrated: %s: %s", path, type(e).__name__, e)
        return _refused(db, f"the database {path} was not migrated: {type(e).__name__}: {e} (the step that failed is rolled back; the copy taken before it is in backup/)")
    finally:
        note.stop()

    if str(path) != ":memory:":
        sweep(Path(path).absolute().parent / "backup", clock().timestamp())      # the temporary files of a copy that a kill ended before this start
        clear_stale_migrating(Path(path).absolute().parent)                     # and the note of a migration a kill ended, which no migration of this start replaced
    return db, ""


def _refused(db: sqlite3.Connection | None, why: str) -> tuple[None, str]:
    """The file is not ours to use: the connection is closed and the reason is the answer of open_database()."""
    if db is not None:
        db.close()
    return None, why


def _step(db: sqlite3.Connection, number: int, clock: Clock) -> bool:
    """Migration `number` in a transaction of its own, with its row in the history: all of it or none. False when another process (the daemon, neoaprs-db) got there first."""
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
    """Before the first step on a file that holds anything: the note that a migration runs, and the copy the migration stands on (backupfolder.py says the rule), made now or found from a start
    that was cut short; None when no step is to run or the file is empty. Raises StoreError when no copy stands and none can be made, or the disk has no room for the migration."""
    if version >= SCHEMA_VERSION or str(path) == ":memory:" or db.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is None:
        return None
    if not migrating(Path(path).absolute().parent):
        drop_still(litter(Path(path).absolute().parent / "backup"))      # (no other NeoAPRS migrates the file now, each keeps the note fresh from before its copy to its end: a copy's temporary file is dead)
    note.start()
    log.info("the database %s is of version %d, this NeoAPRS needs %d: it is brought up to date now (a large file takes minutes)", path, version, SCHEMA_VERSION)
    while version < SCHEMA_VERSION:
        standing = _standing_copy(db, Path(path), version)
        if standing is not None:
            _room(db, standing.parent, version, copy=False)
            why = "taken by a start that did not get through" if file_version(standing) != version else "and the file has not changed since it was taken"     # (the same: a start cut short before its first step, or the copy put back by `neoaprs db restore`)
            log.info("the database %s: the copy of it from before this migration is %s, %s; no other is made", path, standing, why)
            return standing
        try:
            copy = premigration_backup(db, Path(path), version, clock)
        except _Moved as moved:                             # (another NeoAPRS, a tool, migrated the file since it was read: what it left is looked at again)
            log.info("the database %s was brought to version %d by another NeoAPRS meanwhile", path, moved.version)
            version = moved.version
            continue
        log.info("the database %s: a copy of it is in %s", path, copy)
        return copy
    if version > SCHEMA_VERSION:
        raise StoreError(f"the database {path} was brought to version {version} by a newer NeoAPRS meanwhile; not touched")
    return None


class _Moved(Exception):
    """The file is at another version than it was read at: another process migrated it meanwhile."""

    def __init__(self, version: int) -> None:
        super().__init__(version)
        self.version = version


def _standing_copy(db: sqlite3.Connection, path: Path, version: int) -> Path | None:
    """The copy in backup/ this migration stands on already, or None: the copy of a migration that was cut short at this version that the file came from (`_went_on_from`), else a whole copy of the
    file at this version for this migration that the file, its log written into it, still equals byte for byte."""
    folder = path.absolute().parent / "backup"
    for below in cut_short(folder, version):
        if _went_on_from(db, below.path, below.old):
            return below.path
    for same in same_copies(folder, version, SCHEMA_VERSION):
        if _checkpointed(db) and same_bytes(path.absolute(), same.path):
            return same.path
    return None


def _went_on_from(db: sqlite3.Connection, copy: Path, old: int) -> bool:
    """Whether the file was migrated on from the copy (at version `old`): the copy's history is the file's up to `old`, row for row (each step's version, checksum and the time it was applied, which
    a copy keeps as it was), and the file has step `old` + 1. Read from both files; no clock decides it (one that went back after the copy was taken would)."""
    try:
        mine = [(int(v), str(h), int(t)) for v, h, t in db.execute("SELECT version, sha256, applied FROM schema_history WHERE version <= ? ORDER BY version", (old + 1,))]
        theirs = _history_of(copy)
    except sqlite3.Error:
        return False
    return bool(theirs) and len(mine) == len(theirs) + 1 and mine[:-1] == theirs and mine[-1][0] == old + 1


def _history_of(copy: Path) -> list[tuple[int, str, int]]:
    """(version, sha256, applied) of every step in a copy's schema_history, opened only to be read (immutable: nothing is written beside it)."""
    other = sqlite3.connect(f"{copy.absolute().as_uri()}?mode=ro&immutable=1", uri=True)
    try:
        return [(int(v), str(h), int(t)) for v, h, t in other.execute("SELECT version, sha256, applied FROM schema_history ORDER BY version")]
    finally:
        other.close()


def _checkpointed(db: sqlite3.Connection) -> bool:
    """The write-ahead log written whole into the database file (and cut to nothing), so that the file holds what the database does; False when another connection keeps that from being done."""
    try:
        return int(db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]) == 0
    except sqlite3.Error:
        return False


def premigration_backup(db: sqlite3.Connection, path: Path, version: int, clock: Clock) -> Path:
    """The file as it is, whole, in backup/ next to it: premigrate-v<from>-to-v<to>-<time>.sqlite. The copies of earlier migrations are left to the caller to remove once the whole migration has
    succeeded (`drop_older_copies`): a failed copy, or a failed step, leaves them. Raises StoreError when it cannot be made or the disk has no room for it, and the caller migrates nothing."""
    folder = path.absolute().parent / "backup"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        sweep(folder, clock().timestamp())                  # (the temporary file of a copy an earlier start did not end takes room: gone before the room is counted, once it is old enough to be dead)
        _room(db, folder, version, copy=True)
        dest = _copy_name(folder, version, clock)
        db.execute("BEGIN")                                 # one read for the version and the copy: the copy is the file at `version` page for page, whatever another process writes meanwhile
        try:
            if (now := schema_version(db)) != version:
                raise _Moved(now)
            _copy_database(db, dest)
        finally:
            db.commit()                                     # (only read: the read ends)
        if not whole(dest, version):
            dest.unlink(missing_ok=True)
            raise sqlite3.DatabaseError(f"the copy is not the file at version {version}")
    except (sqlite3.Error, OSError) as e:
        raise StoreError(f"the copy of the database before the migration could not be made ({e}); nothing was changed") from e
    return dest


def _copy_name(folder: Path, version: int, clock: Clock) -> Path:
    """The name of a new copy of the file at `version` for this migration: premigrate-v<from>-to-v<to>-<time>.sqlite, with a number after the time for a second in the same second, and after every
    copy of the same migration there is (taken with the time of the newest and the next number when the clock is not past it: it went back), so that the newest by name is the one taken last. Never the
    name of a copy that is being written (its `.tmp`)."""
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


_sleep = time.sleep                                         # (the tests' to replace)


def _room(db: sqlite3.Connection, folder: Path, version: int, *, copy: bool) -> None:
    """`_require_room`; when it refuses and the temporary file of a copy an earlier start did not end is in backup/ (a kill while the copy was written, and the restart a few seconds later), once more
    after that file has been still long enough to be dead and is removed. A file somebody writes meanwhile is left, and the refusal stands."""
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
    """Raises StoreError when `folder`'s disk has less free than the migration from `version` needs, naming what to free: the copy (the database's size and a margin), and the database's size once more
    for a file that migration 32 has yet to rewrite (its write-ahead log; the log lies beside the database and the copy in backup/ under it, one disk). `copy=False`: the copy stands in backup/
    already (a start that was cut short made it), and only the log and the margin are counted."""
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
    """The step that has just run, into schema_history (the first step makes the table, so every step has its row)."""
    step = MIGRATIONS[number - 1]
    db.execute("INSERT INTO schema_history (version, name, sha256, applied) VALUES (?, ?, ?, ?)", (number, step.__name__, source_hash(step), to_unix(clock())))


def history(db: sqlite3.Connection) -> list[tuple[int, str, str, datetime, str]]:
    """(version, name, sha256, applied, note) of every migration step that was applied, oldest first; empty for a file that predates the table."""
    try:
        return [(int(v), str(n), str(h), from_unix(int(t)), str(note)) for v, n, h, t, note
                in db.execute("SELECT version, name, sha256, applied, note FROM schema_history ORDER BY version")]
    except sqlite3.Error:
        return []


def _history_problems(db: sqlite3.Connection) -> list[str]:
    """What schema_history says that is not so: a step whose source is not what it was when it ran (an applied migration was edited), or a step
    the file recorded that this NeoAPRS does not have."""
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
