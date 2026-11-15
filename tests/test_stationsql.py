"""What each radio heard of a station and the path of a station on a radio (neoaprs/stationsql.py: the tables `station_radio` and `station_path` of migration 33), statement by statement on a
connection, and what the message log makes of them (neoaprs/messagelog.py, messagesql.py): what is said of a station is its path on a radio beside RF only and the alert, each kept where it belongs,
replaced, taken away alone, and forgotten with its path on radio 1 while its paths on other radios stay."""
import sqlite3
from pathlib import Path

import pytest

from neoaprs.messagelog import MessageLog
from neoaprs.packetcodec import parse_stamp
from neoaprs.packetlog import station_row
from neoaprs.packetsql import upsert_station
from neoaprs.pref import Alert
from neoaprs.radiospec import FM_ID, RadioHeard
from neoaprs.station import Station
from neoaprs.stationsql import (clear_station_path, delete_station_radios, delete_station_radios_but, put_station_path, put_station_radios, station_paths, station_radio_rows,
                                upsert_station_radio)
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated32 import SHAPE_IDS, SHAPES, connect, shaped
from tests.support.storedb import log_at

STAMP = "2026-10-21T12:00:00.000000Z"
LATER = "2026-10-21T12:30:00.000000Z"
NEW = pytest.mark.parametrize("shape", [True], indirect=True, ids=SHAPE_IDS.get)       # a test of the shape of migration 33 alone


@pytest.fixture(autouse=True, params=SHAPES, ids=SHAPE_IDS.get)
def shape(request: pytest.FixtureRequest) -> bool:
    """The shape of the database the stores write in this test: False that of version 30, True that of migration 33 (`shaped` makes the file to match)."""
    return bool(request.param)


def database(tmp_path: Path) -> sqlite3.Connection:
    """A connection of the test's own to a new database of the shape of migration 33, with today's two radios."""
    return connect(shaped(tmp_path / DB_NAME))


async def opened(tmp_path: Path) -> tuple[MessageLog, FixedClock]:
    log, _, clock = await log_at(shaped(tmp_path / DB_NAME).parent, MessageLog)
    return log, clock


# ---- what each radio heard of a station

@NEW
def test_what_a_radio_heard_of_a_station_is_kept_replaced_and_read_back_by_station_and_radio(tmp_path: Path) -> None:
    db = database(tmp_path)
    assert station_radio_rows(db) == []
    upsert_station_radio(db, "OH2RDG", 2, 1, LATER, "")
    upsert_station_radio(db, "OH2RDG", 1, 3, STAMP, "OH2RCH-2*,WIDE2-1")
    upsert_station_radio(db, "OH2AAA", 1, 1, None, "")
    assert station_radio_rows(db) == [("OH2AAA", 1, 1, None, ""), ("OH2RDG", 1, 3, STAMP, "OH2RCH-2*,WIDE2-1"), ("OH2RDG", 2, 1, LATER, "")]
    upsert_station_radio(db, "OH2RDG", 1, 4, LATER, "WIDE1-1")
    assert station_radio_rows(db)[1] == ("OH2RDG", 1, 4, LATER, "WIDE1-1"), "one row for a station and a radio"
    with pytest.raises(sqlite3.IntegrityError, match="station_radio_heard_count"):
        upsert_station_radio(db, "OH2RDG", 1, -1, LATER, "")
    db.close()


@NEW
def test_the_rows_of_a_station_are_put_as_they_are_now_and_the_row_of_a_radio_not_among_them_goes(tmp_path: Path) -> None:
    db = database(tmp_path)
    put_station_radios(db, "OH2RDG", [("OH2RDG", 1, 3, STAMP, "WIDE1-1"), ("OH2RDG", 2, 1, LATER, "")])
    put_station_radios(db, "OH2AAA", [("OH2AAA", 2, 7, LATER, "")])
    put_station_radios(db, "OH2RDG", [("OH2RDG", 1, 4, LATER, "")])
    assert station_radio_rows(db) == [("OH2AAA", 2, 7, LATER, ""), ("OH2RDG", 1, 4, LATER, "")], "radio 2 heard OH2RDG no more; the other station's row is not touched"
    put_station_radios(db, "OH2RDG", [])
    assert station_radio_rows(db) == [("OH2AAA", 2, 7, LATER, "")]
    db.close()


@NEW
def test_a_station_row_kept_without_what_its_radios_heard_leaves_their_rows_as_they_were(tmp_path: Path) -> None:
    """`upsert_station(db, row)`, the call of before the radios, keeps the station's counts as it did: only `heard=` puts the rows of `station_radio` (an empty one takes them away)."""
    db = database(tmp_path)
    at = parse_stamp(STAMP)
    row = station_row(Station("OH2RDG", first_heard=at, last_heard=at, heard_by={FM_ID: RadioHeard(3, at, ("WIDE1-1",))}))
    upsert_station(db, row, heard=[("OH2RDG", 1, 3, STAMP, "WIDE1-1"), ("OH2RDG", 2, 1, LATER, "")])
    upsert_station(db, row)
    assert station_radio_rows(db) == [("OH2RDG", 1, 3, STAMP, "WIDE1-1"), ("OH2RDG", 2, 1, LATER, "")], "the old call wipes nothing"
    upsert_station(db, row, heard=[])
    assert station_radio_rows(db) == [] and db.execute("SELECT call FROM station").fetchall() == [("OH2RDG",)]
    db.close()


@NEW
def test_what_the_radios_heard_is_deleted_with_a_station_and_with_all_but_one(tmp_path: Path) -> None:
    db = database(tmp_path)
    for call in ("OH2GBA", "OH2AAA", "OH2BBB"):
        put_station_radios(db, call, [(call, 1, 1, STAMP, ""), (call, 2, 1, STAMP, "")])
    assert delete_station_radios(db, "OH2AAA") == 2 and delete_station_radios(db, "NOBODY") == 0
    assert [row[:2] for row in station_radio_rows(db)] == [("OH2BBB", 1), ("OH2BBB", 2), ("OH2GBA", 1), ("OH2GBA", 2)]
    assert delete_station_radios_but(db, "OH2GBA") == 2 and [row[:2] for row in station_radio_rows(db)] == [("OH2GBA", 1), ("OH2GBA", 2)]
    db.close()


# ---- the path of a station on a radio

@NEW
def test_the_path_of_a_station_on_a_radio_is_kept_replaced_and_cleared_for_that_radio_alone(tmp_path: Path) -> None:
    db = database(tmp_path)
    assert station_paths(db) == []
    put_station_path(db, "OH2RDG", 1, "WIDE1-1,WIDE2-1", STAMP)
    put_station_path(db, "OH2RDG", 2, "", STAMP)
    put_station_path(db, "OH2AAA", 1, "OH2RCH-2", STAMP)
    assert station_paths(db) == [("OH2AAA", 1, "OH2RCH-2"), ("OH2RDG", 1, "WIDE1-1,WIDE2-1"), ("OH2RDG", 2, "")], "an empty path is direct, and is a path"
    put_station_path(db, "OH2RDG", 1, "OH2RCH-2", LATER)
    assert db.execute("SELECT path, updated_at FROM station_path WHERE call = 'OH2RDG' AND radio_id = 1").fetchall() == [("OH2RCH-2", LATER)], "one row for a station and a radio"
    assert clear_station_path(db, "OH2RDG", 1) == 1 and clear_station_path(db, "OH2RDG", 1) == 0 and clear_station_path(db, "NOBODY", 1) == 0
    assert station_paths(db) == [("OH2AAA", 1, "OH2RCH-2"), ("OH2RDG", 2, "")], "its path on the other radio stays"
    with pytest.raises(sqlite3.IntegrityError, match="station_path_form"):
        put_station_path(db, "OH2AAA", 1, "wide1-1", LATER)
    db.close()


# ---- what the message log makes of them: both shapes hold what tests/test_messagelog.py holds of the one before

async def test_what_is_said_of_a_station_is_kept_replaced_and_forgotten_and_an_empty_path_is_not_none(tmp_path: Path, shape: bool) -> None:
    log, clock = await opened(tmp_path)
    assert await log.prefs() == {}
    assert await log.save_pref("OH2RDG", "WIDE1-1,WIDE2-1") and await log.save_pref("OH2XYZ", "") and await log.save_pref("OH2ABC", "WIDE2-1", True)
    assert await log.save_pref("EMAIL-2", None, True) and await log.save_pref("OH2WATCH", None, False, Alert(True, 25, False))
    assert await log.prefs() == {"OH2RDG": ("WIDE1-1,WIDE2-1", False, None), "OH2XYZ": ("", False, None), "OH2ABC": ("WIDE2-1", True, None), "EMAIL-2": (None, True, None), "OH2WATCH": (None, False, Alert(True, 25, False))}
    clock.advance(60)
    assert await log.save_pref("OH2RDG", "OH2RCH-2")
    assert (await log.prefs())["OH2RDG"] == ("OH2RCH-2", False, None)
    assert await log.save_pref("OH2ABC", None, True) and (await log.prefs())["OH2ABC"] == (None, True, None), "the path taken away, RF only stays"
    assert await log.save_pref("OH2ABC", "WIDE2-1", False) and (await log.prefs())["OH2ABC"] == ("WIDE2-1", False, None), "RF only taken away, the path stays"
    assert await log.forget_pref("OH2XYZ") and await log.forget_pref("NOBODY") and await log.forget_pref("OH2WATCH")
    assert set(await log.prefs()) == {"OH2RDG", "OH2ABC", "EMAIL-2"}
    assert log.db is not None
    table = "station_path" if shape else "station_pref"
    assert await log.db.read(lambda conn: conn.execute(f"SELECT updated_at FROM {table} WHERE call = 'OH2RDG'").fetchone()[0]) == "2026-10-21T12:01:00.000000Z"


@pytest.mark.expects_errors
async def test_a_preference_the_tables_refuse_is_not_kept_and_the_caller_is_told(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    assert not await log.save_pref("OH2RDG", "wide1-1") and not await log.save_pref("OH2RDG", None)
    assert await log.prefs() == {}
    assert not await MessageLog().save_pref("OH2RDG", "") and not await MessageLog().forget_pref("OH2RDG") and await MessageLog().prefs() == {}


@NEW
@pytest.mark.expects_errors
async def test_the_path_is_in_its_own_table_by_radio_and_rf_only_and_the_alert_stay_by_station(tmp_path: Path) -> None:
    log, clock = await opened(tmp_path)
    store_of = log.db
    assert store_of is not None

    async def rows(table: str, columns: str) -> list[tuple[object, ...]]:
        return await store_of.read(lambda conn: [tuple(r) for r in conn.execute(f"SELECT {columns} FROM {table} ORDER BY 1, 2")])
    assert await log.save_pref("OH2PATH", "WIDE1-1") and await log.save_pref("OH2BOTH", "OH2RCH-2", True) and await log.save_pref("EMAIL-2", None, True)
    assert await rows("station_pref", "call, rf_only") == [("EMAIL-2", 1), ("OH2BOTH", 1)], "a station of which only a path is said has no row here"
    assert await rows("station_path", "call, radio_id, path") == [("OH2BOTH", 1, "OH2RCH-2"), ("OH2PATH", 1, "WIDE1-1")]
    assert await log.save_pref("OH2BOTH", "OH2RCH-2", False), "RF only off: the row of station_pref goes, the path stays"
    assert await rows("station_pref", "call, rf_only") == [("EMAIL-2", 1)] and await log.prefs() == {"EMAIL-2": (None, True, None), "OH2BOTH": ("OH2RCH-2", False, None), "OH2PATH": ("WIDE1-1", False, None)}
    assert not await log.save_pref("OH2BOTH", None) and await log.prefs() == {"EMAIL-2": (None, True, None), "OH2BOTH": ("OH2RCH-2", False, None), "OH2PATH": ("WIDE1-1", False, None)}, \
        "nothing at all said is refused, as it was, and what was kept is as it was"
    assert "path" not in [c[1] for c in await rows("pragma_table_info('station_pref')", "cid, name")]


@NEW
async def test_a_station_has_a_path_on_each_radio_and_the_old_call_reads_and_writes_radio_ones(tmp_path: Path) -> None:
    log, clock = await opened(tmp_path)
    assert await log.paths() == {}
    assert await log.save_path("OH2RDG", 1, "WIDE1-1,WIDE2-1") and await log.save_path("OH2RDG", 2, "") and await log.save_path("OH2LORA", 2, "OH2RCH-2")
    assert await log.paths() == {"OH2RDG": {1: "WIDE1-1,WIDE2-1", 2: ""}, "OH2LORA": {2: "OH2RCH-2"}}
    assert await log.prefs() == {"OH2RDG": ("WIDE1-1,WIDE2-1", False, None)}, "without a radio named: the paths on radio 1, as every caller of today asks"
    assert await log.prefs(radio=2) == {"OH2RDG": ("", False, None), "OH2LORA": ("OH2RCH-2", False, None)}
    assert await log.save_pref("OH2RDG", "OH2RCH-2", True, radio=2) and await log.save_pref("OH2RDG", None, True)
    assert await log.paths() == {"OH2RDG": {2: "OH2RCH-2"}, "OH2LORA": {2: "OH2RCH-2"}}, "the path on radio 1 taken away, the one on radio 2 replaced"
    assert await log.prefs() == {"OH2RDG": (None, True, None)} and await log.prefs(radio=2) == {"OH2RDG": ("OH2RCH-2", True, None), "OH2LORA": ("OH2RCH-2", False, None)}
    clock.advance(60)
    assert await log.save_path("OH2LORA", 2, "WIDE1-1") and await log.forget_path("OH2LORA", 1) and (await log.paths())["OH2LORA"] == {2: "WIDE1-1"}
    assert log.db is not None
    assert await log.db.read(lambda conn: conn.execute("SELECT updated_at FROM station_path WHERE call = 'OH2LORA'").fetchone()[0]) == "2026-10-21T12:01:00.000000Z"
    assert await log.forget_path("OH2LORA", 2) and "OH2LORA" not in await log.paths()
    assert await log.save_path("OH2RDG", 1, "WIDE1-1") and await log.forget_pref("OH2RDG")
    assert await log.paths() == {"OH2RDG": {2: "OH2RCH-2"}} and await log.prefs() == {}, "forgetting what is said of a station without a radio named takes RF only and its path on radio 1"
    assert await log.prefs(radio=2) == {"OH2RDG": ("OH2RCH-2", False, None)}, "its path on radio 2 stays: the operator gave it there and did not take it away"


@NEW
@pytest.mark.expects_errors
async def test_a_path_the_table_refuses_is_not_kept_and_a_log_without_a_database_says_no(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    assert not await log.save_path("OH2RDG", 1, "wide1-1") and await log.paths() == {}
    assert not await MessageLog().save_path("OH2RDG", 1, "") and not await MessageLog().forget_path("OH2RDG", 1) and await MessageLog().paths() == {}


@NEW
async def test_a_row_that_holds_only_what_an_older_version_kept_says_nothing_and_a_path_beside_it_is_read(tmp_path: Path) -> None:
    log, _ = await opened(tmp_path)
    assert log.db is not None
    await log.db.write(lambda conn: conn.execute("INSERT INTO station_pref (call, attempts, updated_at) VALUES ('OH2OLD', 3, ?), ('OH2BOTH', 4, ?)", (STAMP, STAMP)))
    assert await log.prefs() == {}
    assert await log.save_path("OH2BOTH", 1, "WIDE2-1")
    assert await log.prefs() == {"OH2BOTH": ("WIDE2-1", False, None)}
    assert await log.save_pref("OH2BOTH", "WIDE1-1", True) and await log.save_pref("OH2BOTH", "WIDE1-1", False) and await log.prefs() == {"OH2BOTH": ("WIDE1-1", False, None)}
    assert await sql_rows(log, "SELECT call, attempts, rf_only FROM station_pref ORDER BY call") == [("OH2BOTH", 4, 0), ("OH2OLD", 3, 0)], "RF only set and taken away again: what the older version kept is still there"


async def sql_rows(log: MessageLog, statement: str) -> list[tuple[object, ...]]:
    assert log.db is not None
    return await log.db.read(lambda conn: [tuple(r) for r in conn.execute(statement)])

