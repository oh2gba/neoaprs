"""The radios in the database (neoaprs/radiosql.py, and the Store's part of them, neoaprs/store.py): a radio is added with an id no radio had before, its columns and its own settings are changed,
the stored radios are read as `RadioSpec`s (configradios.radios_from_rows), and Remove keeps the row and takes back what chooses the radio, all of it or none."""
import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from neoaprs.clock import utc
from neoaprs.config import DEFAULTS, LAST_PORT, Config
from neoaprs.configradios import radios_from_rows
from neoaprs.dbfile import transaction
from neoaprs.packetcodec import stamp
from neoaprs.radiospec import RadioSpec
from neoaprs.radiosql import CHANGEABLE, insert_radio, put_radio_settings, radio_rows, radio_settings, remove_radio, update_radio
from neoaprs.store import DB_NAME, Store
from neoaprs.wiring import _store_last_port
from tests.support.clock import FixedClock
from tests.support.migrated31 import radio_tables
from tests.support.storedb import sql, store_at

T0 = utc(2026, 11, 14, 8, 0)
AT = stamp(T0)
OBJECT = "INSERT INTO own_object (name, kind, lat, lon, symbol_table, symbol_code, comment, alive, created_at, updated_at, radios) VALUES (?, 'object', 60.2, 25.0, '/', '-', 'camp', 1, ?, ?, ?)"


def database(tmp_path: Path) -> sqlite3.Connection:
    """A new database with the radios' tables, open in autocommit as a tool opens it."""
    radio_tables(tmp_path / DB_NAME, FixedClock())
    return sqlite3.connect(tmp_path / DB_NAME, isolation_level=None)


async def store_of(tmp_path: Path, clock: FixedClock | None = None) -> Store:
    radio_tables(tmp_path / DB_NAME, clock or FixedClock())
    return await store_at(tmp_path / DB_NAME, clock or FixedClock())


def revisions(db: sqlite3.Connection) -> dict[tuple[int, str], tuple[str, int]]:
    return {(int(radio), str(key)): (str(value), int(rev)) for radio, key, value, rev in db.execute("SELECT radio_id, key, value, rev FROM radio_setting")}


# ---- the statements

def test_a_new_database_has_no_radio_and_a_radio_added_gets_the_next_id_which_is_never_used_again(tmp_path: Path) -> None:
    db = database(tmp_path)
    assert radio_rows(db) == [] and radio_settings(db) == []
    assert insert_radio(db, "fm", "kiss", "", True, 1) == 1 and insert_radio(db, "hf", "mercury", "20 m", False, 2) == 2
    assert radio_rows(db) == [(1, "fm", "kiss", "", 1, 1, None), (2, "hf", "mercury", "20 m", 0, 2, None)]
    db.execute("DELETE FROM radio WHERE id = 2")           # (the program never deletes a radio; a tool that did would still not get its id again)
    assert insert_radio(db, "fm", "kiss-tcp", "Shack", True, 2) == 3


def test_a_radios_columns_are_changed_one_or_several_and_its_kind_and_its_removal_are_not_a_change(tmp_path: Path) -> None:
    db = database(tmp_path)
    insert_radio(db, "fm", "kiss", "", True, 1)
    assert update_radio(db, 1, name="Shack") == 1 and update_radio(db, 1, type="kiss-tcp", enabled=False, position=4) == 1 and update_radio(db, 9, name="x") == 0
    assert radio_rows(db) == [(1, "fm", "kiss-tcp", "Shack", 0, 4, None)]
    assert CHANGEABLE == ("type", "name", "enabled", "position")
    for columns in ({"kind": "hf"}, {"removed_at": AT}, {"id": 5}, {"name": "x", "kind": "hf"}, {}):
        with pytest.raises(ValueError, match="cannot be set"):
            update_radio(db, 1, **columns)
    with pytest.raises(sqlite3.IntegrityError):
        update_radio(db, 1, name="much too long")
    assert radio_rows(db) == [(1, "fm", "kiss-tcp", "Shack", 0, 4, None)]


def test_a_radios_own_settings_are_written_with_a_revision_that_counts_up_and_the_others_stay(tmp_path: Path) -> None:
    db = database(tmp_path)
    insert_radio(db, "fm", "kiss", "", True, 1)
    insert_radio(db, "hf", "mercury", "", True, 2)
    put_radio_settings(db, 1, {"port": "/dev/ttyUSB0", "baud": "9600"})
    put_radio_settings(db, 2, {"keying": "vox"})
    put_radio_settings(db, 1, {"port": "/dev/ttyUSB1", "path": "WIDE2-2"})
    put_radio_settings(db, 1, {})
    assert revisions(db) == {(1, "port"): ("/dev/ttyUSB1", 2), (1, "baud"): ("9600", 1), (1, "path"): ("WIDE2-2", 1), (2, "keying"): ("vox", 1)}
    assert radio_settings(db) == [(1, "baud", "9600"), (1, "path", "WIDE2-2"), (1, "port", "/dev/ttyUSB1"), (2, "keying", "vox")]


def test_a_radio_that_is_not_there_or_is_removed_takes_no_settings_and_no_change(tmp_path: Path) -> None:
    db = database(tmp_path)
    insert_radio(db, "fm", "kiss", "", True, 1)
    insert_radio(db, "hf", "mercury", "20 m", False, 2)
    assert put_radio_settings(db, 1, {"port": "/dev/ttyUSB0"}) and not put_radio_settings(db, 9, {"port": "/dev/x"}), "the table's REFERENCES is not enforced: the statement checks"
    assert remove_radio(db, 2, AT) == 1
    assert not put_radio_settings(db, 2, {"keying": "vox"}) and update_radio(db, 2, enabled=True) == 0 and update_radio(db, 2, name="40 m") == 0
    assert revisions(db) == {(1, "port"): ("/dev/ttyUSB0", 1)}, "no row for radio 9, nothing new for the removed radio 2"
    assert radio_rows(db) == [(1, "fm", "kiss", "", 1, 1, None), (2, "hf", "mercury", "20 m", 0, 2, AT)], "the removed radio says what it said when it was removed"
    assert insert_radio(db, "fm", "kiss", "", True, 3) == 3 and radio_settings(db) == [(1, "port", "/dev/ttyUSB0")], "a radio added later starts with no settings of another's"


def test_settings_written_during_an_error_are_not_half_written(tmp_path: Path) -> None:
    db = database(tmp_path)
    insert_radio(db, "fm", "kiss", "", True, 1)
    with pytest.raises(sqlite3.IntegrityError):
        transaction(db, lambda conn: put_radio_settings(conn, 1, {"port": "/dev/ttyUSB0", "a/b": "a key with a slash is refused by the table"}))
    assert radio_settings(db) == [], "all of it or none"


def test_the_stored_radios_are_read_with_the_settings_of_their_kind_and_a_wrong_value_is_the_default_told_once(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    db = database(tmp_path)
    insert_radio(db, "fm", "kenwood-d710", "", True, 2)
    insert_radio(db, "hf", "mercury", "20 m", False, 1)
    insert_radio(db, "fm", "kiss-tcp", "Shack", True, 3)
    put_radio_settings(db, 1, {"port": "/dev/ttyUSB0", "baud": "fast", "path": "WIDE2-2", "sound_card": "plughw:1,0", "note": "no setting of any kind"})
    put_radio_settings(db, 2, {"sound_card": "plughw:1,0", "tx_gain_db": "-6", "path": "WIDE2-2", "digipeat": "true"})
    remove_radio(db, 3, AT)
    with caplog.at_level(logging.WARNING, logger="neoaprs.config"):
        found = radios_from_rows(radio_rows(db), radio_settings(db))
    assert found == (RadioSpec(1, "fm", "kenwood-d710", "", True, 2, None, {"port": "/dev/ttyUSB0", "path": "WIDE2-2", "sound_card": "plughw:1,0"}), RadioSpec(2, "hf", "mercury", "20 m", False, 1, None, {"sound_card": "plughw:1,0", "tx_gain_db": "-6"}),
                     RadioSpec(3, "fm", "kiss-tcp", "Shack", True, 3, T0, {})), "by id; a key that is no setting of the kind is left in the table, and the removed radio is among them with its time"
    assert [r.getMessage() for r in caplog.records] == ["radio/1/baud: 'fast' is not a whole number; the default (empty) is used"]
    assert (found[0].value("baud"), found[0].value("tcp_port"), found[1].value("keying"), found[1].value("beacon")) == (None, 8001, "", True), "what is not stored is the field's default"
    config = Config.from_data({"station/call": "OH2GBA"}, radios=reversed(found))
    assert config.radios == found and [s.id for s in config.live_radios] == [2, 1] and config.main_radio == 1 and config.radio(3) is found[2], "the settings hold them by id, and read them by position"
    assert radios_from_rows([(4, "am", "kiss", "", 1, 1, None), (5, "lora", "dummy-lora", "", 1, 2, None)], []) == (RadioSpec(5, "lora", "dummy-lora", "", True, 2),), "a row of a kind that is none is left out and told"


# ---- Remove

def removal(tmp_path: Path) -> sqlite3.Connection:
    """Three radios and everything that can choose radio 2: objects, stations' paths, stations' choices and the radio's own state rows."""
    db = database(tmp_path)
    insert_radio(db, "fm", "kiss", "", True, 1)
    insert_radio(db, "hf", "mercury", "20 m", True, 2)
    insert_radio(db, "fm", "kiss-tcp", "", True, 3)
    put_radio_settings(db, 2, {"sound_card": "plughw:1,0"})
    for name, radios in (("BOTH", "1,2"), ("ALL", "1,2,3"), ("HFONLY", "2"), ("FMONLY", "1"), ("TWELVE", "12"), ("LAST", "3,12,2")):
        db.execute(OBJECT, (name, AT, AT, radios))
    db.execute("INSERT INTO station_path (call, radio_id, path, updated_at) VALUES ('OH2RDG', 1, 'WIDE1-1', ?), ('OH2RDG', 2, 'WIDE2-1', ?), ('OH6XYZ', 2, '', ?), ('OH6XYZ', 12, 'WIDE2-2', ?)", (AT, AT, AT, AT))
    db.execute("INSERT INTO settings (key, value) VALUES ('messages/radio_by_station', ?), ('radio/2/beacon_last_sent_at', '2026-11-14T07:00:00Z'), ('radio/2/last_port', '/dev/ttyUSB2'), "
               "('radio/1/last_port', '/dev/ttyUSB0'), ('radio/22/last_port', '/dev/ttyUSB9'), ('station/call', 'OH2GBA')", (json.dumps({"OH2RDG": 2, "OH6XYZ": 1, "OH2ABC": 2}),))
    return db


def test_remove_keeps_the_row_and_takes_the_radio_out_of_the_sets_the_paths_the_choices_and_its_state(tmp_path: Path) -> None:
    db = removal(tmp_path)
    assert transaction(db, lambda conn: remove_radio(conn, 2, AT)) == 1
    assert radio_rows(db) == [(1, "fm", "kiss", "", 1, 1, None), (2, "hf", "mercury", "20 m", 1, 2, AT), (3, "fm", "kiss-tcp", "", 1, 3, None)], "the row stays, with when it was removed"
    assert radio_settings(db) == [(2, "sound_card", "plughw:1,0")], "and its own settings with it"
    assert dict(db.execute("SELECT name, radios FROM own_object").fetchall()) == {"BOTH": "1", "ALL": "1,3", "HFONLY": "2", "FMONLY": "1", "TWELVE": "12", "LAST": "3,12"}, \
        "an object that went out on it alone keeps it (such a set is read as the main radio); radio 12 is not radio 2"
    assert db.execute("SELECT call, radio_id, path FROM station_path ORDER BY call, radio_id").fetchall() == [("OH2RDG", 1, "WIDE1-1"), ("OH6XYZ", 12, "WIDE2-2")]
    rows = {str(key): (str(value), int(rev)) for key, value, rev in db.execute("SELECT key, value, rev FROM settings")}
    assert rows == {"messages/radio_by_station": ('{"OH6XYZ": 1}', 2), "radio/1/last_port": ("/dev/ttyUSB0", 1), "radio/22/last_port": ("/dev/ttyUSB9", 1), "station/call": ("OH2GBA", 1)}
    assert [(s.id, s.removed, s.removed_at) for s in radios_from_rows(radio_rows(db), radio_settings(db))] == [(1, False, None), (2, True, T0), (3, False, None)]


def test_removing_a_radio_that_is_gone_or_was_never_there_touches_nothing(tmp_path: Path) -> None:
    db = removal(tmp_path)
    assert remove_radio(db, 2, AT) == 1
    db.execute("UPDATE own_object SET radios = '1,2' WHERE name = 'BOTH'")
    assert remove_radio(db, 2, "2026-11-15T00:00:00.000000Z") == 0 and remove_radio(db, 9, AT) == 0
    assert db.execute("SELECT removed_at FROM radio WHERE id = 2").fetchone() == (AT,) and db.execute("SELECT radios FROM own_object WHERE name = 'BOTH'").fetchone() == ("1,2",)


def test_a_remove_that_fails_half_way_removes_nothing(tmp_path: Path) -> None:
    db = removal(tmp_path)
    db.execute("DROP TABLE station_path")                  # (the statement after the objects' fails)
    with pytest.raises(sqlite3.OperationalError):
        transaction(db, lambda conn: remove_radio(conn, 2, AT))
    assert db.execute("SELECT removed_at FROM radio WHERE id = 2").fetchone() == (None,) and db.execute("SELECT radios FROM own_object WHERE name = 'BOTH'").fetchone() == ("1,2",), "all of it or none"


def test_a_row_of_choices_that_is_not_one_is_left_alone_by_remove(tmp_path: Path) -> None:
    db = removal(tmp_path)
    db.execute("UPDATE settings SET value = 'not json' WHERE key = 'messages/radio_by_station'")
    assert remove_radio(db, 2, AT) == 1 and db.execute("SELECT value, rev FROM settings WHERE key = 'messages/radio_by_station'").fetchone() == ("not json", 1)


# ---- the Store

async def test_a_row_of_a_removed_radios_own_state_written_after_the_removal_is_not_stored(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A write that waited behind the removal (the beacon's last send, services/memory.py; the port the search found, wiring._store_last_port) writes nothing for the removed radio: the removal took
    its rows away, and its id never comes back, so nothing would take them away again."""
    store = await store_of(tmp_path, FixedClock(T0))
    assert await store.add_radio("fm", "kiss", "", True, 1) == 1 and await store.add_radio("lora", "dummy-lora", "", True, 2) == 2
    assert await store.put_settings({"radio/2/beacon_last_sent_at": AT, "radio/1/last_port": "/dev/ttyUSB0"})
    assert await store.remove_radio(2)
    caplog.set_level(logging.INFO, "neoaprs.store")
    assert not await store.put_settings({"radio/2/beacon_last_sent_at": AT}) and not await store.put_setting("radio/2/last_port", "/dev/ttyUSB1")
    assert not await store.put_settings({"station/comment": "x", "radio/2/beacon_last_sent_at": AT}), "all of it or none"
    rows = await store.settings()
    assert not [key for key in rows if key.startswith("radio/2/")] and "station/comment" not in rows
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING], "told in the log, as no error"
    assert await store.put_setting("radio/1/last_port", "/dev/ttyUSB1") and await store.put_settings({"radio/7/beacon_last_sent_at": AT}), \
        "a live radio's, and one of a radio that has no row (radios not stored yet), as before"


async def test_the_port_found_is_neither_stored_nor_put_in_force_when_radio_1_was_removed_while_it_waited(tmp_path: Path) -> None:
    store = await store_of(tmp_path, FixedClock(T0))
    assert await store.add_radio("fm", "kiss", "", True, 1) == 1 and await store.add_radio("fm", "kiss", "", True, 2) == 2
    told: list[Config] = []
    parts = SimpleNamespace(config_lock=asyncio.Lock(), store=store, config=DEFAULTS, config_changed=SimpleNamespace(emit=told.append))
    async with parts.config_lock:                                   # (Controller.remove_radio holds it)
        waiting = asyncio.create_task(_store_last_port(cast(Any, parts), "/dev/ttyUSB0"))
        await asyncio.sleep(0)
        assert await store.remove_radio(1)
    await waiting
    assert await store.setting(LAST_PORT) is None and parts.config.serial_last_port == "" and told == []


async def test_the_store_adds_changes_reads_and_removes_radios_on_the_database_thread(tmp_path: Path) -> None:
    clock = FixedClock(T0)
    store = await store_of(tmp_path, clock)
    assert await store.radios() == ()
    assert await store.add_radio("fm", "kiss", "", True, 1, settings={"port": "/dev/ttyUSB0"}) == 1 and await store.add_radio("hf", "mercury", "20 m", False, 2) == 2
    assert await store.radios() == (RadioSpec(1, "fm", "kiss", "", True, 1, None, {"port": "/dev/ttyUSB0"}), RadioSpec(2, "hf", "mercury", "20 m", False, 2))
    assert await store.change_radio(2, enabled=True, name="40 m") and not await store.change_radio(7, enabled=True)
    assert await store.put_radio_settings(2, {"keying": "vox", "tx_gain_db": "-6"}) and await store.put_radio_settings(1, {"port": "/dev/ttyUSB1"})
    assert await store.radios() == (RadioSpec(1, "fm", "kiss", "", True, 1, None, {"port": "/dev/ttyUSB1"}), RadioSpec(2, "hf", "mercury", "40 m", True, 2, None, {"keying": "vox", "tx_gain_db": "-6"}))
    assert await sql(store, "SELECT radio_id, key, rev FROM radio_setting ORDER BY radio_id, key") == [(1, "port", 2), (2, "keying", 1), (2, "tx_gain_db", 1)]
    assert await store.remove_radio(2) and not await store.remove_radio(2) and not await store.remove_radio(7)
    assert [(s.id, s.removed_at) for s in await store.radios()] == [(1, None), (2, T0)], "removed at the store's clock, and still among the radios"
    assert await store.add_radio("hf", "mercury", "40 m", True, 2) == 3, "the name of the removed radio is free, its id is not"
    assert not await store.put_radio_settings(2, {"keying": "vox"}) and not await store.change_radio(2, enabled=False) and not await store.put_radio_settings(7, {"port": "/dev/x"}), \
        "a removed radio and one that never was are told as no"
    assert await sql(store, "SELECT radio_id, key, rev FROM radio_setting ORDER BY radio_id, key") == [(1, "port", 2), (2, "keying", 1), (2, "tx_gain_db", 1)]


@pytest.mark.expects_errors
async def test_a_radio_the_table_refuses_is_not_stored_and_the_store_says_no_without_raising(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = await store_of(tmp_path)
    assert await store.add_radio("fm", "kiss", "Shack", True, 1) == 1
    assert await store.add_radio("fm", "kiss", "SHACK", True, 2) is None, "a name another live radio has"
    assert await store.add_radio("am", "kiss", "", True, 2) is None
    assert await store.add_radio("fm", "kiss", "", True, 2, settings={"a/b": "x"}) is None and [s.id for s in await store.radios()] == [1], "a radio whose settings are refused is not added at all"
    assert not await store.change_radio(1, name="much too long") and not await store.put_radio_settings(1, {"port": "/dev/ttyUSB0", "a/b": "x"})
    assert await store.radios() == (RadioSpec(1, "fm", "kiss", "Shack", True, 1),), "nothing half stored"
    assert sum("could not be" in r.getMessage() for r in caplog.records if r.levelno == logging.ERROR) == 5
    with pytest.raises(ValueError, match="cannot be set"):
        await store.change_radio(1, kind="hf")


async def test_a_store_that_is_not_open_has_no_radios_and_keeps_none(tmp_path: Path) -> None:
    store = Store(FixedClock())
    assert await store.radios() == () and await store.add_radio("fm", "kiss", "", True, 1) is None
    assert not await store.change_radio(1, enabled=False) and not await store.put_radio_settings(1, {"port": "x"}) and not await store.remove_radio(1)
    opened = await store_of(tmp_path)
    assert opened.db is not None and await opened.add_radio("fm", "kiss", "", True, 1) == 1
    await opened.db.close()
    assert await opened.radios() == () and await opened.add_radio("fm", "kiss", "", True, 2) is None and not await opened.remove_radio(1), "a closed database is no error either"


@pytest.mark.expects_errors
async def test_a_read_of_the_radios_that_failed_is_told_apart_from_a_database_that_has_none(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = await store_of(tmp_path)
    assert await store.read_radios() == (), "an open database with no radio: a new installation"
    assert store.db is not None
    await store.db.write(lambda db: db.execute("DROP TABLE radio_setting"))
    assert await store.read_radios() is None and await store.radios() == (), "a read that failed is None, never taken for a database without radios"
    assert "the radios could not be read" in caplog.text
    assert await Store(FixedClock()).read_radios() is None, "nor is a database that is not open"
