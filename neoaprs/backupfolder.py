"""The folder of copies of the database, data/backup: what a copy that did not end leaves behind, and the way back to a copy.

A copy is written under a temporary name (`<name>.tmp`, with SQLite's `-journal` beside it while it is written) and renamed when it is whole (dbfile.copy_database). A process killed
in between (SIGKILL, the OOM killer, a power cut) leaves the temporary file, up to the size of the database, and nothing else removes it.
"""
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .clock import Clock, from_unix, utcnow
from .durable import fsync_dir, fsync_file
from .instancelock import APP_LOCK_NAME, LOCK_NAME, AlreadyRunning, InstanceLock
from .paths import default_data_dir

LITTER = re.compile(r"^[^/]+\.sqlite\.tmp(-journal)?$")      # the temporary file of a copy, and the journal SQLite keeps beside it while it is written
PREMIGRATION = re.compile(r"^premigrate-v\d+-to-v\d+-\d{8}-\d{6}(-\d+)?\.sqlite$")        # the copy taken before a migration (migrations.premigration_backup)
STAMPED = re.compile(r"^premigrate-v\d+-to-v\d+-(\d{8}-\d{6})(-\d+)?\.sqlite$")     # the same name, with the time of the migration (UTC) in the first group
LITTER_AGE_SEC = 300                                          # a copy that is being written changes its file all the time: what has been still this long is dead


def sweep(folder: Path, now: float) -> list[str]:
    """Removes the temporary files (`*.sqlite.tmp`, `*.sqlite.tmp-journal`) of copies that did not end: those whose last change is more than LITTER_AGE_SEC before `now`, so that a
    copy being written at this moment (the one taken before a migration, by the daemon or by a tool that opens the file) is never touched. Nothing else in the folder is looked at. Returns the names removed."""
    removed: list[str] = []
    try:
        names = os.listdir(folder)
    except OSError:
        return removed
    for name in sorted(names):
        path = folder / name
        try:
            if LITTER.match(name) and path.is_file() and not path.is_symlink() and now - path.stat().st_mtime > LITTER_AGE_SEC:
                path.unlink()
                removed.append(name)
        except OSError:
            continue
    return removed


def drop_older_copies(folder: Path, keep: str) -> list[str]:
    """Removes the copies taken before earlier migrations, all but the file named `keep` (the one just made whole): the folder holds the latest. Nothing else in the folder is looked at,
    so a copy somebody made by hand stays. Returns the names removed; a file that cannot be removed is left."""
    removed: list[str] = []
    try:
        names = os.listdir(folder)
    except OSError:
        return removed
    for name in sorted(names):
        path = folder / name
        try:
            if name != keep and PREMIGRATION.match(name) and path.is_file() and not path.is_symlink():
                path.unlink()
                removed.append(name)
        except OSError:
            continue
    return removed


SQLITE_MAGIC = b"SQLite format 3\x00"
HEADER_BYTES = 100                                            # the header of a SQLite file: its magic at the start and the user_version (the schema version) at byte 60
SIDECARS = ("", "-wal", "-shm")                               # the database file and the two files SQLite keeps beside it while it is open (or was left open by a crash)
FOLDER_NAME = "backup"


@dataclass(frozen=True)
class Copy:
    name: str
    path: Path
    version: int                                              # the schema version the file is at
    size: int
    made: datetime


class RestoreRefused(Exception):
    """A restore that was not done, with the reason, which is for the operator to read; nothing was changed."""


def file_version(path: Path) -> int | None:
    """The schema version a database file is at, read from its header without opening it as a database; None when it is not a SQLite file."""
    try:
        with open(path, "rb") as f:
            head = f.read(HEADER_BYTES)
    except OSError:
        return None
    if len(head) < HEADER_BYTES or not head.startswith(SQLITE_MAGIC):
        return None
    return int(struct.unpack(">I", head[60:64])[0])


def made_at(name: str, mtime: float) -> datetime:
    """When a copy was made: the time in the name of one the daemon took before a migration (it survives a folder copied or synced without its file times), else the file's last change."""
    m = STAMPED.match(name)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            pass
    return from_unix(mtime)


def copies(folder: Path) -> list[Copy]:
    """The database files in `folder` (every `*.sqlite`, the ones the daemon made before a migration and the ones somebody made by hand), the newest first. A file that is not a database is not a copy."""
    found: list[Copy] = []
    try:
        names = os.listdir(folder)
    except OSError:
        return found
    for name in names:
        path = folder / name
        try:
            if not name.endswith(".sqlite") or not path.is_file() or path.is_symlink():
                continue
            version = file_version(path)
            info = path.stat()
        except OSError:
            continue
        if version is not None:
            found.append(Copy(name, path, version, info.st_size, made_at(name, info.st_mtime)))
    return sorted(found, key=lambda c: (c.made, same_second(c.name), c.name), reverse=True)


def same_second(name: str) -> int:
    """The number a copy made in the same second as another has after its time (`-2`, `-3` ... in the order they were made; 1 for the first, which has none, and for a name of another form)."""
    m = STAMPED.match(name)
    return int(m.group(2)[1:]) if m and m.group(2) else 1


def can_open(copy: Copy, knows: int) -> bool:
    """Whether a NeoAPRS that knows schema versions up to `knows` opens the copy as it is: not one of a newer version, and not an empty file."""
    return 1 <= copy.version <= knows


def newest_usable(folder: Path, knows: int) -> Copy | None:
    return next((c for c in copies(folder) if can_open(c, knows)), None)


def stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M UTC")


def quoted(word: str) -> str:
    """`word` as one word of a command line of this system's shell."""
    return subprocess.list2cmdline([word]) if sys.platform == "win32" else shlex.quote(word)


def way_back(data_dir: Path, knows: int) -> str:
    """One sentence for the operator whose database is of a newer version than this NeoAPRS: the newest copy in backup/ that this one can open, with its date, and the command that puts it back; or that there is none."""
    copy = newest_usable(data_dir / FOLDER_NAME, knows)
    if copy is None:
        return "there is no copy in the backup folder that this NeoAPRS can open: use the NeoAPRS that made the file, or move the file away to start with an empty database (the file stays with you)"
    where = "" if data_dir == default_data_dir() else f" --data {quoted(str(data_dir))}"
    return f"the newest copy this NeoAPRS can open is {copy.name} of {stamp(copy.made)}: stop NeoAPRS and run `neoaprs db restore{where} {quoted(copy.name)}` to go back to it"


def _aside_stem(data_dir: Path, db_name: str, clock: Clock) -> str:
    base = f"{Path(db_name).stem}-set-aside-{clock():%Y%m%d-%H%M%S}"
    stem, n = base, 1
    while any((data_dir / f"{stem}.sqlite{suffix}").exists() for suffix in SIDECARS):
        n += 1
        stem = f"{base}-{n}"
    return stem


def _hold(data_dir: Path) -> list[InstanceLock]:
    """The locks of the data folder (the daemon's and the desktop app's), taken for the restore; RestoreRefused when either is held by a running NeoAPRS."""
    held: list[InstanceLock] = []
    for name in (LOCK_NAME, APP_LOCK_NAME):
        lock = InstanceLock(data_dir, name)
        try:
            lock.acquire()
        except (AlreadyRunning, OSError) as e:
            _release(held)
            if isinstance(e, AlreadyRunning):
                raise RestoreRefused(f"NeoAPRS is running with the data folder {data_dir}: stop it first (`neoaprs stop`)") from e
            raise RestoreRefused(f"the data folder {data_dir} cannot be used: {e.strerror or e}") from e
        held.append(lock)
    return held


def _release(locks: list[InstanceLock]) -> None:
    for lock in locks:
        lock.release()


def restore(data_dir: Path, db_name: str, name: str, knows: int, clock: Clock = utcnow) -> tuple[Copy, Path | None]:
    """Puts the copy `name` of backup/ in the place of the database `db_name` of `data_dir`. The file that is there (with the files SQLite keeps beside it) is set aside under a name that says when,
    in the data folder, and never deleted; the copy stays in backup/. Returns the copy and where the file was put aside (None when there was none). Raises RestoreRefused, with nothing changed, when
    a daemon holds the data folder, when the copy is not there, is not a database or is of a version this NeoAPRS (it knows up to `knows`) cannot open, and when the copy cannot be put in place."""
    if Path(name).name != name or not name.endswith(".sqlite"):
        raise RestoreRefused(f"{name} is not the name of a copy in the backup folder (`neoaprs db restore` lists them)")
    copy = next((c for c in copies(data_dir / FOLDER_NAME) if c.name == name), None)
    if copy is None:
        raise RestoreRefused(f"there is no database copy {name} in the backup folder (`neoaprs db restore` lists them)")
    if not can_open(copy, knows):
        raise RestoreRefused(f"{name} is of version {copy.version}, which this NeoAPRS cannot open (it knows {knows}): choose another copy, or use the NeoAPRS that made it")
    locks = _hold(data_dir)
    try:
        return copy, _put_in_place(data_dir, db_name, copy, clock)
    finally:
        _release(locks)


def _put_in_place(data_dir: Path, db_name: str, copy: Copy, clock: Clock) -> Path | None:
    """The copy is written whole beside the database first (`.tmp`, synced), and only then is the database set aside and the copy given its name: a process killed or a power cut on the way leaves the
    database where it was, or the copy in its place, never no database at all."""
    target = data_dir / db_name
    tmp = target.with_name(target.name + ".tmp")
    try:
        _write_private(copy.path, tmp)
    except OSError as e:
        raise RestoreRefused(f"the copy could not be put in place ({e.strerror or e}); the database is as it was") from e
    stem = _aside_stem(data_dir, db_name, clock)
    moved: list[tuple[Path, Path]] = []
    try:
        for suffix in SIDECARS:
            old = data_dir / f"{db_name}{suffix}"
            if old.exists():
                aside = data_dir / f"{stem}.sqlite{suffix}"
                old.rename(aside)
                moved.append((aside, old))
        tmp.replace(target)
    except OSError as e:
        for aside, old in reversed(moved):
            try:
                aside.rename(old)
            except OSError:
                pass
        tmp.unlink(missing_ok=True)
        raise RestoreRefused(f"the copy could not be put in place ({e.strerror or e}); the database is as it was") from e
    fsync_dir(target.parent)
    return data_dir / f"{stem}.sqlite" if moved else None


def _write_private(source: Path, path: Path) -> None:
    """`source` as the new file `path`, private from the first byte and synced to the disk; nothing of it is left when it cannot be written whole."""
    path.unlink(missing_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with open(source, "rb") as src, os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(src, out)
        fsync_file(path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
