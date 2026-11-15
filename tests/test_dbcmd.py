"""`neoaprs db` (neoaprs/cli/dbcmd.py) run in the test's own process on a data folder of the test: the table of `list` with the rows that are not settings, the ways the database can be unusable (not a database, of
an older or a newer version, one the daemon is bringing up to date), a write that is refused, and Ctrl-C; and the radios as rows (migration 31): `radios`, a radio's own setting `radio/<id>/<key>`, and a flat key of radios 1 and 2 stored
with its radio, refused for a radio the station does not have. The commands as processes, through the main command, are in tests/test_cli.py."""
import asyncio
import sqlite3
from typing import Any
from pathlib import Path

import pytest

from neoaprs.cli import dbcmd
from neoaprs.config import BEACON_SENT, INSTALL_ID
from neoaprs.dberror import SqlError
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.radiosql import insert_radio, put_radio_settings, remove_radio
from neoaprs.stopfile import MIGRATING_NAME
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
    assert db("set", "station/call", "oh2gba", data=folder) == 0           # (the file is made, at the version of this program)
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
    """A read would find the version before and send the operator to start the daemon that is running; a write would migrate the file beside it, with a copy of its own."""
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
    assert db("set", "serial/port", "/dev/ttyUSB0", data=data) == 0
    capsys.readouterr()
    assert db("set", "tnc/profile", "kiss-tcp", data=data) == 2, "a TCP profile and a serial port do not go together"
    assert "serial/port" in capsys.readouterr().err
    assert db("get", "tnc/profile", data=data) == 0 and capsys.readouterr().out.strip() != "kiss-tcp", "and nothing was stored"
    assert db("set", "status/source", "rig", data=data) == 2, "the radio as the source of the status needs status/rigctld"
    assert "status/rigctld" in capsys.readouterr().err
    assert db("set", "serial/port", "", data=data) == 0 and db("set", "tnc/profile", "kiss-tcp", data=data) == 0, "once the port is clear the profile is taken"


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


# ---- the radios as rows of the database (migration 31): `radios`, `radio/<id>/<key>`, and the flat keys of radios 1 and 2 stored with their radio

def with_radios(folder: Path, **flat: str) -> Path:
    """A data folder whose database had these flat settings at version 30 and was migrated: its radios are rows, made of them as an installation's update makes them."""
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
    assert heads == ["radio 1  FM  fm  kenwood-tnc2  on  (position 1)", "radio 2  HF  hf  mercury  on  (position 2)", f"radio {third}  Base  fm  kiss-tcp  off  (position 3)"]
    own = {line.split()[0]: line.split()[1:] for line in lines if line.startswith("  radio/")}
    assert own["radio/1/port"] == ["/dev/ttyUSB0", "stored"] and own["radio/1/baud"] == ["default"] and own["radio/2/keying"] == ["vox", "stored"]
    assert own[f"radio/{third}/tcp_host"] == ["10.0.0.9", "stored"] and own[f"radio/{third}/tcp_port"] == ["8001", "default"]
    assert [key for key in own if key.startswith("radio/1/")][:2] == ["radio/1/port", "radio/1/baud"], "in the order the type lists them"


def test_radios_on_a_database_without_radios_says_that_the_settings_of_list_are_in_force(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert db("radios", data=data) == 0
    out = capsys.readouterr()
    assert out.out == "" and "no radio is stored in this database: the radio settings of `list` are in force" in out.err


def test_a_flat_key_of_a_radio_is_stored_with_its_radio_and_read_back_from_it(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert db("set", "serial/port", "COM9", data=stored) == 0
    assert db("set", "tnc/profile", "kiss", data=stored) == 0
    assert db("set", "hf/enabled", "false", data=stored) == 0
    assert db("set", "mercury/tx_gain_db", "-3", data=stored) == 0
    assert rows_of(stored, "SELECT radio_id, key, value, rev FROM radio_setting WHERE key IN ('port', 'tx_gain_db') ORDER BY radio_id") == [(1, "port", "COM9", 2), (2, "tx_gain_db", "-3", 1)]
    assert rows_of(stored, "SELECT id, type, enabled FROM radio ORDER BY id") == [(1, "kiss", 1), (2, "mercury", 0)]
    assert rows_of(stored, "SELECT key FROM settings WHERE key IN ('serial/port', 'tnc/profile', 'hf/enabled', 'mercury/tx_gain_db')") == [], "no row the daemon would never read"
    capsys.readouterr()
    assert db("get", "serial/port", data=stored) == 0 and db("get", "tnc/profile", data=stored) == 0 and db("get", "radio/1/port", data=stored) == 0
    assert capsys.readouterr().out.splitlines() == ["COM9", "kiss", "COM9"]
    assert db("get", "serial/baud", data=stored) == 0 and "is not stored; this is the default" in capsys.readouterr().err
    assert db("list", data=stored) == 0
    listed = {line.split()[0]: line.split()[-1] for line in capsys.readouterr().out.splitlines()}
    assert (listed["serial/port"], listed["tnc/profile"], listed["hf/enabled"], listed["serial/baud"], listed["tcp/host"]) == ("stored", "stored", "stored", "default", "default")


def test_the_rules_between_settings_hold_for_a_flat_key_stored_with_its_radio(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert db("set", "tnc/profile", "kiss-tcp", data=stored) == 2 and "serial/port" in capsys.readouterr().err, "a TCP type and a serial port do not go together"
    assert db("set", "hf/enabled", "false", data=stored) == 0
    assert db("set", "fm/enabled", "false", data=stored) == 2 and "at least one radio" in capsys.readouterr().err
    assert rows_of(stored, "SELECT id, type, enabled FROM radio ORDER BY id") == [(1, "kenwood-tnc2", 1), (2, "mercury", 0)], "and nothing was stored"


def test_the_fm_radio_may_go_off_while_a_third_radio_is_on_and_the_last_radio_on_is_refused_by_the_key_that_was_set(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    connection = sqlite3.connect(stored / DB_NAME, isolation_level=None)
    third = insert_radio(connection, "fm", "kiss-tcp", "Base", True, 3)
    connection.close()
    assert db("set", "hf/enabled", "false", data=stored) == 0
    capsys.readouterr()
    assert db("set", "fm/enabled", "false", data=stored) == 0, "radio 3 stays on: the FM radio may go"
    assert rows_of(stored, "SELECT id, enabled FROM radio ORDER BY id") == [(1, 0), (2, 0), (third, 1)]
    connection = sqlite3.connect(stored / DB_NAME, isolation_level=None)
    connection.execute("UPDATE radio SET enabled = 0 WHERE id = ?", (third,))
    connection.close()
    assert db("set", "fm/enabled", "false", data=stored) == 2
    err = capsys.readouterr().err
    assert "fm/enabled: at least one radio stays on" in err, "the words begin with what was set"


def test_a_flat_key_of_a_radio_the_station_does_not_have_is_refused_with_the_way_to_add_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = with_radios(tmp_path / "fm", station_call="OH2GBA")
    assert rows_of(folder, "SELECT id, kind FROM radio") == [(1, "fm")], "HF was never set up: no radio 2"
    capsys.readouterr()
    for key, value in (("hf/enabled", "true"), ("mercury/keying", "vox"), ("hf/profile", "dummy-hf")):
        assert db("set", key, value, data=folder) == 2
        err = capsys.readouterr().err
        assert f"{key} is a setting of the HF radio, and this station has none" in err and "add it on the page (Settings tab, Radio)" in err
    assert rows_of(folder, "SELECT count(*) FROM radio_setting WHERE radio_id = 2") == [(0,)] and rows_of(folder, "SELECT count(*) FROM settings WHERE key GLOB 'hf/*' OR key GLOB 'mercury/*'") == [(0,)]


def test_a_flat_key_on_a_database_without_radios_is_its_row_of_the_settings_as_before(data: Path) -> None:
    assert rows_of(data, "SELECT count(*) FROM radio") == [(0,)], "a new installation: no radio stored"
    assert db("set", "serial/port", "/dev/ttyUSB0", data=data) == 0 and db("set", "hf/enabled", "true", data=data) == 0
    assert rows_of(data, "SELECT key, value FROM settings WHERE key IN ('serial/port', 'hf/enabled') ORDER BY key") == [("hf/enabled", "true"), ("serial/port", "/dev/ttyUSB0")]


def test_a_radios_own_setting_is_checked_by_its_field_and_stored_with_its_revision(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert db("set", "radio/1/baud", "4800", data=stored) == 0 and capsys.readouterr().out.strip() == "radio/1/baud = 4800"
    assert db("set", "radio/1/beacon", "FALSE", data=stored) == 0 and capsys.readouterr().out.strip() == "radio/1/beacon = false", "the text as the field keeps it"
    assert db("set", "radio/1/baud", "4801", data=stored) == 0
    assert rows_of(stored, "SELECT key, value, rev FROM radio_setting WHERE radio_id = 1 AND key IN ('baud', 'beacon') ORDER BY key") == [("baud", "4801", 2), ("beacon", "false", 1)]
    capsys.readouterr()
    assert db("set", "radio/1/baud", "fast", data=stored) == 2 and capsys.readouterr().err.startswith("neoaprs db: radio/1/baud: ")
    assert db("set", "radio/2/path", "WIDE1-1", data=stored) == 2 and "a radio of the kind hf has no such setting" in capsys.readouterr().err
    assert db("set", "radio/1/last_port", "/dev/ttyUSB1", data=stored) == 2, "a row of the radio's state is not a setting"
    assert db("set", "radio/7/port", "COM3", data=stored) == 2 and "there is no radio 7" in capsys.readouterr().err
    assert rows_of(stored, "SELECT key, value FROM radio_setting WHERE radio_id = 1 AND key = 'baud'") == [("baud", "4801")], "a refused value changes nothing"


def test_a_radios_own_setting_that_is_a_flat_keys_follows_the_rules_between_settings_and_one_of_a_removed_radio_is_refused(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert db("set", "tnc/profile", "kiss-tcp", data=stored) == 2
    assert db("set", "radio/1/port", "", data=stored) == 0 and db("set", "tnc/profile", "kiss-tcp", data=stored) == 0
    capsys.readouterr()
    assert db("set", "radio/1/port", "/dev/ttyUSB0", data=stored) == 2 and "connects over TCP" in capsys.readouterr().err, "radio 1's port is serial/port: the rule of the type and the port holds"
    connection = sqlite3.connect(stored / DB_NAME, isolation_level=None)
    third = insert_radio(connection, "fm", "kiss-tcp", "", True, 3)
    remove_radio(connection, third, "2026-11-14T10:00:00.000000Z")
    connection.close()
    assert db("set", f"radio/{third}/tcp_host", "10.0.0.9", data=stored) == 2 and "it was removed" in capsys.readouterr().err
    assert db("set", "radio/1/port", "x", data=tmp_folder_without_database(stored)) == 1 and "so no radio" in capsys.readouterr().err
    assert not (tmp_folder_without_database(stored) / DB_NAME).exists(), "no database is made for a setting of a radio it cannot have"


def tmp_folder_without_database(next_to: Path) -> Path:
    return next_to.parent / "empty"


def test_a_radios_setting_the_database_will_not_take_is_told_and_exit_1(stored: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    async def refuse(self: object, radio: int, values: object) -> bool:
        return False
    monkeypatch.setattr(dbcmd.Store, "put_radio_settings", refuse)
    assert db("set", "radio/1/baud", "4800", data=stored) == 1 and db("set", "serial/baud", "4800", data=stored) == 1
    assert capsys.readouterr().err.count("could not be stored") == 2


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


def test_the_flat_keys_of_a_removed_radio_show_the_defaults_and_say_the_station_has_no_such_radio(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    connection = sqlite3.connect(stored / DB_NAME, isolation_level=None)
    remove_radio(connection, 2, "2026-11-14T10:00:00.000000Z")
    connection.close()
    capsys.readouterr()
    assert db("get", "mercury/keying", data=stored) == 0
    out = capsys.readouterr()
    assert out.out == "\n" and "mercury/keying: this station has no HF radio (radio 2 was removed); the default is shown" in out.err, "not the removed radio's keying, vox, called the default"
    assert db("list", data=stored) == 0
    listed = {line.split()[0]: line.split()[1:] for line in capsys.readouterr().out.splitlines()}
    assert listed["mercury/keying"] == ["default"] and listed["hf/enabled"] == ["false", "default"]
    fm = with_radios(stored.parent / "fm", station_call="OH2GBA")
    capsys.readouterr()
    assert db("get", "mercury/keying", data=fm) == 0 and "this station has no HF radio; the default is shown" in capsys.readouterr().err, "and a station that never had one is told so too"


def test_a_radios_own_setting_stored_as_a_text_that_is_no_value_is_said_stored_with_its_default_in_force(stored: Path, capsys: pytest.CaptureFixture[str]) -> None:
    connection = sqlite3.connect(stored / DB_NAME, isolation_level=None)
    connection.execute("INSERT INTO radio_setting (radio_id, key, value) VALUES (1, 'baud', 'fast')")
    connection.close()
    capsys.readouterr()
    for key in ("serial/baud", "radio/1/baud"):
        assert db("get", key, data=stored) == 0
        out = capsys.readouterr()
        assert out.out == "\n" and f"{key} is stored as 'fast', which is not a value: the default is in force" in out.err and "is not stored" not in out.err, key
    assert db("list", data=stored) == 0 and [line.split()[1:] for line in capsys.readouterr().out.splitlines() if line.startswith("serial/baud ")] == [["stored"]]
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
    for key in ("radio/1/beacon_last_sent_at", "radio/2/beacon_last_sent_at", "radio/1/last_port", "radio/3/last_port", "beacon/last_sent_at", "hf/beacon_last_sent_at", "status/last_sent_at"):
        assert db("set", key, "2026-11-14T10:00:00Z", data=stored) == 2, key
        assert capsys.readouterr().err.strip().startswith(f"neoaprs db: {key}: kept by the daemon ("), key
    assert rows_of(stored, "SELECT key, value, rev FROM settings ORDER BY key") == before, "nothing written"
    assert db("set", "radio/1/last_port", "/dev/ttyUSB9", data=stored) == 2 and capsys.readouterr().err.strip().endswith("; db set serial/last_port sets it"), "radio 1's is told the setting that sets it"
    assert db("set", "serial/last_port", "/dev/ttyUSB9", data=stored) == 0, "the setting of the port found is still set, in radio 1's own row"
