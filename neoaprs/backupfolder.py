"""The folder of copies of the database, data/backup: what a copy that did not end leaves behind, which copy a migration stands on, and the way back to a copy.

A copy is written under a temporary name (`<name>.tmp`, with SQLite's `-journal` beside it while it is written) and renamed when it is whole (dbfile.copy_database). A process killed
in between (SIGKILL, the OOM killer, a power cut) leaves the temporary file, up to the size of the database, and nothing else removes it.

The rule of the copies taken before a migration (migrations.open_database): a migration stands on one copy, the database as the NeoAPRS before left it. The first start of the migration makes it; a
start that finds the file at a middle version (an earlier start was cut short after a step) stands on that start's copy and makes none (`cut_short`; the file came from it when its history is the
copy's and the step after it, which no clock decides); a start that finds the file at the version of a whole copy taken for the same new version, and the file unchanged since, stands on that copy
and makes none (`same_copies`, `same_bytes`). A new copy of the same migration is named after every one there is, so the newest by name is the one taken last also when the clock went back. When the
migration has ended whole every other copy taken before a migration goes (`drop_older_copies`): backup/ holds that one copy, and the files somebody put there by hand, which are never touched.
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

LITTER = re.compile(r"^[^/]+\.sqlite\.tmp(-journal)?$")      # the temporary file of a copy, and the journal SQLite keeps beside it while it is written
PREMIGRATION = re.compile(r"^premigrate-v(\d+)-to-v(\d+)-\d{8}-\d{6}(-\d+)?\.sqlite$")   # the copy taken before a migration (migrations.premigration_backup), its version and the one it went to in the groups
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


def litter(folder: Path) -> dict[Path, tuple[int, int]]:
    """The temporary files of copies in `folder` as they are now (the time of their last change in nanoseconds, their size), to be looked at again later (`drop_still`)."""
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
    """How long to look at the temporary files `seen` before the still ones are known to be dead: until the youngest has been still LITTER_AGE_SEC, at most that long (a file whose time is ahead
    of `now`, written before the clock went back, is watched the whole time)."""
    ages = [min(max(now - mtime / 1e9, 0.0), LITTER_AGE_SEC) for mtime, _ in seen.values()]
    return LITTER_AGE_SEC - min(ages) + 1.0 if ages else 0.0


def drop_still(seen: dict[Path, tuple[int, int]]) -> list[str]:
    """Removes those of the temporary files `seen` that have not changed since they were seen (a copy being written changes its file all the time); returns their names."""
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
    """Removes every copy taken before a migration (by its name) but the file named `keep`, the one the migration that has just ended whole stood on: the copies of earlier migrations, and
    any an earlier program took at a middle version. Nothing else in the folder is looked at, so a copy somebody made by hand stays. Two are never removed: any copy when `keep` is not whole at the
    version its name says (it is not the file the migration began with), and a whole copy of a version older than `keep`'s taken by a migration that went past it (the file may have come from that
    one). Returns the names removed; a file that cannot be removed is left."""
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
    """A copy taken before a migration, as its name says: the version the file was at, the version that migration went to, and when it was taken."""
    path: Path
    old: int
    new: int
    made: datetime


def taken_copies(folder: Path) -> list[Taken]:
    """The copies taken before a migration (premigrate-v<old>-to-v<new>-<time>.sqlite, files and not links), by their names alone: whether one is whole is `whole`'s to say. The newest first (by the
    time in the name and the number after it; of one migration that is the order they were taken in, migrations.premigration_backup names them so)."""
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
    """Whether the file under the name of a copy is a whole database at `version`. A copy gets its name only once it is whole (written under `.tmp`, checked, synced, renamed: dbfile.copy_database), and
    a `.tmp` is never one; that it still is whole is read from its header, without opening it: SQLite's, at `version`, a page size SQLite writes, as long as its header says (or a whole number of pages
    where the header's count is not kept), with no journal or log of its own beside it (a file somebody is changing)."""
    try:
        with open(path, "rb") as f:
            head = f.read(HEADER_BYTES)
        size = path.stat().st_size
        beside = any(path.with_name(path.name + suffix).exists() for suffix in ("-journal", "-wal"))
    except OSError:
        return False
    if len(head) < HEADER_BYTES or not head.startswith(SQLITE_MAGIC) or beside or struct.unpack(">I", head[60:64])[0] != version:
        return False
    page = int(struct.unpack(">H", head[16:18])[0])
    page = 65536 if page == 1 else page
    if page < 512 or page & (page - 1):
        return False
    count = int(struct.unpack(">I", head[28:32])[0])
    if head[92:96] == head[24:28] and count > 0:          # (the count is kept when the number it is valid for is the file's change counter)
        return size == count * page
    return size >= page and size % page == 0


def cut_short(folder: Path, found: int) -> list[Taken]:
    """The copies a migration cut short may have left behind, for a start that finds the file at `found`: the whole copies of a file older than `found`, taken by a migration that went above it (it got
    as far as `found`), the oldest version first and of one version the newest first. The caller takes the first the file came from (its history is the copy's, and the step after it)."""
    return sorted((t for t in taken_copies(folder) if t.old < found < t.new and whole(t.path, t.old)), key=lambda t: t.old)


def before_copy(folder: Path) -> Taken | None:
    """The copy the NeoAPRS before this one opens: the one the latest migration stands on, which is the whole copy taken for the highest new version, of the oldest version among those (and the newest
    of that version). None when backup/ holds no whole copy taken before a migration."""
    found = [t for t in taken_copies(folder) if whole(t.path, t.old)]
    top = max((t.new for t in found), default=None)
    return next(iter(sorted((t for t in found if t.new == top), key=lambda t: t.old)), None)


def same_copies(folder: Path, found: int, new: int) -> list[Taken]:
    """The whole copies taken of a file at `found` for a migration to `new`, the newest first: a start that finds the file there again (the start before was cut short before its first step
    was in) stands on one of them when the file has not changed since (`same_bytes`)."""
    return [t for t in taken_copies(folder) if t.old == found and t.new == new and whole(t.path, found)]


CHUNK_BYTES = 1024 * 1024
# the fields of the header that the copy writes for itself and that say nothing of what the file holds: the journal's mode (the copy's is DELETE, the database's WAL), the change counter, the
# schema cookie (sqlite3's backup gives the copy its own), the number the page count is valid for and the version of SQLite that wrote the file last
BOOKKEEPING = (slice(18, 20), slice(24, 28), slice(40, 44), slice(92, 100))


def _blank(head: bytearray) -> bytearray:
    for field in BOOKKEEPING:
        head[field] = bytes(len(head[field]))
    return head


def same_bytes(database: Path, copy: Path) -> bool:
    """Whether the database file holds exactly what the copy does, byte for byte but the bookkeeping of the header. The caller has written the database's log into the file first (a checkpoint, whole): the
    copy is SQLite's page by page image of it (sqlite3's backup), so a file that nothing changed since is equal and any change to a row or a table is a difference. Only read; False when either cannot be."""
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
    """The locks of the data folder (the daemon's, the desktop app's, and the migration's, which `neoaprs db set` holds for its whole run: stopfile.MIGRATE_LOCK_NAME), taken for the restore;
    RestoreRefused when one is held by a running NeoAPRS."""
    held: list[InstanceLock] = []
    for name in (LOCK_NAME, APP_LOCK_NAME, MIGRATE_LOCK_NAME):
        lock = InstanceLock(data_dir, name)
        try:
            lock.acquire()
        except (AlreadyRunning, OSError) as e:
            _release(held)
            if isinstance(e, AlreadyRunning) and name == MIGRATE_LOCK_NAME:
                raise RestoreRefused("NeoAPRS is writing to the database or bringing it up to date now: try again when that is done") from e
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
    a daemon holds the data folder, when a tool writes or migrates the file (`_hold`), when the copy is not there, is not a database or is of a version this NeoAPRS (it knows up to `knows`) cannot open, and when the copy cannot be put in place."""
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
