"""`neoaprs db` (neoaprs/cli/dbcmd.py) run in the test's own process on a data folder of the test: the table of `list` with the rows that are not settings, the ways the database can be unusable (not a database, of
an older or a newer version), a write that is refused, and Ctrl-C. The commands as processes, through the main command, are in tests/test_cli.py."""
import asyncio
import sqlite3
from pathlib import Path

import pytest

from neoaprs.cli import dbcmd
from neoaprs.config import BEACON_SENT
from neoaprs.dberror import SqlError
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.test_migration_settings_reset import version_fifteen


def db(*args: str, data: Path) -> int:
    return dbcmd.main(["--data", str(data), *args])


@pytest.fixture
def data(tmp_path: Path) -> Path:
    folder = tmp_path / "data"
    assert db("set", "station/call", "oh2gba", data=folder) == 0           # (the file is made, at the version of this program)
    return folder


def user_version(data: Path, version: int) -> None:
    connection = sqlite3.connect(data / DB_NAME)
    connection.execute(f"PRAGMA user_version = {version}")
    connection.close()


def test_list_tells_for_each_setting_whether_it_is_stored_and_names_the_rows_that_are_not_settings(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    connection = sqlite3.connect(data / DB_NAME)
    connection.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", [(BEACON_SENT, "2026-10-21T12:00:00Z"), ("old/setting", "x")])
    connection.commit()
    connection.close()
    capsys.readouterr()
    assert db("list", data=data) == 0
    lines = capsys.readouterr().out.splitlines()
    assert any(line.startswith("station/call") and "OH2GBA" in line and line.endswith("stored") for line in lines)
    assert any(line.startswith("web/port") and line.endswith("default") for line in lines)
    assert any(line.startswith(BEACON_SENT) and line.endswith("kept by the daemon (when it last sent, how the map stands), not a setting") for line in lines)
    assert any(line.startswith("old/setting") and line.endswith("stored, not a setting of this NeoAPRS") for line in lines)


def test_a_file_that_is_not_a_database_is_told_with_its_path_and_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / DB_NAME).write_bytes(b"this is not a database, it is a letter to the operator " * 40)
    assert db("list", data=folder) == 1
    assert capsys.readouterr().err.startswith(f"neoaprs db: {folder / DB_NAME}:")


def test_a_database_of_an_older_version_is_not_read_the_daemon_has_to_migrate_it_first(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    user_version(data, SCHEMA_VERSION - 1)
    assert db("get", "station/call", data=data) == 1
    err = capsys.readouterr().err
    assert f"is of version {SCHEMA_VERSION - 1}, this NeoAPRS needs {SCHEMA_VERSION}" in err and "start the daemon once" in err


def test_set_on_a_database_of_an_older_version_migrates_it_and_says_what_the_migration_did(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    version_fifteen(tmp_path / DB_NAME, FixedClock(), {"map/maxzoom": "14"})
    capsys.readouterr()
    assert db("set", "station/call", "OH2XYZ", data=tmp_path) == 0
    err = capsys.readouterr().err
    assert "map/maxzoom reset to the default: 14 → 12" in err and f"is now version {SCHEMA_VERSION} (was {SCHEMA_VERSION - 1})" in err
    assert db("get", "station/call", data=tmp_path) == 0 and capsys.readouterr().err == "", "a command that does not write says nothing of the kind"


def test_a_database_of_a_newer_version_is_read_but_never_written(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    user_version(data, SCHEMA_VERSION + 1)
    assert db("get", "station/call", data=data) == 0
    assert db("set", "station/call", "OH2XYZ", data=data) == 1
    assert capsys.readouterr().err.count("neoaprs db:") == 1
    assert db("get", "station/call", data=data) == 0 and capsys.readouterr().out.strip() == "OH2GBA", "and the value is the one that was there"


def test_a_value_the_database_will_not_take_is_told_and_exit_1(data: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    async def refuse(self: object, key: str, value: str) -> bool:
        return False
    monkeypatch.setattr(dbcmd.Store, "put_setting", refuse)
    assert db("set", "station/call", "OH2XYZ", data=data) == 1
    assert "station/call could not be stored" in capsys.readouterr().err


def test_a_database_error_while_reading_is_told_not_raised(data: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    async def broken(store: object, only: str | None) -> int:
        raise SqlError("disk I/O error")
    monkeypatch.setattr(dbcmd, "show_settings", broken)
    assert db("list", data=data) == 1
    assert "disk I/O error" in capsys.readouterr().err


def test_ctrl_c_ends_the_command_with_130(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupted(coroutine: object) -> int:
        coroutine.close()
        raise KeyboardInterrupt
    monkeypatch.setattr(asyncio, "run", interrupted)
    assert dbcmd.main(["list"]) == 130
