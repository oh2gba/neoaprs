"""The folder of copies of the database, data/backup: what a copy that did not end leaves behind.

A copy is written under a temporary name (`<name>.tmp`, with SQLite's `-journal` beside it while it is written) and renamed when it is whole (dbfile.copy_database). A process killed
in between (SIGKILL, the OOM killer, a power cut) leaves the temporary file, up to the size of the database, and nothing else removes it.
"""
import os
import re
from pathlib import Path

LITTER = re.compile(r"^[^/]+\.sqlite\.tmp(-journal)?$")      # the temporary file of a copy, and the journal SQLite keeps beside it while it is written
PREMIGRATION = re.compile(r"^premigrate-v\d+-to-v\d+-\d{8}-\d{6}(-\d+)?\.sqlite$")        # the copy taken before a migration (migrations.premigration_backup)
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
