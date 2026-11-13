"""The way back from a database of a newer version: the refusal names the newest copy in backup/ that this NeoAPRS can open and the command that puts it back (neoaprs/backupfolder.py, migrations.py),
and `neoaprs db restore` (neoaprs/cli/dbcmd.py) lists the copies and puts one in the place of the database, never while a NeoAPRS holds the data folder and never deleting the file that was there."""
import os
import shlex
import sqlite3
import sys
from pathlib import Path

import pytest

from neoaprs import backupfolder
from neoaprs.backupfolder import RestoreRefused
from neoaprs.cli import dbcmd
from neoaprs.instancelock import APP_LOCK_NAME, InstanceLock
from neoaprs.migrations import SCHEMA_VERSION, open_database
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock

NEWER = SCHEMA_VERSION + 1
WINDOWS = sys.platform == "win32"


def make_db(path: Path, version: int, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE marker (x)")
    db.execute("INSERT INTO marker VALUES (?)", (marker,))
    db.execute(f"PRAGMA user_version = {version}")
    db.commit()
    db.close()


def marker_of(path: Path) -> str:
    db = sqlite3.connect(path)
    try:
        return str(db.execute("SELECT x FROM marker").fetchone()[0])
    finally:
        db.close()


def dated(path: Path, when: float) -> None:
    os.utime(path, (when, when))


def restore_cli(data: Path, *args: str) -> int:
    return dbcmd.main(["--data", str(data), "restore", *args])


@pytest.fixture
def data(tmp_path: Path) -> Path:
    folder = tmp_path / "data"
    make_db(folder / DB_NAME, NEWER, "newer file")
    return folder


def test_a_newer_file_with_a_usable_copy_names_the_copy_with_its_date_and_the_command(data: Path) -> None:
    folder = data / "backup"
    old = folder / f"premigrate-v{SCHEMA_VERSION - 1}-to-v{SCHEMA_VERSION}-20261026-120000.sqlite"
    mine = folder / f"premigrate-v{SCHEMA_VERSION}-to-v{NEWER}-20261104-090000.sqlite"
    unusable = folder / "premigrate-v90-to-v91-20261109-000000.sqlite"
    make_db(old, SCHEMA_VERSION - 1, "old")
    make_db(mine, SCHEMA_VERSION, "mine")
    make_db(unusable, SCHEMA_VERSION + 5, "later")
    dated(old, 1_793_000_000)                                   # 2026-10-26
    dated(mine, 1_793_800_000)                                  # 2026-11-04 (the one before the migration that made the newer file)
    dated(unusable, 1_794_500_000)
    ok, why = open_database(data / DB_NAME)
    assert not ok and "made by a newer NeoAPRS" in why and "not touched" in why
    assert mine.name in why and "2026-11-04" in why and f"neoaprs db restore --data {data} {mine.name}" in why
    assert old.name not in why and unusable.name not in why
    assert marker_of(data / DB_NAME) == "newer file"


def test_the_date_is_that_of_the_name_when_the_file_times_are_lost_and_the_command_is_quoted_for_a_folder_with_a_space(tmp_path: Path) -> None:
    folder = tmp_path / "my data"
    make_db(folder / DB_NAME, NEWER, "newer file")
    a = folder / "backup" / f"premigrate-v1-to-v{SCHEMA_VERSION}-20261101-120000.sqlite"
    b = folder / "backup" / f"premigrate-v1-to-v{SCHEMA_VERSION}-20261105-090000.sqlite"
    make_db(a, SCHEMA_VERSION, "a")
    make_db(b, SCHEMA_VERSION, "b")
    dated(a, 1_795_000_000)
    dated(b, 1_795_000_000)                                     # a folder copied without its times: all the same
    ok, why = open_database(folder / DB_NAME)
    assert b.name in why and "2026-11-05 09:00 UTC" in why
    command = why.split("run `")[1].split("`")[0]
    quote = '"' if WINDOWS else "'"                             # (the command is written for the shell of the system: cmd and PowerShell take double quotes)
    assert command.startswith("neoaprs db restore --data ") and f"{quote}{folder}{quote}" in command
    words = [word.strip('"') for word in shlex.split(command, posix=False)] if WINDOWS else shlex.split(command)
    assert dbcmd.parse(words[2:]).name == b.name and dbcmd.parse(words[2:]).data == str(folder)


def test_a_newer_file_without_a_usable_copy_says_so_plainly(data: Path) -> None:
    make_db(data / "backup" / "by-hand.sqlite", NEWER, "also newer")
    (data / "backup" / "premigrate-v1-to-v2-20260101-000000.sqlite").write_bytes(b"not a database at all")
    ok, why = open_database(data / DB_NAME)
    assert not ok and "there is no copy in the backup folder that this NeoAPRS can open" in why and "restore" not in why and "stays with you" in why
    folder_less = data.parent / "other"
    make_db(folder_less / DB_NAME, NEWER, "x")
    ok, why = open_database(folder_less / DB_NAME)
    assert not ok and "there is no copy in the backup folder that this NeoAPRS can open" in why


def test_the_list_shows_date_version_and_size_and_marks_what_this_version_cannot_open(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = data / "backup" / "mine.sqlite"
    bad = data / "backup" / "later.sqlite"
    make_db(good, SCHEMA_VERSION, "mine")
    make_db(bad, NEWER, "later")
    (data / "backup" / "leftover.sqlite.tmp").write_bytes(b"x")
    dated(good, 1_793_800_000)
    capsys.readouterr()
    assert restore_cli(data) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    line = next(x for x in lines if x.startswith("mine.sqlite"))
    assert "2026-11-04" in line and f"version {SCHEMA_VERSION}" in line and "MB" in line and "cannot" not in line
    assert "cannot be opened" in next(x for x in lines if x.startswith("later.sqlite"))
    assert restore_cli(data.parent / "empty") == 0 and "no copy" in capsys.readouterr().err


def test_a_restore_puts_the_copy_in_place_and_keeps_the_present_file_under_a_name_that_says_when(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    copy = data / "backup" / "mine.sqlite"
    make_db(copy, SCHEMA_VERSION, "the copy")
    (data / f"{DB_NAME}-wal").write_bytes(b"frames the crash left")
    capsys.readouterr()
    assert restore_cli(data, "mine.sqlite") == 0
    assert "is now the database" in capsys.readouterr().err
    assert marker_of(data / DB_NAME) == "the copy" and copy.is_file() and marker_of(copy) == "the copy"
    kept = sorted(p.name for p in data.glob("neoaprs-set-aside-*"))
    assert len(kept) == 2 and kept[0].endswith(".sqlite") and kept[1].endswith(".sqlite-wal"), "the file and the log that belongs to it go together"
    assert marker_of(data / kept[0]) == "newer file"
    assert not (data / f"{DB_NAME}-wal").exists(), "a log of the old file is never applied to the copy"
    assert WINDOWS or (data / DB_NAME).stat().st_mode & 0o077 == 0          # (Windows has no such bits: the folder's own access list holds there)
    ok, why = open_database(data / DB_NAME)
    assert ok is not None and why == ""


def test_two_restores_in_one_second_set_aside_both_files(data: Path) -> None:
    clock = FixedClock()
    make_db(data / "backup" / "mine.sqlite", SCHEMA_VERSION, "the copy")
    _, first = backupfolder.restore(data, DB_NAME, "mine.sqlite", SCHEMA_VERSION, clock)
    _, second = backupfolder.restore(data, DB_NAME, "mine.sqlite", SCHEMA_VERSION, clock)
    assert first is not None and second is not None and first != second
    assert marker_of(first) == "newer file" and marker_of(second) == "the copy"


def test_restore_with_no_database_in_place_just_puts_the_copy(tmp_path: Path) -> None:
    make_db(tmp_path / "backup" / "mine.sqlite", SCHEMA_VERSION, "the copy")
    copy, aside = backupfolder.restore(tmp_path, DB_NAME, "mine.sqlite", SCHEMA_VERSION)
    assert aside is None and copy.version == SCHEMA_VERSION and marker_of(tmp_path / DB_NAME) == "the copy"


@pytest.mark.parametrize("lock_name", ["neoaprs.lock", APP_LOCK_NAME])
def test_restore_is_refused_while_a_neoaprs_holds_the_data_folder_and_nothing_changes(data: Path, lock_name: str, capsys: pytest.CaptureFixture[str]) -> None:
    make_db(data / "backup" / "mine.sqlite", SCHEMA_VERSION, "the copy")
    holder = InstanceLock(data, lock_name)
    holder.acquire()
    try:
        capsys.readouterr()
        assert restore_cli(data, "mine.sqlite") == 1
        assert "NeoAPRS is running" in capsys.readouterr().err
    finally:
        holder.release()
    assert marker_of(data / DB_NAME) == "newer file" and not list(data.glob("neoaprs-set-aside-*"))
    assert restore_cli(data, "mine.sqlite") == 0, "and with the lock let go it goes through (the refusal left no lock behind)"


def test_a_copy_this_version_cannot_open_is_refused(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_db(data / "backup" / "later.sqlite", NEWER, "later")
    capsys.readouterr()
    assert restore_cli(data, "later.sqlite") == 1
    assert "cannot open" in capsys.readouterr().err and marker_of(data / DB_NAME) == "newer file" and not list(data.glob("neoaprs-set-aside-*"))


@pytest.mark.parametrize("name", ["missing.sqlite", "../neoaprs.sqlite", "notes.txt", "backup/mine.sqlite"])
def test_a_name_that_is_not_a_copy_in_the_backup_folder_is_refused(data: Path, name: str) -> None:
    make_db(data / "backup" / "mine.sqlite", SCHEMA_VERSION, "the copy")
    with pytest.raises(RestoreRefused):
        backupfolder.restore(data, DB_NAME, name, SCHEMA_VERSION)
    assert marker_of(data / DB_NAME) == "newer file"


def test_a_copy_that_cannot_be_written_in_place_leaves_the_database_as_it_was(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_db(data / "backup" / "mine.sqlite", SCHEMA_VERSION, "the copy")

    def fail(source: Path, target: Path) -> None:
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(backupfolder, "_write_private", fail)
    with pytest.raises(RestoreRefused, match="as it was"):
        backupfolder.restore(data, DB_NAME, "mine.sqlite", SCHEMA_VERSION)
    assert marker_of(data / DB_NAME) == "newer file" and not list(data.glob("neoaprs-set-aside-*"))


def test_the_files_moved_aside_come_back_when_the_write_fails_and_when_a_move_fails(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_db(data / "backup" / "mine.sqlite", SCHEMA_VERSION, "the copy")
    (data / f"{DB_NAME}-wal").write_bytes(b"log")
    (data / f"{DB_NAME}-shm").write_bytes(b"shm")

    def fail(source: Path, target: Path) -> None:
        raise OSError(5, "Input/output error")
    monkeypatch.setattr(backupfolder, "_write_private", fail)
    with pytest.raises(RestoreRefused):
        backupfolder.restore(data, DB_NAME, "mine.sqlite", SCHEMA_VERSION)
    assert (data / f"{DB_NAME}-wal").read_bytes() == b"log" and (data / f"{DB_NAME}-shm").read_bytes() == b"shm" and not list(data.glob("neoaprs-set-aside-*"))
    monkeypatch.undo()
    assert marker_of(data / DB_NAME) == "newer file"            # (opening the file lets SQLite drop a log it cannot use)
    (data / f"{DB_NAME}-wal").write_bytes(b"log")
    real = Path.rename

    def rename(self: Path, target: str | Path) -> Path:
        if self.name.endswith("-wal") and "set-aside" in str(target):
            raise OSError(13, "Permission denied")
        return real(self, target)
    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(RestoreRefused, match="as it was"):
        backupfolder.restore(data, DB_NAME, "mine.sqlite", SCHEMA_VERSION)
    assert (data / f"{DB_NAME}-wal").read_bytes() == b"log" and not list(data.glob("neoaprs-set-aside-*")) and marker_of(data / DB_NAME) == "newer file"


def test_a_restore_cut_short_while_the_copy_is_written_leaves_the_database_in_its_place(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_db(data / "backup" / "mine.sqlite", SCHEMA_VERSION, "the copy")

    def killed(source: object, target: object) -> None:
        raise KeyboardInterrupt                                  # (as far as the files go, a kill or a power cut in the middle of the copy)
    monkeypatch.setattr(backupfolder.shutil, "copyfileobj", killed)
    with pytest.raises(KeyboardInterrupt):
        backupfolder.restore(data, DB_NAME, "mine.sqlite", SCHEMA_VERSION)
    assert marker_of(data / DB_NAME) == "newer file" and not list(data.glob("neoaprs-set-aside-*")) and not (data / f"{DB_NAME}.tmp").exists()


def test_copies_made_in_the_same_second_are_listed_in_the_order_they_were_made_the_last_first(tmp_path: Path) -> None:
    stem = f"premigrate-v{SCHEMA_VERSION - 1}-to-v{SCHEMA_VERSION}-20261113-120000"
    for name in (f"{stem}.sqlite", f"{stem}-2.sqlite", f"{stem}-10.sqlite"):
        make_db(tmp_path / name, SCHEMA_VERSION, name)
    assert [c.name for c in backupfolder.copies(tmp_path)] == [f"{stem}-10.sqlite", f"{stem}-2.sqlite", f"{stem}.sqlite"]
