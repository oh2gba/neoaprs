"""The opening of the one database file and its migrations' runner: the file is versioned (SQLite's user_version) and brought up to date by the steps (migrationsteps*.py, listed in
MIGRATIONS below), one after the other; a file from
a newer NeoAPRS than this one is refused, not damaged. Before the first migration step that is going to run on a file that holds anything, the file is copied whole into backup/ next to it
(premigrate-v<from>-to-v<to>-<time>.sqlite, a name nothing removes); if that copy cannot be made, nothing is migrated. Every step that ran is written to the table
schema_history (version, name, a checksum of the function's source, the time). A migration that has been applied is never edited: a change is a new migration (the checksum of the
source of each step is pinned by tests/test_migrations.py; the steps keep the names and the annotations they were written with, which is why they name sqlite3 and not dberror.py's aliases).

This is run on the thread that calls it, before the database thread (db.py) opens the file for good, and by the tools that own a connection of their own; the statements of the daemon
are not made through it. The settings and the other rows are store.py's, through the database thread."""
import hashlib
import inspect
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .backupfolder import sweep
from .clock import Clock, from_unix, to_unix, utcnow
from .dberror import StoreError
from .dbfile import DEFAULT_BUSY_MS, configure, copy_database as _copy_database
from .migrationlog import log
from .migrationsteps12to21 import _v12, _v13, _v14, _v15, _v16, _v17, _v18, _v19, _v20, _v21
from .migrationsteps1to11 import _v1, _v2, _v3, _v4, _v5, _v6, _v7, _v8, _v9, _v10, _v11
from .migrationsteps22on import _v22, _v23


def source_hash(step: Callable[[sqlite3.Connection], None]) -> str:
    """sha256 of the source text of a migration function; "unknown" when the source is not to be had (compiled only)."""
    try:
        return hashlib.sha256(inspect.getsource(step).encode("utf-8")).hexdigest()
    except (OSError, TypeError):
        return "unknown"


# one function per version, in order: version N is reached by running MIGRATIONS[N - 1] on version N - 1
MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_v1, _v2, _v3, _v4, _v5, _v6, _v7, _v8, _v9, _v10, _v11, _v12, _v13, _v14, _v15, _v16, _v17, _v18, _v19, _v20, _v21, _v22, _v23]
SCHEMA_VERSION = len(MIGRATIONS)


def schema_version(db: sqlite3.Connection) -> int:
    return int(db.execute("PRAGMA user_version").fetchone()[0])


def open_database(path: str | Path, busy_ms: int = DEFAULT_BUSY_MS, clock: Clock = utcnow) -> tuple[sqlite3.Connection | None, str]:
    """The connection to the database file, brought up to date, and "" -- or None and the reason when the file cannot be opened or is of a newer version. ":memory:" for tests.
    `busy_ms`: how long a write waits for another writer; the daemon asks for a few seconds (it must not stand still), the tools for longer. This runs on the thread that calls
    it, before the database thread (db.py) opens the file for good, and in the tools; it is the migrations' own, the daemon's statements are not made through it.

    When a migration is going to run on a file that holds anything, the file is copied whole first (see `premigration_backup`); if the copy cannot be made, nothing is migrated and
    the file is as it was."""
    db: sqlite3.Connection | None = None
    try:
        db = sqlite3.connect(str(path), isolation_level=None, timeout=busy_ms / 1000.0)         # the transactions are ours: BEGIN and COMMIT where a write needs more than one statement
        version = schema_version(db)                        # first: nothing of a file is changed before it is known to be ours

        if version > SCHEMA_VERSION:
            db.close()
            return None, f"{path} is of version {version}, made by a newer NeoAPRS than this one (it knows {SCHEMA_VERSION}); not touched"

        configure(db, path, busy_ms)                        # WAL, synchronous=FULL, the busy time, the bound of the log, the file private (dbfile.py)

        if version < SCHEMA_VERSION and str(path) != ":memory:" and db.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is not None:
            copy = premigration_backup(db, Path(path), version, clock)
            log.info("the database %s is of version %d, this NeoAPRS needs %d: a copy of it is in %s", path, version, SCHEMA_VERSION, copy)

        for number in range(version + 1, SCHEMA_VERSION + 1):
            if _step(db, number, clock) and version:
                log.info("the database %s is now version %d (was %d)", path, number, number - 1)
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

    if str(path) != ":memory:":
        sweep(Path(path).absolute().parent / "backup", clock().timestamp())      # the temporary files of a copy that a kill ended before this start
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


def premigration_backup(db: sqlite3.Connection, path: Path, version: int, clock: Clock) -> Path:
    """The file as it is, whole, in backup/ next to it: premigrate-v<from>-to-v<to>-<time>.sqlite. Nothing removes it:
    it stays until somebody removes it. Raises StoreError when it cannot be made, and the caller migrates nothing."""
    folder = path.absolute().parent / "backup"
    stem = f"premigrate-v{version}-to-v{SCHEMA_VERSION}-{clock():%Y%m%d-%H%M%S}"
    dest = folder / f"{stem}.sqlite"
    n = 1
    while dest.exists():
        n += 1
        dest = folder / f"{stem}-{n}.sqlite"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _copy_database(db, dest)
    except (sqlite3.Error, OSError) as e:
        raise StoreError(f"the copy of the database before the migration could not be made ({e}); nothing was changed") from e
    return dest


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
