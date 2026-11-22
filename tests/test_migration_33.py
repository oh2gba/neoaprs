"""Migration 33 (neoaprs/migrationsteps32.py): what each radio heard of a station is a
`station_radio` row, a station's path is its path on a radio (`station_path`), and our objects name
their radios by id.
"""
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from neoaprs import packetcodec
from neoaprs.dberror import StoreError
from neoaprs.messagelog import MessageLog
from neoaprs.migrationsteps32 import _v32, _v33
from neoaprs.ownlog import OwnLog
from neoaprs.packetcodec import parse_stamp
from neoaprs.packetlog import PacketLog
from neoaprs.pref import Alert
from neoaprs.radiospec import RadioHeard
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated32 import columns, heard_by, old_database, run, said_of, step_31, stepped, tables, undo_32, undo_33
from tests.support.storedb import sql, store_at

STAMP = "2026-10-21T12:00:00.000000Z"
LATER = "2026-10-21T12:30:00.000000Z"
LATEST = "2026-10-21T13:30:00.000000Z"
STATION = ("INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, lat, lon, first_heard, last_heard, last_position_at, last_status, last_comment, packets, last_path, heard_rf, heard_is, last_rf_at, "
           "last_is_at, heard_fm, heard_hf, last_fm_at, last_hf_at, snr, rssi, signal_at) VALUES (?, 'station', '', '/', '-', 60.1, 24.9, ?, ?, ?, 'QRV', 'comment', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, -3.5, -101.0, ?)")
PREF = "INSERT INTO station_pref (call, path, attempts, rf_only, alert_on_air, alert_within_km, alert_direct, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
OBJECT = "INSERT INTO own_object (name, kind, lat, lon, symbol_table, symbol_code, comment, alive, created_at, updated_at, qru_group, radio) VALUES (?, 'object', 60.2, 25.0, '/', '-', 'camp', 1, ?, ?, 'RP70', ?)"
# (call, the path of its last packet, heard on FM, heard on HF, when on FM, when on HF, heard from
# the internet)
STATIONS = [("OH2FMLAST", "OH2RCH-2*,WIDE2-1", 3, 2, LATEST, LATER, 0), ("OH2HFLAST", "WIDE1-1", 3, 2, STAMP, LATER, 0), ("OH2TIE", "OH2RCH-2*", 1, 1, LATER, LATER, 0), ("OH2FM", "WIDE1-1*", 4, 0, LATER, None, 1),
            ("OH2HF", "", 0, 5, None, LATEST, 0), ("OH2NET", "", 0, 0, None, None, 7), ("OH2DIRECT", "", 2, 0, STAMP, None, 0)]
HEARD = {"OH2FMLAST": {1: (3, LATEST, "OH2RCH-2*,WIDE2-1"), 2: (2, LATER, "")}, "OH2HFLAST": {1: (3, STAMP, ""), 2: (2, LATER, "WIDE1-1")}, "OH2TIE": {1: (1, LATER, "OH2RCH-2*"), 2: (1, LATER, "")},
         "OH2FM": {1: (4, LATER, "WIDE1-1*")}, "OH2HF": {2: (5, LATEST, "")}, "OH2DIRECT": {1: (2, STAMP, "")}}
# (call, path, attempts, rf_only, alert_on_air, alert_within_km, alert_direct, updated_at)
PREFS = [("OH2PATH", "WIDE1-1,WIDE2-1", None, 0, 0, None, 0, STAMP), ("OH2DIRECT", "", None, 0, 0, None, 0, LATER), ("OH2BOTH", "OH2RCH-2", None, 1, 0, None, 0, LATER), ("EMAIL-2", None, None, 1, 0, None, 0, STAMP),
         ("OH2ALERT", None, None, 0, 1, 25, 1, LATEST), ("OH2OLD", None, 3, 0, 0, None, 0, STAMP), ("OH2ALL", "WIDE2-1", 4, 1, 1, None, 0, LATEST)]
OBJECTS = [("ONFM", "fm"), ("ONHF", "hf"), ("ONBOTH", "both")]
BOTH_ON = {"fm/enabled": "true", "hf/enabled": "true"}


def stations(db: sqlite3.Connection) -> None:
    for call, path, fm, hf, fm_at, hf_at, internet in STATIONS:
        last = max(at for at in (fm_at, hf_at, STAMP) if at is not None)
        db.execute(STATION, (call, STAMP, last, STAMP, fm + hf + internet, path, fm + hf, internet, max((at for at in (fm_at, hf_at) if at is not None), default=None), STAMP if internet else None, fm, hf, fm_at, hf_at, last))


def prefs(db: sqlite3.Connection) -> None:
    db.executemany(PREF, PREFS)


def objects(db: sqlite3.Connection) -> None:
    for name, radio in OBJECTS:
        db.execute(OBJECT, (name, STAMP, LATER, radio))


def whole(db: sqlite3.Connection, table: str, without: tuple[str, ...]) -> list[tuple[Any, ...]]:
    """Every row of a table without the columns named, by the table's key."""
    names = [name for name in columns(db, table) if name not in without]
    return db.execute(f"SELECT {', '.join(names)} FROM {table} ORDER BY 1").fetchall()


def at_32(tmp_path: Path, *fill: Any, settings: dict[str, str] | None = None) -> sqlite3.Connection:
    """A database of version 30 with the rows the functions of `fill` insert and the settings given,
    and migrations 31 and 32 run on it."""
    db = old_database(tmp_path / DB_NAME, FixedClock())
    for key, value in (settings or {}).items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    for rows in fill:
        rows(db)
    run(db, step_31)
    run(db, _v32)
    return db


def radios_of(db: sqlite3.Connection) -> dict[str, str]:
    return {str(name): str(radios) for name, radios in db.execute("SELECT name, radios FROM own_object")}


# ---- one shape of old database for each test

def test_an_empty_database_gets_the_two_tables_and_loses_the_old_columns_and_the_note_of_31(tmp_path: Path) -> None:
    db = at_32(tmp_path)
    assert "_m31" in tables(db)
    run(db, _v33)
    assert {"station_radio", "station_path"} <= tables(db) and "_m31" not in tables(db) and "station_pref_old" not in tables(db)
    assert not {"heard_fm", "heard_hf", "last_fm_at", "last_hf_at", "last_path"} & set(columns(db, "station")) and "path" not in columns(db, "station_pref")
    assert "radios" in columns(db, "own_object") and "radio" not in columns(db, "own_object")
    assert [db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("station_radio", "station_path", "station_pref", "own_object", "radio")] == [0, 0, 0, 0, 0]
    db.close()


def test_what_each_radio_heard_of_a_station_is_its_row_and_the_path_goes_to_the_radio_that_heard_it_last(tmp_path: Path) -> None:
    db = at_32(tmp_path, stations, settings=BOTH_ON)
    before = whole(db, "station", ("heard_fm", "heard_hf", "last_fm_at", "last_hf_at", "last_path"))
    run(db, _v33)
    assert heard_by(db) == HEARD
    assert heard_by(db)["OH2TIE"][1][2] == "OH2RCH-2*" and heard_by(db)["OH2TIE"][2][2] == "", "heard on both at the same time: the path is the FM radio's"
    assert "OH2NET" not in heard_by(db), "a station known from the internet alone has no row: no radio heard it"
    assert whole(db, "station", ()) == before and len(before) == len(STATIONS), "every other column of every station is what it was"
    assert db.execute("SELECT COUNT(*) FROM station_radio WHERE radio_id NOT IN (SELECT id FROM radio)").fetchone() == (0,), "every radio a row names is in the table"
    db.close()


def test_a_station_heard_on_the_fm_radio_alone_has_one_row_with_its_path_where_there_is_no_radio_two(tmp_path: Path) -> None:
    fm_only = [row for row in STATIONS if row[3] == 0]
    db = at_32(tmp_path, lambda d: [d.execute(STATION, (call, STAMP, LATER, STAMP, fm + net, path, fm, net, fm_at, STAMP if net else None, fm, 0, fm_at, None, LATER)) for call, path, fm, _, fm_at, _, net in fm_only],
               settings={"station/call": "OH2GBA"})
    assert db.execute("SELECT id FROM radio").fetchall() == [(1,)]
    run(db, _v33)
    assert heard_by(db) == {"OH2FM": {1: (4, LATER, "WIDE1-1*")}, "OH2DIRECT": {1: (2, STAMP, "")}} and db.execute("SELECT COUNT(*) FROM station").fetchone() == (3,)
    db.close()


def test_a_count_of_the_hf_radio_is_kept_as_radio_twos_even_where_migration_31_made_no_radio_two(tmp_path: Path) -> None:
    """Nothing is dropped for want of a radio's row: the HF radio is radio 2 by the
    constants, and the row says so."""
    db = at_32(tmp_path, stations, settings=BOTH_ON)
    db.execute("DELETE FROM radio WHERE id = 2")
    run(db, _v33)
    assert heard_by(db) == HEARD
    db.close()


def test_the_path_of_a_station_is_its_path_on_radio_one_and_a_row_that_said_only_a_path_is_gone(tmp_path: Path) -> None:
    db = at_32(tmp_path, prefs, settings={"station/call": "OH2GBA"})
    before = whole(db, "station_pref", ("path",))
    run(db, _v33)
    assert db.execute("SELECT call, radio_id, path, updated_at FROM station_path ORDER BY call").fetchall() == [("OH2ALL", 1, "WIDE2-1", LATEST), ("OH2BOTH", 1, "OH2RCH-2", LATER), ("OH2DIRECT", 1, "", LATER),
                                                                                                          ("OH2PATH", 1, "WIDE1-1,WIDE2-1", STAMP)], "an empty path is direct, and is a path"
    assert [row[0] for row in db.execute("SELECT call FROM station_pref ORDER BY call")] == ["EMAIL-2", "OH2ALERT", "OH2ALL", "OH2BOTH", "OH2OLD"], "OH2PATH and OH2DIRECT said only a path: their rows are gone"
    assert whole(db, "station_pref", ()) == [row for row in before if row[0] not in ("OH2PATH", "OH2DIRECT")], "RF only, the alerts and what older versions kept are what they were"
    assert said_of(db) == [("EMAIL-2", None, 1), ("OH2ALERT", None, 0), ("OH2ALL", "WIDE2-1", 1), ("OH2BOTH", "OH2RCH-2", 1), ("OH2DIRECT", "", 0), ("OH2OLD", None, 0), ("OH2PATH", "WIDE1-1,WIDE2-1", 0)]
    db.execute("INSERT INTO station_pref (call, rf_only, updated_at) VALUES ('OH2NEW', 1, ?)", (STAMP,))
    for statement, check in (("INSERT INTO station_pref (call, updated_at) VALUES ('OH2NIL', '2026-10-21T12:00:00.000000Z')", "station_pref_says_something"),
                             ("INSERT INTO station_path (call, radio_id, path, updated_at) VALUES ('OH2X', 1, 'wide1-1', '2026-10-21T12:00:00.000000Z')", "station_path_form"),
                             ("INSERT INTO station_path (call, radio_id, path, updated_at) VALUES ('', 1, '', '2026-10-21T12:00:00.000000Z')", "station_path_call_present"),
                             ("INSERT INTO station_path (call, radio_id, path, updated_at) VALUES ('OH2X', 1, '', 'noon')", "station_path_updated_form"),
                             ("INSERT INTO station_path (call, radio_id, path, updated_at) VALUES ('OH2PATH', 1, '', '2026-10-21T12:00:00.000000Z')", "UNIQUE"),
                             ("INSERT INTO station_radio (call, radio_id, heard) VALUES ('OH2X', 1, -1)", "station_radio_heard_count")):
        with pytest.raises(sqlite3.IntegrityError, match=check):
            db.execute(statement)
    # The same station, another radio: a path of its own
    db.execute("INSERT INTO station_path (call, radio_id, path, updated_at) VALUES ('OH2PATH', 2, 'OH2RCH-2', ?)", (STAMP,))
    db.close()


def test_with_both_radios_enabled_an_object_is_on_the_radios_its_word_named(tmp_path: Path) -> None:
    db = at_32(tmp_path, objects, settings=BOTH_ON)
    before = whole(db, "own_object", ("radio",))
    run(db, _v33)
    assert radios_of(db) == {"ONFM": "1", "ONHF": "2", "ONBOTH": "1,2"}
    assert whole(db, "own_object", ("radios",)) == before, "every other column of every object is what it was"
    db.close()


def test_with_one_radio_enabled_an_object_keeps_the_radios_its_word_named(tmp_path: Path) -> None:
    """The operator's choice outlives a radio that is off at the update: an object on hf or on both
    keeps those radios, and goes out on the radio that is on meanwhile, as it did (the sender puts
    an object none of whose radios is on onto the main radio); when the other radio is switched on
    again the object is where the operator put it."""
    db = at_32(tmp_path, objects, settings={"station/call": "OH2GBA"})
    assert db.execute("SELECT id, enabled FROM radio ORDER BY id").fetchall() == [(1, 1), (2, 0)], "an object on hf made migration 31 make radio 2; it is not enabled"
    run(db, _v33)
    assert radios_of(db) == {"ONFM": "1", "ONHF": "2", "ONBOTH": "1,2"}
    db.close()


def test_with_the_hf_radio_alone_enabled_an_object_keeps_the_radios_its_word_named(tmp_path: Path) -> None:
    db = at_32(tmp_path, objects, settings={"fm/enabled": "false", "hf/enabled": "true"})
    run(db, _v33)
    assert radios_of(db) == {"ONFM": "1", "ONHF": "2", "ONBOTH": "1,2"}
    db.close()


def test_with_no_radio_enabled_an_object_keeps_the_radios_its_word_named(tmp_path: Path) -> None:
    db = at_32(tmp_path, objects, settings={"fm/enabled": "false", "hf/enabled": "false"})
    run(db, _v33)
    assert radios_of(db) == {"ONFM": "1", "ONHF": "2", "ONBOTH": "1,2"}
    db.close()


@pytest.mark.parametrize("fm_enabled", [0, 1], ids=["radio 1 off", "radio 1 on"])
def test_without_a_radio_two_an_object_on_hf_or_on_both_is_on_radio_one(tmp_path: Path, fm_enabled: int) -> None:
    db = at_32(tmp_path, objects, settings={"station/call": "OH2GBA"})
    db.execute("DELETE FROM radio WHERE id = 2")
    db.execute("UPDATE radio SET enabled = ?", (fm_enabled,))
    run(db, _v33)
    assert radios_of(db) == {"ONFM": "1", "ONHF": "1", "ONBOTH": "1"}
    db.close()


def test_objects_in_a_database_without_settings_are_on_radio_one_which_31_made(tmp_path: Path) -> None:
    db = at_32(tmp_path, objects)
    assert db.execute("SELECT id, kind, enabled FROM radio ORDER BY id").fetchall() == [(1, "fm", 1), (2, "hf", 0)], \
        "objects are rows of an installation: migration 31 makes radio 1, and radio 2 for the objects on hf and both"
    run(db, _v33)
    assert radios_of(db) == {"ONFM": "1", "ONHF": "2", "ONBOTH": "1,2"}, "each object keeps the radios its word named, radio 2 off or not"
    assert db.execute("INSERT INTO radio (kind, type, enabled, position) VALUES ('fm', 'kiss', 1, 3)").lastrowid == 3, "a radio added later inherits nothing"
    db.close()


def message_on_hf(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO message (at, direction, from_call, to_call, text, state, route, radio) VALUES (?, 'in', 'OH2HF', 'OH2GBA', 'hi', 'received', '', 'hf')", (STAMP,))
    db.execute("INSERT INTO message (at, direction, from_call, to_call, text, state, route, radio) VALUES (?, 'out', 'OH2GBA', 'OH2FM', 'hi', 'acked', '', '')", (STAMP,))
    db.execute("INSERT INTO message_attempt (message_id, attempt, sent_at, path, radio) VALUES (2, 1, ?, 'WIDE1-1', 'fm')", (STAMP,))


@pytest.mark.parametrize("fill, radios", [((stations,), [(1, 1), (2, 0)]), ((prefs,), [(1, 1)]), ((objects,), [(1, 1), (2, 0)]), ((message_on_hf,), [(1, 1), (2, 0)]),
                                          ((stations, prefs, objects, message_on_hf), [(1, 1), (2, 0)])],
                         ids=["stations, one heard on hf alone", "preferences", "objects", "messages", "all of them"])
def test_a_database_without_settings_and_packets_names_only_radios_the_table_has(tmp_path: Path, fill: tuple[Any, ...], radios: list[tuple[int, int]]) -> None:
    """No settings row (none was ever changed) and no packet (the prune took them): the stations,
    preferences, objects and messages are an installation's, so migration 31 makes the radios their
    rows name (radio 2 for a station that HF heard alone too), and every id 32 and 33 write is a
    radio the table has: none is left for a radio the operator adds later to inherit."""
    db = at_32(tmp_path, *fill)
    run(db, _v33)
    assert db.execute("SELECT id, enabled FROM radio ORDER BY id").fetchall() == radios
    assert db.execute("PRAGMA foreign_key_check").fetchall() == [], "no row of station_radio, station_path, message or message_attempt names a radio the table lacks"
    assert all(part in {str(r) for r, _ in radios} for (ids,) in db.execute("SELECT radios FROM own_object") for part in str(ids).split(","))
    db.close()


# ---- a step that doubts, or is cut short

class Tampered:
    """A connection on which one statement of the step does nothing."""

    def __init__(self, db: sqlite3.Connection, skipped: str) -> None:
        self.db, self.skipped = db, skipped

    def execute(self, statement: str, *args: Any) -> Any:
        return self.db.execute("SELECT 1 WHERE 0") if statement.startswith(self.skipped) else self.db.execute(statement, *args)


@pytest.mark.parametrize("skipped, told", [("INSERT INTO station_path", "7 rows, 4 with a path, 2 with nothing else: the new one got 5 of which 5 are the same, and station_path 0 of the paths"),
                                           ("INSERT INTO station_pref", "the new one got 0 of which 0 are the same, and station_path 4 of the paths")], ids=["the paths were not moved", "the rows were not kept"])
def test_a_step_that_doubts_what_it_moved_raises_and_the_rollback_leaves_everything_as_it_was(tmp_path: Path, skipped: str, told: str) -> None:
    db = at_32(tmp_path, stations, prefs, objects, settings=BOTH_ON)
    shape = db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    rows = {table: db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() for table in ("station", "station_pref", "own_object", "_m31")}
    with pytest.raises(StoreError, match=f"{told}; nothing was changed"):
        run(db, lambda d: _v33(Tampered(d, skipped)))  # type: ignore[arg-type]
    assert db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall() == shape and {table: db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() for table in rows} == rows
    run(db, _v33)
    assert heard_by(db) == HEARD and len(said_of(db)) == len(PREFS) and radios_of(db) == {"ONFM": "1", "ONHF": "2", "ONBOTH": "1,2"}, "the next run finishes it"
    db.close()


def test_a_step_that_is_cut_short_leaves_the_database_as_it_was_and_the_next_run_finishes_it(tmp_path: Path) -> None:
    """The runner gives the step a transaction of its own: the stations are moved and their columns
    dropped when the table in the way stops it, and none of that stays."""
    db = at_32(tmp_path, stations, prefs, objects, settings=BOTH_ON)
    shape = db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    rows = {table: db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() for table in ("station", "station_pref", "own_object")}
    db.execute("CREATE TABLE station_pref_old (x TEXT)")
    with pytest.raises(sqlite3.OperationalError, match="station_pref_old"):
        run(db, _v33)
    db.execute("DROP TABLE station_pref_old")
    assert db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall() == shape and {table: db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() for table in rows} == rows
    db.close()
    # The next start: another connection finds the file of before
    again = sqlite3.connect(str(tmp_path / DB_NAME), isolation_level=None)
    run(again, _v33)
    assert heard_by(again) == HEARD and "_m31" not in tables(again)
    again.close()


def test_the_step_does_not_need_the_note_of_31_and_reads_the_radios_from_their_table(tmp_path: Path) -> None:
    db = at_32(tmp_path, objects, settings=BOTH_ON)
    db.execute("DROP TABLE _m31")
    run(db, _v33)
    assert radios_of(db) == {"ONFM": "1", "ONHF": "2", "ONBOTH": "1,2"}
    db.close()


def test_the_way_back_gives_the_columns_again_and_the_step_then_makes_the_same_database(tmp_path: Path) -> None:
    """`undo_33` is what tests/support/migrated.step_back uses below 33, so that the test of an
    older migration runs this step over its rows."""
    db = at_32(tmp_path, stations, prefs, objects, settings=BOTH_ON)
    keys = {"station": "call", "station_pref": "call", "own_object": "name", "_m31": "hf_exists"}
    before = {table: db.execute(f"SELECT {', '.join(sorted(columns(db, table)))} FROM {table} ORDER BY {key}").fetchall() for table, key in keys.items()}
    run(db, _v33)
    after = db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    undo_33(db)
    assert {table: db.execute(f"SELECT {', '.join(sorted(columns(db, table)))} FROM {table} ORDER BY {key}").fetchall() for table, key in keys.items()} == before
    assert not {"station_radio", "station_path", "station_pref_33"} & tables(db)
    run(db, _v33)
    assert db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall() == after and heard_by(db) == HEARD and len(said_of(db)) == len(PREFS)
    db.close()


def test_the_way_back_through_32_and_33_gives_the_tables_of_version_30_word_for_word(tmp_path: Path) -> None:
    """After 33 and 32 are taken back the tables are those of a file of version 30, column by column
    and in the text of their statements, so that a test of an older migration cannot insert a row
    that no file of that version takes (a station without its last path); and the station's last
    path is that of the radio that heard it last, whichever radio's row has one."""
    (tmp_path / "fresh").mkdir()
    fresh = old_database(tmp_path / "fresh" / DB_NAME)
    db = at_32(tmp_path, stations, settings=BOTH_ON)
    run(db, _v33)
    # A path on each radio, as the station book keeps them.
    db.execute("UPDATE station_radio SET last_path = 'OH2RCH-2*' WHERE call = 'OH2HFLAST' AND radio_id = 1")
    undo_33(db)
    undo_32(db)
    for table in ("radio_setting", "radio", "_m31"):
        db.execute(f"DROP TABLE {table}")
    schema = "SELECT name, sql FROM sqlite_master ORDER BY name"
    assert db.execute(schema).fetchall() == fresh.execute(schema).fetchall()
    assert all(db.execute(f"PRAGMA table_xinfo({t})").fetchall() == fresh.execute(f"PRAGMA table_xinfo({t})").fetchall() for t in ("station", "packet", "message", "message_attempt"))
    assert db.execute("SELECT last_path FROM station WHERE call = 'OH2HFLAST'").fetchone() == ("WIDE1-1",), "radio 2 heard it last: its path, not radio 1's"
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL constraint failed: station.last_path"):
        db.execute("INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, first_heard, last_heard, last_status, last_comment, packets) VALUES ('OH2NEW', 'station', '', '/', '-', ?, ?, '', '', 0)", (STAMP, STAMP))
    fresh.close()
    db.close()


# ---- the stores on the database the step leaves

async def test_the_logs_read_what_the_step_left_and_write_beside_it(tmp_path: Path) -> None:
    db = at_32(tmp_path, stations, prefs, objects, settings=BOTH_ON)
    run(db, _v33)
    stepped(db)
    db.close()
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    packets, messages, own = PacketLog(store.db, clock), MessageLog(store.db, clock), OwnLog(store.db, clock)
    found = {s.call: s for s in await packets.stations()}
    assert {call: {radio: (heard.count, None if heard.last_at is None else packetcodec.stamp(heard.last_at), ",".join(heard.last_path)) for radio, heard in s.heard_by.items()} for call, s in found.items() if s.heard_by} == HEARD
    assert found["OH2HFLAST"].last_path == ("WIDE1-1",) and found["OH2FMLAST"].last_path == ("OH2RCH-2*", "WIDE2-1") and found["OH2NET"].heard_by == {} and found["OH2NET"].heard_is == 7
    assert found["OH2FM"].heard_on(1) == RadioHeard(4, parse_stamp(LATER), ("WIDE1-1*",)) and (found["OH2FM"].snr, found["OH2FM"].last_status) == (-3.5, "QRV")
    assert await messages.prefs() == {"EMAIL-2": (None, True, None), "OH2ALERT": (None, False, Alert(True, 25, True)), "OH2ALL": ("WIDE2-1", True, Alert(True, None, False)), "OH2BOTH": ("OH2RCH-2", True, None),
                                      "OH2DIRECT": ("", False, None), "OH2PATH": ("WIDE1-1,WIDE2-1", False, None)}, "what was said of each station, as it was said (the row that holds only an old count says nothing)"
    assert await messages.paths() == {"OH2ALL": {1: "WIDE2-1"}, "OH2BOTH": {1: "OH2RCH-2"}, "OH2DIRECT": {1: ""}, "OH2PATH": {1: "WIDE1-1,WIDE2-1"}}
    assert sorted((o.name, o.radios, o.qru_group) for o in await own.objects()) == [("ONBOTH", (1, 2), "RP70"), ("ONFM", (1,), "RP70"), ("ONHF", (2,), "RP70")]
    station = found["OH2FM"]
    station.heard_by[2] = RadioHeard(1, parse_stamp(LATEST), ())
    packets.save_station(station)
    assert {s.call: s for s in await packets.stations()}["OH2FM"] == station
    assert await sql(store, "SELECT radio_id, heard, last_path FROM station_radio WHERE call = 'OH2FM' ORDER BY radio_id") == [(1, 4, "WIDE1-1*"), (2, 1, "")], "each radio keeps its own path"
