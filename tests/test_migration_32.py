"""Migration 32 (neoaprs/migrationsteps32.py): packets, messages and attempts name their radio by
its id in the table `radio` instead of by a word. The step runs as the runner runs it on a version
30 database that migration 31 has run on (tests/support/migrated32.py); an interrupted step is
finished by the next run.
"""
import logging
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from neoaprs import ax25
from neoaprs.chain import Attempt
from neoaprs.dberror import StoreError
from neoaprs.message import MessageRecord
from neoaprs.messagelog import MessageLog
from neoaprs.migrationsteps32 import _v32, _v33
from neoaprs.packet import Packet, Status
from neoaprs.packetcodec import parse_stamp
from neoaprs.packetlog import PacketLog
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated32 import columns, old_database, run, step_31, stepped, tables, undo_32
from tests.support.storedb import sql, store_at

STAMP = "2026-10-21T12:00:00.000000Z"
LATER = "2026-10-21T12:30:00.000000Z"
FRAME = ax25.encode(ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2RDG"), (), info=b">hi"))
DECODED = '{"type":"status","text":"hi","timestamp":null,"locator":null,"frequency":null}'
PACKET = "INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded, via, radio, snr, rssi) VALUES (?, ?, ?, ?, 'APRS', '', 'status', 'status hi', ?, ?, ?, ?, ?)"
MESSAGE = "INSERT INTO message (at, direction, from_call, to_call, text, msg_id, state, attempts, route, radio) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?)"
ATTEMPT = "INSERT INTO message_attempt (message_id, attempt, sent_at, path, radio) VALUES (?, ?, ?, ?, ?)"
PACKETS = [("in", "OH2RDG", "rf", "fm", None, None), ("in", "Q3TKU", "rf", "hf", -2.5, -112.0), ("in", "OH2NET", "is", "", None, None), ("out", "OH2GBA", "rf", "fm", None, None),
           ("in", "OH7JHF-1", "rf-gated", "fm", None, None), ("in", "QDUMMY", "dummy", "fm", None, None), ("in", "OH2OLD", "rf", "", None, None), ("out", "OH2GBA", "rf", "hf", None, None)]
RADIOS = [1, 2, None, 1, 1, 1, 1, 2]                        # what 32 makes of the radio of each of PACKETS


def packets(db: sqlite3.Connection, rows: list[tuple[Any, ...]] = PACKETS) -> None:
    for n, (direction, source, via, radio, snr, rssi) in enumerate(rows):
        db.execute(PACKET, (STAMP if n % 2 == 0 else LATER, direction, FRAME, source, DECODED, via, radio, snr, rssi))


def messages(db: sqlite3.Connection) -> None:
    for at, direction, frm, to, text, msg_id, state, attempts, radio in ((STAMP, "out", "OH2GBA", "OH2RDG", "hello", "01", "acked", 2, ""), (LATER, "in", "OH2RDG", "OH2GBA", "hi there", "7", "received", 0, "fm"),
                                                                         (LATER, "in", "Q3TKU", "OH2GBA", "over hf", "8", "received", 0, "hf"), (LATER, "in", "OH2AAA", "OH2BBB", "not for us", None, "overheard", 0, "fm"),
                                                                         (LATER, "in", "OH2NET", "OH2GBA", "kept before the radios", "9", "received", 0, ""), (LATER, "out", "OH2GBA", "OH2XYZ", "never sent", "02", "failed", 0, "")):
        db.execute(MESSAGE, (at, direction, frm, to, text, msg_id, state, attempts, radio))
    for number, attempt, at, path, radio in ((1, 1, STAMP, "WIDE1-1", "fm"), (1, 2, LATER, "", "hf"), (1, 3, LATER, "", "")):
        db.execute(ATTEMPT, (number, attempt, at, path, radio))


def whole(db: sqlite3.Connection, table: str) -> list[tuple[Any, ...]]:
    """Every row of a table without its radio, by the table's own order."""
    names = [name for name in columns(db, table) if name not in ("radio", "radio_id")]
    return db.execute(f"SELECT {', '.join(names)} FROM {table} ORDER BY rowid").fetchall()


def radios(db: sqlite3.Connection, table: str) -> list[int | None]:
    return [row[0] for row in db.execute(f"SELECT radio FROM {table} ORDER BY rowid")]


def at_31(tmp_path: Path, *fill: Any, settings: dict[str, str] | None = None) -> sqlite3.Connection:
    """A database of version 30 with the rows the functions of `fill` insert and the settings given,
    and migration 31 run on it."""
    db = old_database(tmp_path / DB_NAME, FixedClock())
    for key, value in (settings or {}).items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    for rows in fill:
        rows(db)
    run(db, step_31)
    return db


# ---- one shape of old database for each test

def test_an_empty_database_gets_the_three_columns_and_no_radio(tmp_path: Path) -> None:
    db = at_31(tmp_path)
    run(db, _v32)
    assert [columns(db, table)["radio"] for table in ("packet", "message", "message_attempt")] == ["INTEGER"] * 3
    assert db.execute("SELECT COUNT(*) FROM radio").fetchone() == (0,), "a fresh installation has no radio, and 32 makes none"
    assert all("radio_id" not in columns(db, table) for table in ("packet", "message", "message_attempt"))
    db.close()


def test_a_packet_of_the_fm_radio_is_radio_ones_one_of_the_hf_radio_radio_twos_and_one_from_the_internet_none(tmp_path: Path) -> None:
    db = at_31(tmp_path, packets, settings={"hf/enabled": "true"})
    before = whole(db, "packet")
    run(db, _v32)
    assert radios(db, "packet") == RADIOS
    assert db.execute("SELECT source, via, radio, typeof(radio) FROM packet WHERE source IN ('OH2NET', 'OH2OLD') ORDER BY id").fetchall() == [("OH2NET", "is", None, "null"), ("OH2OLD", "rf", 1, "integer")], \
        "a packet of the air that named no radio is radio 1's, as migration 25 set the ones it found; the internet's stays without"
    assert whole(db, "packet") == before and len(before) == len(PACKETS), "every other column of every packet is what it was"
    assert db.execute("SELECT COUNT(*) FROM packet WHERE radio IS NOT NULL AND radio NOT IN (SELECT id FROM radio)").fetchone() == (0,), "every radio a packet names is in the table"
    db.close()


def test_where_hf_was_never_enabled_there_is_no_radio_two_and_nothing_names_it(tmp_path: Path) -> None:
    fm_only = [row for row in PACKETS if row[3] != "hf"]
    db = at_31(tmp_path, lambda d: packets(d, fm_only), settings={"station/call": "OH2GBA"})
    assert db.execute("SELECT id, kind FROM radio").fetchall() == [(1, "fm")]
    run(db, _v32)
    assert sorted(set(radios(db, "packet")), key=str) == [1, None] and radios(db, "packet").count(None) == 1
    db.close()


def test_where_hf_was_never_enabled_but_one_packet_came_on_it_the_packet_is_radio_twos(tmp_path: Path) -> None:
    db = at_31(tmp_path, lambda d: packets(d, [PACKETS[0], PACKETS[1]]), settings={"station/call": "OH2GBA"})
    assert db.execute("SELECT id, kind, enabled FROM radio ORDER BY id").fetchall() == [(1, "fm", 1), (2, "hf", 0)], "migration 31 makes radio 2 for it, not enabled"
    run(db, _v32)
    assert db.execute("SELECT source, radio FROM packet ORDER BY id").fetchall() == [("OH2RDG", 1), ("Q3TKU", 2)]
    db.close()


def test_a_message_that_came_in_and_an_attempt_name_the_radio_by_its_id_and_a_message_out_names_none(tmp_path: Path) -> None:
    db = at_31(tmp_path, messages, settings={"hf/enabled": "true"})
    before, attempts_before = whole(db, "message"), whole(db, "message_attempt")
    run(db, _v32)
    assert db.execute("SELECT id, direction, radio FROM message ORDER BY id").fetchall() == [(1, "out", None), (2, "in", 1), (3, "in", 2), (4, "in", 1), (5, "in", None), (6, "out", None)], \
        "one of ours has none (its attempts say), and neither has one kept before the radios were named"
    assert db.execute("SELECT message_id, attempt, radio FROM message_attempt ORDER BY message_id, attempt").fetchall() == [(1, 1, 1), (1, 2, 2), (1, 3, None)]
    assert whole(db, "message") == before and whole(db, "message_attempt") == attempts_before, "every other column of every row is what it was"
    db.close()


# ---- what the step leaves besides the rows

def test_the_tables_keep_their_indexes_their_checks_and_the_count_of_the_message_ids(tmp_path: Path) -> None:
    db = at_31(tmp_path, packets, messages, settings={"hf/enabled": "true"})
    db.execute("DELETE FROM message WHERE id = 6")
    indexes = db.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'index' ORDER BY name").fetchall()
    run(db, _v32)
    assert db.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'index' ORDER BY name").fetchall() == indexes
    for table in ("packet", "message", "message_attempt"):
        made = str(db.execute("SELECT sql FROM sqlite_master WHERE name = ?", (table,)).fetchone()[0])
        assert f"radio INTEGER CONSTRAINT {table}_radio_known REFERENCES radio (id)" in made and f"{table}_radio CHECK" not in made and "radio_id" not in made, made
    db.execute("INSERT INTO message (at, direction, from_call, to_call, text, state) VALUES (?, 'out', 'OH2GBA', 'OH2NEW', 'next', 'sending')", (STAMP,))
    assert db.execute("SELECT last_insert_rowid(), (SELECT radio FROM message WHERE id = 7)").fetchone() == (7, None), "the id of the deleted message is not given again, and a new message names no radio"
    with pytest.raises(sqlite3.IntegrityError, match="packet_via"):
        db.execute("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded, via) VALUES (?, 'in', x'00', 'A', 'B', '', 'status', 's', '{}', 'tcp')", (STAMP,))
    with pytest.raises(sqlite3.IntegrityError, match="cannot store TEXT"):
        db.execute("UPDATE packet SET radio = 'fm'")
    db.close()


def test_a_step_that_is_cut_short_leaves_the_database_as_it_was_and_the_next_run_finishes_it(tmp_path: Path) -> None:
    """The runner gives the step a transaction of its own: what a kill, or a statement that fails in
    the middle, leaves is the database of before, and the step runs again from its start."""
    db = at_31(tmp_path, packets, messages, settings={"hf/enabled": "true"})
    shape = db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    rows = {table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in ("packet", "message", "message_attempt")}
    # Something is in the way of the third table: the first two are done when it fails
    db.execute("ALTER TABLE message_attempt ADD COLUMN radio_id TEXT")
    with pytest.raises(sqlite3.OperationalError, match="duplicate column name: radio_id"):
        run(db, _v32)
    db.execute("ALTER TABLE message_attempt DROP COLUMN radio_id")
    assert db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall() == shape, "the two tables that were done are as they were"
    assert {table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in rows} == rows
    db.close()
    # The next start: another connection finds the file of before
    again = sqlite3.connect(str(tmp_path / DB_NAME), isolation_level=None)
    run(again, _v32)
    assert radios(again, "packet") == RADIOS and radios(again, "message") == [None, 1, 2, 1, None, None] and radios(again, "message_attempt") == [1, 2, None]
    again.close()


class OldSqlite:
    """A connection whose SQLite says it is of an older version, and counts what else it is asked.
    """

    def __init__(self, db: sqlite3.Connection, version: str) -> None:
        self.db, self.version, self.asked = db, version, 0

    def execute(self, statement: str, *args: Any) -> Any:
        if statement == "SELECT sqlite_version()":
            return self.db.execute("SELECT ?", (self.version,))
        self.asked += 1
        return self.db.execute(statement, *args)


@pytest.mark.parametrize("version", ["3.34.1", "3.8.3", "2.8.17"])
def test_an_sqlite_that_cannot_drop_a_column_is_refused_before_anything_is_changed(tmp_path: Path, version: str) -> None:
    db = at_31(tmp_path, packets, settings={"hf/enabled": "true"})
    old = OldSqlite(db, version)
    with pytest.raises(StoreError, match=f"needs SQLite 3.35 or later and this Python has SQLite {version}; nothing was changed .* in backup/"):
        _v32(old)  # type: ignore[arg-type]
    assert old.asked == 0 and columns(db, "packet")["radio"] == "TEXT"
    newer = OldSqlite(db, "3.35.0")
    run(db, lambda _: _v32(newer))  # type: ignore[arg-type]
    assert newer.asked > 0 and radios(db, "packet") == RADIOS
    db.close()


def test_the_way_back_gives_the_words_again_and_the_step_then_makes_the_same_database(tmp_path: Path) -> None:
    """`undo_32` is what tests/support/migrated.step_back uses below 32, so that the test of an
    older migration runs this step over its rows."""
    db = at_31(tmp_path, packets, messages, settings={"hf/enabled": "true"})
    before = {table: whole(db, table) for table in ("packet", "message", "message_attempt")}
    run(db, _v32)
    after = db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    undo_32(db)
    assert {table: whole(db, table) for table in before} == before
    assert radios(db, "packet") == ["fm", "hf", "", "fm", "fm", "fm", "fm", "hf"], "the words again; the packet of the air that named no radio names the FM radio, which is what 32 took it for"
    assert radios(db, "message") == ["", "fm", "hf", "fm", "", ""] and radios(db, "message_attempt") == ["fm", "hf", ""]
    with pytest.raises(sqlite3.IntegrityError, match="packet_radio"):
        db.execute("UPDATE packet SET radio = 'lora'")
    run(db, _v32)
    assert db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall() == after and radios(db, "packet") == RADIOS
    db.close()


# ---- the stores on the database the step leaves

async def test_the_logs_read_the_rows_the_step_left_and_write_the_ids_beside_them(tmp_path: Path) -> None:
    db = at_31(tmp_path, packets, messages, settings={"hf/enabled": "true"})
    run(db, _v32)
    run(db, _v33)
    assert {"station_radio", "station_path"} <= tables(db)
    stepped(db)
    db.close()
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    log, kept = PacketLog(store.db, clock), MessageLog(store.db, clock)
    assert [(p.source, p.radio_id) for p in reversed(await log.recent())] == [(source, radio) for (_, source, *_), radio in zip(PACKETS, RADIOS)]
    assert [(m.id, m.direction, m.radio_id) for m in reversed(await kept.held(10))] == [(1, "out", None), (2, "in", 1), (3, "in", 2), (4, "in", 1), (5, "in", None), (6, "out", None)]
    assert [(a.number, a.radio_id) for a in (await kept.chains())[1]] == [(1, 1), (2, 2), (3, None)]
    at = parse_stamp(LATER)
    assert log.append(Packet(at, "in", FRAME, "OH2RDG", "APRS", (), b">hi", Status("hi"), radio_id=2))
    came = await kept.insert(MessageRecord(0, at, "in", "Q3TKU", "OH2GBA", "again", "9", "received", radio_id=2))
    ours = await kept.insert(MessageRecord(0, at, "out", "OH2GBA", "Q3TKU", "answer", "03", "sending"))
    assert came is not None and ours is not None and kept.add_attempt(ours.id, Attempt(1, at, (), radio_id=2)) and kept.add_attempt(ours.id, Attempt(2, at, ("WIDE1-1",), radio_id=1)) and kept.add_attempt(ours.id, Attempt(3, at, ()))
    assert (await log.recent(1))[0].radio_id == 2 and [(m.id, m.radio_id) for m in (await kept.held(2))] == [(ours.id, None), (came.id, 2)]
    assert [(a.number, a.radio_id) for a in (await kept.chains())[ours.id]] == [(1, 2), (2, 1), (3, None)]
    assert await sql(store, "SELECT radio FROM packet ORDER BY id DESC LIMIT 1") == [(2,)] and await sql(store, "SELECT id, radio FROM message WHERE id >= ? ORDER BY id", came.id) == [(came.id, 2), (ours.id, None)]
    assert await sql(store, "SELECT attempt, radio FROM message_attempt WHERE message_id = ? ORDER BY attempt", ours.id) == [(1, 2), (2, 1), (3, None)]


async def test_a_message_and_an_attempt_of_a_third_radio_are_read_as_they_are(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A message and an attempt hold the id of their radio as it is: a row of a third radio is read
    with it, and nothing is told."""
    db = at_31(tmp_path, messages, settings={"hf/enabled": "true"})
    run(db, _v32)
    run(db, _v33)
    db.execute("UPDATE message SET radio = 3 WHERE id = 3")
    db.execute("UPDATE message_attempt SET radio = 3 WHERE attempt = 2")
    stepped(db)
    db.close()
    caplog.set_level(logging.WARNING, "neoaprs.messagelog")
    kept = MessageLog((await store_at(tmp_path / DB_NAME)).db, FixedClock())
    assert [(m.id, m.radio_id) for m in reversed(await kept.held(10))] == [(1, None), (2, 1), (3, 3), (4, 1), (5, None), (6, None)]
    assert [(a.number, a.radio_id) for a in (await kept.chains())[1]] == [(1, 1), (2, 3), (3, None)]
    assert not [r for r in caplog.records if r.name == "neoaprs.messagelog"]
