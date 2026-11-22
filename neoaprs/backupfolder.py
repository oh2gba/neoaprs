"""The folder of database copies, data/backup: leftovers, migration copies and restoring.

A copy is written as `<name>.tmp` and renamed when whole; a migration stands on one copy, the
database as the previous version left it. Files put there by hand are never touched.
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
from .stopfile import MIGRATE_LOCK_NAME

# a copy's temporary file and its SQLite journal
LITTER = re.compile(r"^[^/]+\.sqlite\.tmp(-journal)?$")
# Groups: old version, new version.
PREMIGRATION = re.compile(r"^premigrate-v(\d+)-to-v(\d+)-\d{8}-\d{6}(-\d+)?\.sqlite$")
# Group 1: time of the migration (UTC).
STAMPED = re.compile(r"^premigrate-v\d+-to-v\d+-(\d{8}-\d{6})(-\d+)?\.sqlite$")
# A copy being written changes constantly; a file still this long is dead.
LITTER_AGE_SEC = 300


def sweep(folder: Path, now: float) -> list[str]:
    """Remove temporary copy files unchanged for LITTER_AGE_SEC before `now`; return their names."""
    removed: list[str] = []
    try:
        names = os.listdir(folder)
    except OSError:
        return removed
    for name in sorted(names):
        path = folder / name
        try:
            if (
                LITTER.match(name)
                and path.is_file()
                and not path.is_symlink()
                and now - path.stat().st_mtime > LITTER_AGE_SEC
            ):
                path.unlink()
                removed.append(name)
        except OSError:
            continue
    return removed


def litter(folder: Path) -> dict[Path, tuple[int, int]]:
    """Return the temporary copy files in `folder` with their (mtime in ns, size), for
    `drop_still`."""
    found: dict[Path, tuple[int, int]] = {}
    try:
        names = os.listdir(folder)
    except OSError:
        return found
    for name in names:
        path = folder / name
        try:
            if LITTER.match(name) and path.is_file() and not path.is_symlink():
                info = path.stat()
                found[path] = (info.st_mtime_ns, info.st_size)
        except OSError:
            continue
    return found


def litter_wait(seen: dict[Path, tuple[int, int]], now: float) -> float:
    """Return how long to wait until the files in `seen` are known dead (at most LITTER_AGE_SEC + 1).

    A file with an mtime ahead of `now` counts as brand new."""
    ages = [min(max(now - mtime / 1e9, 0.0), LITTER_AGE_SEC) for mtime, _ in seen.values()]
    return LITTER_AGE_SEC - min(ages) + 1.0 if ages else 0.0


def drop_still(seen: dict[Path, tuple[int, int]]) -> list[str]:
    """Remove the files in `seen` that have not changed since; return their names."""
    removed: list[str] = []
    for path, state in seen.items():
        try:
            info = path.stat()
            if (info.st_mtime_ns, info.st_size) == state:
                path.unlink()
                removed.append(path.name)
        except OSError:
            continue
    return removed


def drop_older_copies(folder: Path, keep: str) -> list[str]:
    """Remove every pre-migration copy except `keep`; return the names removed.

    Nothing is removed if `keep` is not whole; whole copies a longer migration started from stay."""
    taken = taken_copies(folder)
    kept = next((t for t in taken if t.path.name == keep), None)
    if kept is None or not whole(kept.path, kept.old):
        return []
    removed: list[str] = []
    for t in taken:
        try:
            if t is not kept and not (t.old < kept.old < t.new and whole(t.path, t.old)):
                t.path.unlink()
                removed.append(t.path.name)
        except OSError:
            continue
    return removed


@dataclass(frozen=True)
class Taken:
    """A pre-migration copy as its name says: version before, version after, and time taken."""

    path: Path
    old: int
    new: int
    made: datetime


def taken_copies(folder: Path) -> list[Taken]:
    """Return the pre-migration copies (premigrate-v<old>-to-v<new>-<time>.sqlite), newest first.

    Judged by name only, ordered by the time and counter in it."""
    found: list[Taken] = []
    try:
        names = os.listdir(folder)
    except OSError:
        return found
    for name in names:
        match = PREMIGRATION.match(name)
        path = folder / name
        try:
            if match is not None and path.is_file() and not path.is_symlink():
                found.append(Taken(path, int(match.group(1)), int(match.group(2)), made_at(name, path.stat().st_mtime)))
        except OSError:
            continue
    return sorted(found, key=lambda t: (t.made, same_second(t.path.name)), reverse=True)


def whole(path: Path, version: int) -> bool:
    """Return whether the file is a whole database at `version`, judged from its header.

    The size must match the page count, and no journal or WAL may be beside it."""
    try:
        with open(path, "rb") as f:
            head = f.read(HEADER_BYTES)
        size = path.stat().st_size
        beside = any(path.with_name(path.name + suffix).exists() for suffix in ("-journal", "-wal"))
    except OSError:
        return False
    if (
        len(head) < HEADER_BYTES
        or not head.startswith(SQLITE_MAGIC)
        or beside
        or struct.unpack(">I", head[60:64])[0] != version
    ):
        return False
    page = int(struct.unpack(">H", head[16:18])[0])
    page = 65536 if page == 1 else page
    if page < 512 or page & (page - 1):
        return False
    count = int(struct.unpack(">I", head[28:32])[0])
    if head[92:96] == head[24:28] and count > 0:
        return size == count * page
    return size >= page and size % page == 0


def cut_short(folder: Path, found: int) -> list[Taken]:
    """Return the whole copies of older versions taken by a migration that went above `found`.

    Oldest version first, newest first within a version."""
    return sorted(
        (t for t in taken_copies(folder) if t.old < found < t.new and whole(t.path, t.old)), key=lambda t: t.old
    )


def before_copy(folder: Path) -> Taken | None:
    """Return the copy the latest migration stands on (oldest old version, highest new), or None."""
    found = [t for t in taken_copies(folder) if whole(t.path, t.old)]
    top = max((t.new for t in found), default=None)
    return next(iter(sorted((t for t in found if t.new == top), key=lambda t: t.old)), None)


def same_copies(folder: Path, found: int, new: int) -> list[Taken]:
    """Return the whole copies of a file at `found` taken for a migration to `new`, newest first."""
    return [t for t in taken_copies(folder) if t.old == found and t.new == new and whole(t.path, found)]


CHUNK_BYTES = 1024 * 1024
BOOKKEEPING = (slice(18, 20), slice(24, 28), slice(40, 44), slice(92, 100))


def _blank(head: bytearray) -> bytearray:
    for field in BOOKKEEPING:
        head[field] = bytes(len(head[field]))
    return head


def same_bytes(database: Path, copy: Path) -> bool:
    """Return whether the database and the copy are byte-equal apart from the header bookkeeping.

    The caller must have checkpointed the log first."""
    try:
        if database.stat().st_size != copy.stat().st_size:
            return False
        with open(database, "rb") as a, open(copy, "rb") as b:
            x, y = _blank(bytearray(a.read(CHUNK_BYTES))), _blank(bytearray(b.read(CHUNK_BYTES)))
            while x == y and x:
                x, y = bytearray(a.read(CHUNK_BYTES)), bytearray(b.read(CHUNK_BYTES))
            return x == y
    except OSError:
        return False


SQLITE_MAGIC = b"SQLite format 3\x00"
HEADER_BYTES = 100
# the database file and its WAL and shared-memory files
SIDECARS = ("", "-wal", "-shm")
FOLDER_NAME = "backup"


@dataclass(frozen=True)
class Copy:
    name: str
    path: Path
    version: int  # schema version of the file
    size: int
    made: datetime


class RestoreRefused(Exception):
    """A restore that was refused; the message is for the operator and nothing was changed."""


def file_version(path: Path) -> int | None:
    """Return the schema version from the file header, or None if it is not a SQLite file."""
    try:
        with open(path, "rb") as f:
            head = f.read(HEADER_BYTES)
    except OSError:
        return None
    if len(head) < HEADER_BYTES or not head.startswith(SQLITE_MAGIC):
        return None
    return int(struct.unpack(">I", head[60:64])[0])


def made_at(name: str, mtime: float) -> datetime:
    """Return when a copy was made: the time in its name, else its mtime."""
    m = STAMPED.match(name)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            pass
    return from_unix(mtime)


def copies(folder: Path) -> list[Copy]:
    """Return the database files (`*.sqlite`) in `folder`, newest first; others are skipped."""
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
    """Return the counter after the time in a copy's name (`-2`, `-3`, ...); 1 if there is none."""
    m = STAMPED.match(name)
    return int(m.group(2)[1:]) if m and m.group(2) else 1


def can_open(copy: Copy, knows: int) -> bool:
    """Return whether a program knowing schema versions up to `knows` can open the copy."""
    return 1 <= copy.version <= knows


def newest_usable(folder: Path, knows: int) -> Copy | None:
    return next((c for c in copies(folder) if can_open(c, knows)), None)


def stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M UTC")


def quoted(word: str) -> str:
    """Return `word` quoted for this platform's shell."""
    return subprocess.list2cmdline([word]) if sys.platform == "win32" else shlex.quote(word)


def way_back(data_dir: Path, knows: int) -> str:
    """Return a sentence naming the newest usable copy and the command to restore it."""
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
    """Take the data folder's locks; raise RestoreRefused if one is held."""
    held: list[InstanceLock] = []
    for name in (LOCK_NAME, APP_LOCK_NAME, MIGRATE_LOCK_NAME):
        lock = InstanceLock(data_dir, name)
        try:
            lock.acquire()
        except (AlreadyRunning, OSError) as e:
            _release(held)
            if isinstance(e, AlreadyRunning) and name == MIGRATE_LOCK_NAME:
                raise RestoreRefused(
                    "NeoAPRS is writing to the database or bringing it up to date now: try again when that is done"
                ) from e
            if isinstance(e, AlreadyRunning):
                raise RestoreRefused(
                    f"NeoAPRS is running with the data folder {data_dir}: stop it first (`neoaprs stop`)"
                ) from e
            raise RestoreRefused(f"the data folder {data_dir} cannot be used: {e.strerror or e}") from e
        held.append(lock)
    return held


def _release(locks: list[InstanceLock]) -> None:
    for lock in locks:
        lock.release()


def restore(data_dir: Path, db_name: str, name: str, knows: int, clock: Clock = utcnow) -> tuple[Copy, Path | None]:
    """Replace the database `db_name` with the copy `name` of backup/, setting the old one aside.

    Return the copy and the set-aside path (None if none). Raise RestoreRefused, changing nothing."""
    if Path(name).name != name or not name.endswith(".sqlite"):
        raise RestoreRefused(f"{name} is not the name of a copy in the backup folder (`neoaprs db restore` lists them)")
    copy = next((c for c in copies(data_dir / FOLDER_NAME) if c.name == name), None)
    if copy is None:
        raise RestoreRefused(f"there is no database copy {name} in the backup folder (`neoaprs db restore` lists them)")
    if not can_open(copy, knows):
        raise RestoreRefused(
            f"{name} is of version {copy.version}, which this NeoAPRS cannot open (it knows {knows}): choose another copy, or use the NeoAPRS that made it"
        )
    locks = _hold(data_dir)
    try:
        return copy, _put_in_place(data_dir, db_name, copy, clock)
    finally:
        _release(locks)


def _put_in_place(data_dir: Path, db_name: str, copy: Copy, clock: Clock) -> Path | None:
    """Write the copy as `.tmp`, set the database aside, rename the copy; a crash leaves one of them."""
    target = data_dir / db_name
    tmp = target.with_name(target.name + ".tmp")
    try:
        _write_private(copy.path, tmp)
    except OSError as e:
        raise RestoreRefused(
            f"the copy could not be put in place ({e.strerror or e}); the database is as it was"
        ) from e
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
        raise RestoreRefused(
            f"the copy could not be put in place ({e.strerror or e}); the database is as it was"
        ) from e
    fsync_dir(target.parent)
    return data_dir / f"{stem}.sqlite" if moved else None


def _write_private(source: Path, path: Path) -> None:
    """Copy `source` to the new file `path` with mode 0600 and sync it; remove it on failure."""
    path.unlink(missing_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with open(source, "rb") as src, os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(src, out)
        fsync_file(path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
