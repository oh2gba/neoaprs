"""Tests for `neoaprs db` (neoaprs/cli/dbcmd.py) in the test's own process: the `list` table,
unusable databases, refused writes, Ctrl-C, and radios as rows (`radios`, `radios add`,
`radio/<id>/<key>`)."""
import asyncio
import sqlite3
import threading
import time
from typing import Any
from pathlib import Path

import pytest

from neoaprs import backupfolder
from neoaprs.cli import dbcmd
from neoaprs.config import BEACON_SENT, INSTALL_ID
from neoaprs.dberror import SqlError
from neoaprs.instancelock import LOCK_NAME, InstanceLock
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.radiosql import insert_radio, put_radio_settings, remove_radio
from neoaprs.radiotypes import type_of
from neoaprs.stopfile import MIGRATE_LOCK_NAME, MIGRATING_NAME
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened
from tests.support.migrated31 import at_thirty
from tests.test_migration_settings_reset import version_fifteen


def db(*args: str, data: Path) -> int:
    return dbcmd.main(["--data", str(data), *args])


@pytest.fixture
def data(tmp_path: Path) -> Path:
    folder = tmp_path / "data"
    # The file is made at the version of this program.
    assert db("set", "station/call", "oh2gba", data=folder) == 0
    return folder


def user_version(data: Path, version: int) -> None:
    connection = sqlite3.connect(data / DB_NAME)
    connection.execute(f"PRAGMA user_version = {version}")
    connection.close()


def test_list_tells_for_each_setting_whether_it_is_stored_and_names_the_rows_that_are_not_settings(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    connection = sqlite3.connect(data / DB_NAME)
    connection.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", [(BEACON_SENT, "2026-10-21T12:00:00Z"), (INSTALL_ID, "0123456789abcdef0123456789abcdef"), ("old/setting", "x")])
    connection.commit()
    connection.close()
    capsys.readouterr()
    assert db("list", data=data) == 0
    lines = capsys.readouterr().out.splitlines()
    assert any(line.startswith("station/call") and "OH2GBA" in line and line.endswith("stored") for line in lines)
    assert any(line.startswith("web/port") and line.endswith("default") for line in lines)
    assert any(line.startswith(BEACON_SENT) and line.endswith("kept by the daemon (when it last sent, how the map stands), not a setting") for line in lines)
    assert any(line.startswith(INSTALL_ID) and line.endswith("kept by the daemon (the number of this installation), not a setting") for line in lines)
    assert any(line.startswith("old/setting") and line.endswith("stored, not a setting of this NeoAPRS") for line in lines)


def test_list_says_where_the_value_of_a_row_of_a_key_of_before_goes_now_and_that_the_radio_is_added_first(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A folder of an older build before its first start: old rows and no radio.
    connection = sqlite3.connect(data / DB_NAME)
    connection.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", [("serial/port", "/dev/ttyUSB7"), ("hf/enabled", "true")])
    connection.commit()
    connection.close()
    capsys.readouterr()
    assert db("list", data=data) == 0
    lines = capsys.readouterr().out.splitlines()
    assert any(line.startswith("serial/port") and "/dev/ttyUSB7" in line and line.endswith("a key of before, not read: it is radio/<id>/port now (add the radio first: neoaprs db radios add TYPE)")
               for line in lines), lines
    assert any(line.startswith("hf/enabled") and line.endswith("a key of before, not read: it is the Mercury radio's Enable (Settings tab, Radio) now (add the radio first: neoaprs db radios add TYPE)") for line in lines)
    assert db("radios", "add", "kiss", data=data) == 0
    capsys.readouterr()
    assert db("list", data=data) == 0
    assert any(line.startswith("serial/port") and line.endswith("a key of before, not read: it is radio/1/port now") for line in capsys.readouterr().out.splitlines()), "with the radio there, its own key"


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


def test_while_the_daemon_brings_the_database_up_to_date_a_command_says_so_and_neither_reads_nor_migrates_it(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A read would find the old version and send the operator to start the daemon that is running;
    a write would migrate the file beside it, with a copy of its own."""
    user_version(data, SCHEMA_VERSION - 1)
    (data / MIGRATING_NAME).write_text("migrating\n")              # (the daemon's note, fresh)
    capsys.readouterr()
    for args in (("list",), ("radios",), ("get", "station/call"), ("set", "station/comment", "beside the migration")):
        assert db(*args, data=data) == 1, args
        err = capsys.readouterr().err
        assert "NeoAPRS is bringing it up to date now" in err and "try again when that is done" in err and "start the daemon" not in err, args
    connection = sqlite3.connect(data / DB_NAME)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION - 1 and connection.execute("SELECT value FROM settings WHERE key = 'station/comment'").fetchone() is None
    connection.close()
    assert not list((data / "backup").glob("premigrate-*")), "and no copy of its own"
    (data / MIGRATING_NAME).unlink()
    assert db("get", "station/call", data=data) == 1 and "start the daemon once" in capsys.readouterr().err, "with no note, the older version as before"


def test_set_on_a_database_of_an_older_version_migrates_it_and_says_what_the_migration_did(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    version_fifteen(tmp_path / DB_NAME, FixedClock(), {"map/maxzoom": "14"})
    capsys.readouterr()
    assert db("set", "station/call", "OH2XYZ", data=tmp_path) == 0
    err = capsys.readouterr().err
    assert "map/maxzoom reset to the default: 14 → 12" in err and f"is now version {SCHEMA_VERSION} (was {SCHEMA_VERSION - 1})" in err
    assert db("get", "station/call", data=tmp_path) == 0 and capsys.readouterr().err == "", "a command that does not write says nothing of the kind"


def test_set_beside_a_running_daemon_on_an_older_file_migrates_nothing_and_says_to_wait_or_to_stop_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A daemon of the previous version has the file open: these steps would break its statements (a
    packet's radio is a number since migration 32, migration 33 dropped a station column) until it
    is restarted. A daemon of this version that has just started holds the folder before it writes
    its migration note and looks the same from here."""
    at_thirty(tmp_path / DB_NAME).close()
    daemon = InstanceLock(tmp_path, LOCK_NAME)
    daemon.acquire()
    try:
        capsys.readouterr()
        assert db("set", "station/call", "OH2XYZ", data=tmp_path) == 1
        assert capsys.readouterr().err.strip() == (f"neoaprs db: {tmp_path / DB_NAME}: NeoAPRS is running with this folder and the database is not up to date yet: if it has just started, it is "
                                                   "bringing it up to date, so try again in a minute; if it is the version before, stop it (`neoaprs stop`), and the new one brings it up to date "
                                                   "at its start")
        assert rows_of(tmp_path, "PRAGMA user_version") == [(30,)] and not list((tmp_path / "backup").glob("premigrate-*")), "not migrated, and no copy taken"
    finally:
        daemon.release()
    assert db("set", "station/call", "OH2XYZ", data=tmp_path) == 0 and rows_of(tmp_path, "PRAGMA user_version") == [(SCHEMA_VERSION,)], "with that daemon stopped, the set migrates as before"


def test_set_beside_a_running_daemon_of_this_version_goes_through_though_the_files_header_is_behind_its_log(data: Path) -> None:
    """The version is SQLite's, through the write-ahead log: a migration that has not reached a
    checkpoint leaves the file's header at the old version."""
    user_version(data, SCHEMA_VERSION - 1)
    # (the daemon's connection: the log is not checkpointed into the file while it is open)
    held = sqlite3.connect(data / DB_NAME)
    held.execute("SELECT 1 FROM settings").fetchall()
    user_version(data, SCHEMA_VERSION)
    daemon = InstanceLock(data, LOCK_NAME)
    daemon.acquire()
    try:
        assert backupfolder.file_version(data / DB_NAME) == SCHEMA_VERSION - 1, "the header is behind"
        assert db("set", "station/comment", "beside the daemon", data=data) == 0
    finally:
        daemon.release()
        held.close()
    assert rows_of(data, "SELECT value FROM settings WHERE key = 'station/comment'") == [("beside the daemon",)]


def test_set_while_another_neoaprs_writes_or_migrates_the_file_is_refused_and_writes_nothing(data: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """The lock of the migration is held by a NeoAPRS that migrates the file, restores a copy, or
    writes it as `set` does (migrations.hold_for_writing), for longer than a set waits its turn."""
    monkeypatch.setattr(dbcmd, "WRITE_WAIT_MS", 200)
    other = InstanceLock(data, MIGRATE_LOCK_NAME)
    other.acquire()
    try:
        capsys.readouterr()
        assert db("set", "station/comment", "beside another", data=data) == 1
        assert capsys.readouterr().err.strip() == f"neoaprs db: {data / DB_NAME}: another `neoaprs db` command is writing it now; try again when that is done"
    finally:
        other.release()
    assert rows_of(data, "SELECT value FROM settings WHERE key = 'station/comment'") == []
    assert db("set", "station/comment", "alone", data=data) == 0, "and with the lock let go it goes through"


def test_a_second_set_waits_its_turn_behind_a_set_that_writes_and_then_goes_through(data: Path) -> None:
    """Two sets at once (two terminals, a script that runs them side by side): SQLite put them one
    after the other before the lock, and so does the lock, for as long as a set waits for SQLite's
    write lock."""
    other = InstanceLock(data, MIGRATE_LOCK_NAME)
    other.acquire()
    done = threading.Timer(0.3, other.release)                     # (the first set ends)
    done.start()
    try:
        assert db("set", "station/comment", "second", data=data) == 0
    finally:
        done.join()
    assert rows_of(data, "SELECT value FROM settings WHERE key = 'station/comment'") == [("second",)]


def test_a_set_that_waits_its_turn_stops_waiting_when_a_migration_is_seen_to_hold_the_lock(data: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """A tool does not wait for a migration (it may take minutes): the note that appears while the
    set waits ends the wait at once, with the migration's sentence."""
    monkeypatch.setattr(dbcmd, "WRITE_WAIT_MS", 60_000)
    other = InstanceLock(data, MIGRATE_LOCK_NAME)
    other.acquire()
    # (the daemon's note, written just after its lock)
    note = threading.Timer(0.2, (data / MIGRATING_NAME).write_text, ("migrating\n",))
    note.start()
    began = time.monotonic()
    try:
        capsys.readouterr()
        assert db("set", "station/comment", "beside the migration", data=data) == 1
        assert time.monotonic() - began < 5, "not the minute of the wait"
        assert "NeoAPRS is bringing it up to date now" in capsys.readouterr().err
    finally:
        note.join()
        other.release()
    assert rows_of(data, "SELECT value FROM settings WHERE key = 'station/comment'") == []


def test_a_restore_while_set_writes_is_refused_so_that_the_setting_does_not_land_in_the_file_put_aside(data: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """From before the open (which may migrate the file) to after the close: on POSIX a rename goes
    through under an open file, and the set would go on in the file put aside."""
    (data / "backup").mkdir()
    source = sqlite3.connect(data / DB_NAME)
    source.execute("VACUUM INTO ?", (str(data / "backup" / "mine.sqlite"),))           # (a copy this NeoAPRS can open)
    source.close()
    refusals: list[str] = []
    store_setting = dbcmd.store_setting

    async def beside(*args: Any) -> int:
        try:
            backupfolder.restore(data, DB_NAME, "mine.sqlite", SCHEMA_VERSION)
        except backupfolder.RestoreRefused as e:
            refusals.append(str(e))
        return await store_setting(*args)

    monkeypatch.setattr(dbcmd, "store_setting", beside)
    assert db("set", "station/comment", "kept", data=data) == 0
    assert refusals == ["NeoAPRS is writing to the database or bringing it up to date now: try again when that is done"]
    assert rows_of(data, "SELECT value FROM settings WHERE key = 'station/comment'") == [("kept",)] and not list(data.glob("neoaprs-set-aside-*"))


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


def test_set_applies_the_rules_between_settings_against_the_stored_ones_as_a_save_of_the_page_does(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert db("set", "status/source", "rig", data=data) == 2, "the radio as the source of the status needs status/rigctld"
    assert "status/rigctld" in capsys.readouterr().err
    assert db("get", "status/source", data=data) == 0 and capsys.readouterr().out.strip() != "rig", "and nothing was stored"
    assert db("set", "status/rigctld", "127.0.0.1:4532", data=data) == 0 and db("set", "status/source", "rig", data=data) == 0, "once the rigctld is set the source is taken"


def test_set_refuses_a_station_call_that_is_the_call_of_an_enabled_pair_with_the_pages_refusal(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = sqlite3.connect(data / DB_NAME, isolation_level=None)
    store.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", [("pair/1/2/enabled", "true"), ("pair/1/2/ssid", "15")])
    store.close()
    capsys.readouterr()
    assert db("set", "station/call", "OH2GBA-15", data=data) == 2
    assert "OH2GBA-15 is the call of a pair of your radios" in capsys.readouterr().err
    assert db("get", "station/call", data=data) == 0 and capsys.readouterr().out.strip() == "OH2GBA", "and nothing was stored"
    assert db("set", "station/call", "OH2GBA-9", data=data) == 0


def test_a_database_error_while_reading_is_told_not_raised(data: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    async def broken(store: object, only: str | None) -> int:
        raise SqlError("disk I/O error")
    monkeypatch.setattr(dbcmd, "show_settings", broken)
    assert db("list", data=data) == 1
    assert "disk I/O error" in capsys.readouterr().err


def test_ctrl_c_ends_the_command_with_130(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupted(coroutine: Any) -> int:
        coroutine.close()
        raise KeyboardInterrupt
    monkeypatch.setattr(asyncio, "run", interrupted)
    assert dbcmd.main(["list"]) == 130


def test_the_data_folder_may_be_given_after_the_command_and_a_folder_that_cannot_be_made_is_one_sentence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "after"
    assert dbcmd.main(["set", "--data", str(folder), "station/call", "oh2gba"]) == 0
    capsys.readouterr()
    assert dbcmd.main(["get", "--data", str(folder), "station/call"]) == 0
    assert dbcmd.main(["--data", str(tmp_path / "unused"), "get", "--data", str(folder), "station/call"]) == 0, "(the one after the command is the one that counts)"
    assert capsys.readouterr().out.splitlines() == ["OH2GBA", "OH2GBA"]
    afile = tmp_path / "afile"
    afile.write_text("not a folder")
    capsys.readouterr()
    assert db("set", "station/call", "oh2gba", data=afile / "inside") == 1
    err = capsys.readouterr().err
    assert "cannot be made or used" in err and "Traceback" not in err


# ---- the radios as rows of the database: `radios`, `radios add`, `radio/<id>/<key>`, and the old
# flat keys, which are refused

def with_radios(folder: Path, **flat: str) -> Path:
    """A data folder whose database had these flat settings at version 30 and was migrated: its
    radios are rows made from them."""
    folder.mkdir(parents=True, exist_ok=True)
    old = at_thirty(folder / DB_NAME)
    old.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", [(key.replace("_", "/", 1), value) for key, value in flat.items()])
    old.close()
    opened(folder / DB_NAME).close()
    return folder


def rows_of(folder: Path, statement: str) -> list[tuple[Any, ...]]:
    connection = sqlite3.connect(folder / DB_NAME)
    try:
        return connection.execute(statement).fetchall()
    finally:
        connection.close()


@pytest.fixture
def stored(tmp_path: Path) -> Path:
    return with_radios(tmp_path / "stored", station_call="OH2GBA", tnc_profile="kenwood-tnc2", serial_port="/dev/ttyUSB0", hf_enabled="true", mercury_keying="vox")


def test_radios_lists_each_radio_by_its_name_with_its_own_settings_and_whether_each_is_stored(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    connection = sqlite3.connect(stored / DB_NAME, isolation_level=None)
    third = insert_radio(connection, "fm", "kiss-tcp", "Base", False, 3)
    put_radio_settings(connection, third, {"tcp_host": "10.0.0.9"})
    connection.close()
    capsys.readouterr()
    assert db("radios", data=stored) == 0
    lines = capsys.readouterr().out.splitlines()
    heads = [line for line in lines if line.startswith("radio ")]
    assert heads == ["radio 1  FM  fm  kenwood-tnc2  on  (position 1)", "radio 2  Mercury  hf  mercury  on  (position 2)", f"radio {third}  Base  fm  kiss-tcp  off  (position 3)"]
    own = {line.split()[0]: line.split()[1:] for line in lines if line.startswith("  radio/")}
    assert own["radio/1/port"] == ["/dev/ttyUSB0", "stored"] and own["radio/1/baud"] == ["default"] and own["radio/2/keying"] == ["vox", "stored"]
    assert own[f"radio/{third}/tcp_host"] == ["10.0.0.9", "stored"] and own[f"radio/{third}/tcp_port"] == ["8001", "default"]
    assert [key for key in own if key.startswith("radio/1/")][:2] == ["radio/1/port", "radio/1/baud"], "in the order the type lists them"


def test_radios_lists_a_radios_type_fields_and_of_its_kinds_other_fields_only_a_value_it_keeps_from_a_type_it_had(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "kiss"
    assert db("radios", "add", "kiss", data=folder) == 0
    capsys.readouterr()
    assert db("radios", data=folder) == 0
    keys = [line.split()[0] for line in capsys.readouterr().out.splitlines() if line.startswith("  radio/")]
    assert keys == [f"radio/1/{f.key}" for f in type_of("kiss").fields], "a KISS radio lists its type's fields alone: no sound card, keying or gain of the Sound card type, no server of KISS over TCP"
    connection = sqlite3.connect(folder / DB_NAME, isolation_level=None)
    put_radio_settings(connection, 1, {"tcp_host": "10.0.0.9"})
    connection.close()
    assert db("radios", data=folder) == 0
    own = {line.split()[0]: line.split()[1:] for line in capsys.readouterr().out.splitlines() if line.startswith("  radio/")}
    assert own["radio/1/tcp_host"] == ["10.0.0.9", "stored"] and "radio/1/tcp_port" not in own and "radio/1/sound_card" not in own, "a value kept from a type it had is listed, a default of another type is not"


def test_radios_on_a_database_without_radios_says_the_station_has_none_yet_and_how_to_add_one(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert db("radios", data=data) == 0
    out = capsys.readouterr()
    assert out.out == "" and "this station has no radio yet: add one (radios add TYPE, or on the page)" in out.err


def test_radios_add_makes_a_fresh_folder_and_adds_each_radio_after_the_others_with_the_next_number(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "fresh"
    assert db("radios", "add", "kiss", "--off", data=folder) == 0, "a station set up before its first start"
    assert db("radios", "add", "mercury", "20 m", data=folder) == 0
    assert capsys.readouterr().out.splitlines() == ["radio 1  FM  fm  kiss  off  (position 1)", "radio 2  20 m  hf  mercury  on  (position 2)"]
    assert rows_of(folder, "SELECT id, kind, type, name, enabled, position FROM radio ORDER BY id") == [(1, "fm", "kiss", "", 0, 1), (2, "hf", "mercury", "20 m", 1, 2)]
    assert db("set", "radio/1/port", "/dev/ttyUSB0", data=folder) == 0 and db("set", "radio/2/keying", "vox", data=folder) == 0, "and their own settings are set by their numbers"
    connection = sqlite3.connect(folder / DB_NAME, isolation_level=None)
    remove_radio(connection, 2, "2026-11-14T10:00:00.000000Z")
    connection.close()
    assert db("radios", "add", "dummy-hf", data=folder) == 0 and capsys.readouterr().out.splitlines()[-1] == "radio 3  Mercury  hf  dummy-hf  on  (position 2)", "a removed radio's number is not given again"


def test_radios_add_refuses_a_type_that_is_none_and_a_name_another_radio_has_and_adds_nothing(stored: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert db("radios", "add", "tin-can", data=stored) == 2 and "'tin-can' is not a type of radio (the types are " in capsys.readouterr().err
    assert db("radios", "add", "kiss-tcp", "Base", data=stored) == 0
    capsys.readouterr()
    assert db("radios", "add", "kiss", "BASE", data=stored) == 2 and "is radio 3's already" in capsys.readouterr().err
    assert db("radios", "add", "kiss", "a name too long", data=stored) == 2 and "at most 8" in capsys.readouterr().err
    assert db("radios", "add", data=stored) == 2 and "which type?" in capsys.readouterr().err
    assert rows_of(stored, "SELECT id FROM radio ORDER BY id") == [(1,), (2,), (3,)], "nothing added but the radio that could be"
    assert db("radios", "add", data=tmp_path / "none") == 2 and not (tmp_path / "none" / DB_NAME).exists(), "no database is made for a refused add"


def test_a_key_of_before_of_a_radios_setting_is_refused_with_its_new_key_and_nothing_is_stored(stored: Path, data: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A key that names a radio setting without the radio is answered with the radio's own key in
    the page's sentence (configradios.flat_moved), or the radio's Enable and type by number, and
    exits 2."""
    before = rows_of(stored, "SELECT key, value, rev FROM settings ORDER BY key"), rows_of(stored, "SELECT radio_id, key, value, rev FROM radio_setting ORDER BY radio_id, key"), rows_of(stored, "SELECT * FROM radio ORDER BY id")
    capsys.readouterr()
    for command, said in ((("set", "serial/port", "COM9"), "serial/port: no such setting: it is radio/1/port now"), (("set", "mercury/tx_gain_db", "-3"), "mercury/tx_gain_db: no such setting: it is radio/2/tx_gain_db now"),
                          (("set", "tnc/profile", "kiss"), "tnc/profile: no such setting: it is radio 1's type (Settings tab, Radio) now"), (("set", "hf/enabled", "false"), "hf/enabled: no such setting: it is radio 2's Enable (Settings tab, Radio) now"),
                          (("get", "serial/baud"), "serial/baud: no such setting: it is radio/1/baud now")):
        assert db(*command, data=stored) == 2, command
        out = capsys.readouterr()
        assert (out.out, out.err.strip()) == ("", f"neoaprs db: {said}"), command
    assert (rows_of(stored, "SELECT key, value, rev FROM settings ORDER BY key"), rows_of(stored, "SELECT radio_id, key, value, rev FROM radio_setting ORDER BY radio_id, key"), rows_of(stored, "SELECT * FROM radio ORDER BY id")) == before, "nothing stored"
    assert db("set", "serial/port", "/dev/ttyUSB0", data=data) == 2 and "serial/port: no such setting: it is radio/<id>/port now" in capsys.readouterr().err, "a station with no radio: no number to name"
    assert rows_of(data, "SELECT count(*) FROM settings WHERE key = 'serial/port'") == [(0,)]
    assert db("set", "mercury/keying", "vox", data=tmp_path / "none") == 2 and "it is radio/<id>/keying now" in capsys.readouterr().err and not (tmp_path / "none" / DB_NAME).exists(), "and no database is made for it"
    assert db("list", data=stored) == 0
    assert not {line.split()[0] for line in capsys.readouterr().out.splitlines()} & {"serial/port", "tnc/profile", "hf/enabled", "mercury/keying", "beacon/path"}, "list shows no key of before"


def test_a_radios_own_setting_is_checked_by_its_field_and_stored_with_its_revision(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert db("set", "radio/1/baud", "4800", data=stored) == 0 and capsys.readouterr().out.strip() == "radio/1/baud = 4800"
    assert db("set", "radio/1/beacon", "FALSE", data=stored) == 0 and capsys.readouterr().out.strip() == "radio/1/beacon = false", "the text as the field keeps it"
    assert db("set", "radio/2/status", "True", data=stored) == 0 and capsys.readouterr().out.strip() == "radio/2/status = true", "the status's Send on, by its key as the beacon's"
    assert db("set", "radio/1/baud", "4801", data=stored) == 0
    assert rows_of(stored, "SELECT key, value, rev FROM radio_setting WHERE radio_id = 1 AND key IN ('baud', 'beacon') ORDER BY key") == [("baud", "4801", 2), ("beacon", "false", 1)]
    capsys.readouterr()
    assert db("set", "radio/1/baud", "fast", data=stored) == 2 and capsys.readouterr().err.startswith("neoaprs db: radio/1/baud: ")
    assert db("set", "radio/2/path", "WIDE1-1", data=stored) == 2 and "a radio of the kind hf has no such setting" in capsys.readouterr().err
    assert db("set", "radio/1/last_port", "/dev/ttyUSB1", data=stored) == 2, "a row of the radio's state is not a setting"
    assert db("set", "radio/7/port", "COM3", data=stored) == 2 and "there is no radio 7" in capsys.readouterr().err
    assert rows_of(stored, "SELECT key, value FROM radio_setting WHERE radio_id = 1 AND key = 'baud'") == [("baud", "4801")], "a refused value changes nothing"


def test_the_port_of_a_tcp_radio_is_no_serial_device_and_a_setting_of_a_removed_radio_is_refused(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    connection = sqlite3.connect(stored / DB_NAME, isolation_level=None)
    tcp = insert_radio(connection, "fm", "kiss-tcp", "Base", True, 3)
    connection.close()
    capsys.readouterr()
    assert db("set", f"radio/{tcp}/port", "/dev/ttyUSB0", data=stored) == 2 and "connects over TCP" in capsys.readouterr().err, "the rule of the type and the port holds"
    assert db("set", f"radio/{tcp}/port", "tcp://10.0.0.5:8100", data=stored) == 0 and db("set", "radio/1/port", "/dev/ttyUSB1", data=stored) == 0, "an address over TCP, and a serial type's serial port"
    connection = sqlite3.connect(stored / DB_NAME, isolation_level=None)
    remove_radio(connection, tcp, "2026-11-14T10:00:00.000000Z")
    connection.close()
    capsys.readouterr()
    assert db("set", f"radio/{tcp}/tcp_host", "10.0.0.9", data=stored) == 2 and "it was removed" in capsys.readouterr().err
    assert db("set", "radio/1/port", "x", data=tmp_folder_without_database(stored)) == 1 and "so no radio" in capsys.readouterr().err
    assert not (tmp_folder_without_database(stored) / DB_NAME).exists(), "no database is made for a setting of a radio it cannot have"


def tmp_folder_without_database(next_to: Path) -> Path:
    return next_to.parent / "empty"


def test_a_radios_setting_the_database_will_not_take_is_told_and_exit_1(stored: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    async def refuse(self: object, radio: int, values: object) -> bool:
        return False
    monkeypatch.setattr(dbcmd.Store, "put_radio_settings", refuse)
    assert db("set", "radio/1/baud", "4800", data=stored) == 1
    assert capsys.readouterr().err.count("could not be stored") == 1


def test_get_reads_a_radios_own_setting_and_a_row_of_its_state(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert db("get", "radio/2/keying", data=stored) == 0 and capsys.readouterr().out.strip() == "vox"
    assert db("get", "radio/2/tx_gain_db", data=stored) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "0" and "is not stored; this is the default" in out.err
    assert db("get", "radio/9/port", data=stored) == 2 and "there is no such radio" in capsys.readouterr().err
    connection = sqlite3.connect(stored / DB_NAME, isolation_level=None)
    connection.execute("INSERT INTO settings (key, value) VALUES ('radio/1/last_port', '/dev/ttyUSB3')")
    connection.close()
    assert db("get", "radio/1/last_port", data=stored) == 0 and capsys.readouterr().out.strip() == "/dev/ttyUSB3"
    assert db("get", "serial/last_port", data=stored) == 0 and capsys.readouterr().out.strip() == "/dev/ttyUSB3", "radio 1's own state row is the flat key's"
    assert db("list", data=stored) == 0
    assert any(line.startswith("radio/1/last_port") and "a radio's own" in line for line in capsys.readouterr().out.splitlines())


def test_a_database_whose_radios_cannot_be_read_is_told_with_the_way_back_and_no_flat_row_is_written_in_their_place(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    connection = sqlite3.connect(stored / DB_NAME, isolation_level=None)
    connection.execute("ALTER TABLE radio_setting RENAME TO radio_setting_gone")
    connection.close()
    capsys.readouterr()
    for command in (("set", "serial/port", "/dev/ttyUSB6"), ("set", "radio/1/port", "/dev/ttyUSB6"), ("get", "serial/port"), ("list",), ("radios",)):
        assert db(*command, data=stored) == 1, command
        out = capsys.readouterr()
        assert "the radios cannot be read: no such table: radio_setting; restore a copy (neoaprs db restore)" in out.err and "no radio is stored" not in out.err and out.out == "", command
    assert rows_of(stored, "SELECT key FROM settings WHERE key = 'serial/port'") == [], "no row of the settings that nothing reads once the radios are rows"
    assert db("stations", data=stored) == 0, "what does not read the radios still answers"


def test_a_flat_key_of_a_removed_radio_names_the_radio_of_its_kind_the_station_has_now(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Radio 1 removed and an FM radio 3 on: `serial/port` is radio 3's `radio/3/port` now, which
    the refusal of `set` and of `get` says; never radio 1's, nor that the station has no FM
    radio."""
    connection = sqlite3.connect(stored / DB_NAME, isolation_level=None)
    third = insert_radio(connection, "fm", "kiss", "Base", True, 3)
    remove_radio(connection, 1, "2026-11-14T10:00:00.000000Z")
    connection.close()
    capsys.readouterr()
    assert db("set", "serial/port", "/dev/ttyUSB2", data=stored) == 2
    err = capsys.readouterr().err
    assert f"serial/port: no such setting: it is radio/{third}/port now" in err and "radio/1/" not in err and "has none" not in err, err
    assert db("set", "fm/enabled", "false", data=stored) == 2 and f"fm/enabled: no such setting: it is radio {third}'s Enable (Settings tab, Radio) now" in capsys.readouterr().err
    assert db("get", "serial/port", data=stored) == 2
    err = capsys.readouterr().err
    assert f"serial/port: no such setting: it is radio/{third}/port now" in err and "has no FM radio" not in err, err
    assert rows_of(stored, f"SELECT count(*) FROM radio_setting WHERE radio_id = {third}") == [(0,)], "nothing was stored"


def test_a_radios_own_setting_stored_as_a_text_that_is_no_value_is_said_stored_with_its_default_in_force(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    connection = sqlite3.connect(stored / DB_NAME, isolation_level=None)
    connection.execute("INSERT INTO radio_setting (radio_id, key, value) VALUES (1, 'baud', 'fast')")
    connection.close()
    capsys.readouterr()
    assert db("get", "radio/1/baud", data=stored) == 0
    out = capsys.readouterr()
    assert out.out == "\n" and "radio/1/baud is stored as 'fast', which is not a value: the default is in force" in out.err and "is not stored" not in out.err
    assert db("radios", data=stored) == 0 and [line.split()[1:] for line in capsys.readouterr().out.splitlines() if line.startswith("  radio/1/baud ")] == [["stored"]], "as the bundle says it"


def test_a_key_of_a_radio_without_its_number_is_told_the_form_of_a_radios_key(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert db("set", "radio/x/port", "/dev/ttyUSB4", data=stored) == 2
    assert capsys.readouterr().err.strip() == "neoaprs db: radio/x/port: a radio's setting is radio/<number>/<key> (try radios)"


def test_the_port_the_search_found_is_set_in_radio_1s_own_state_row_once_the_radios_are_stored(stored: Path, data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert db("set", "serial/last_port", "/dev/ttyUSB9", data=stored) == 0
    assert rows_of(stored, "SELECT key, value FROM settings WHERE key IN ('serial/last_port', 'radio/1/last_port')") == [("radio/1/last_port", "/dev/ttyUSB9")]
    assert db("set", "serial/last_port", "/dev/ttyUSB8", data=stored) == 0
    capsys.readouterr()
    assert db("get", "serial/last_port", data=stored) == 0 and capsys.readouterr().out.strip() == "/dev/ttyUSB8", "the row that is read is the one that was set"
    assert db("set", "serial/last_port", "/dev/ttyUSB7", data=data) == 0, "a database without radios keeps it under its own name, as before"
    assert rows_of(data, "SELECT key, value FROM settings WHERE key LIKE '%last_port'") == [("serial/last_port", "/dev/ttyUSB7")]


def test_set_refuses_the_rows_the_daemon_keeps_each_radios_own_and_the_two_of_before_and_writes_none(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    before = rows_of(stored, "SELECT key, value, rev FROM settings ORDER BY key")
    capsys.readouterr()
    for key in ("radio/1/beacon_last_sent_at", "radio/2/beacon_last_sent_at", "radio/2/status_last_sent_at", "radio/1/last_port", "beacon/last_sent_at", "hf/beacon_last_sent_at", "status/last_sent_at"):
        assert db("set", key, "2026-11-14T10:00:00Z", data=stored) == 2, key
        assert capsys.readouterr().err.strip().startswith(f"neoaprs db: {key}: kept by the daemon ("), key
    assert db("set", "radio/2/last_port", "/dev/ttyUSB9", data=stored) == 2
    assert capsys.readouterr().err.strip() == "neoaprs db: radio/2/last_port: a radio of the kind hf has no such setting", "only radio 1 remembers a port: radio 2's is no row of anything"
    assert rows_of(stored, "SELECT key, value, rev FROM settings ORDER BY key") == before, "nothing written"
    assert db("set", "radio/1/last_port", "/dev/ttyUSB9", data=stored) == 2 and capsys.readouterr().err.strip().endswith("; db set serial/last_port sets it"), "radio 1's is told the setting that sets it"
    assert db("set", "serial/last_port", "/dev/ttyUSB9", data=stored) == 0, "the setting of the port found is still set, in radio 1's own row"
