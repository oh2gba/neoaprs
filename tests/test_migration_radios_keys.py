"""Migrations 24 and 25 (neoaprs/migrationsteps22on.py) on databases with rows in them. 24 (encrypted messages): the table of the stations' keys is there and empty, a message is plain (`seal` empty, `wire` none) as it was.
25 (two radios): everything the air gave so far came on the FM radio, so a packet that was heard or sent has the radio `fm` and a packet from the internet none, a station's FM count is the sum of its radio counts (the
Dummy radio's included) and its FM time the latest of their times, a message that came in and every attempt of ours name the FM radio, and an object of ours goes out on FM."""
from pathlib import Path

from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, STAMP, raw

LATER = "2026-10-21T12:30:00.000000Z"
LATEST = "2026-10-21T13:30:00.000000Z"
INSERT_PACKET = "INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded{via}) VALUES (?, ?, x'00', ?, 'APRS', '', 'status', 's', '{{}}'{value})"
INSERT_MESSAGE = ("INSERT INTO message (at, direction, from_call, to_call, text, msg_id, state, attempts, route) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')")


def messages(db: object) -> None:
    db.execute(INSERT_MESSAGE, (STAMP, "out", "OH2GBA", "OH2RDG", "hello", "01", "acked", 2))      # type: ignore[attr-defined]
    db.execute(INSERT_MESSAGE, (LATER, "in", "OH2RDG", "OH2GBA", "hi there", "7", "received", 0))      # type: ignore[attr-defined]
    db.execute(INSERT_MESSAGE, (LATER, "in", "OH2AAA", "OH2BBB", "not for us", None, "overheard", 0))      # type: ignore[attr-defined]


def test_migration_24_leaves_the_messages_plain_and_makes_the_table_of_keys(tmp_path: Path) -> None:
    clock = FixedClock()
    path = tmp_path / DB_NAME
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 24")
    step_back(db, 23)
    db.execute("PRAGMA user_version = 23")
    messages(db)
    db.close()
    migrated = opened(path, clock)
    assert migrated.version() == SCHEMA_VERSION >= 24 and [(r[0], r[2]) for r in migrated.history()][23:] == [(24, GOLDEN[24]), (25, GOLDEN[25])]
    assert migrated.db.execute("SELECT text, seal, wire FROM message ORDER BY id").fetchall() == [("hello", "", None), ("hi there", "", None), ("not for us", "", None)]
    assert migrated.db.execute("SELECT count(*) FROM station_key").fetchone() == (0,)
    migrated.close()


def test_migration_25_marks_what_the_air_gave_as_the_fm_radios_and_counts_the_stations_for_it(tmp_path: Path) -> None:
    clock = FixedClock()
    path = tmp_path / DB_NAME
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 25")
    step_back(db, 24)
    db.execute("PRAGMA user_version = 24")
    for at, direction, source, via in ((STAMP, "in", "OH2RDG", "rf"), (LATER, "in", "OH7JHF-1", "rf-gated"), (LATER, "in", "OH2NET", "is"), (LATER, "out", "OH2GBA", "rf"), (LATEST, "in", "OH2DUM", "dummy")):
        db.execute(INSERT_PACKET.format(via=", via", value=", ?"), (at, direction, source, via))
    station = ("INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, lat, lon, first_heard, last_heard, last_position_at, last_status, last_comment, packets, last_path, "
               "heard_rf, heard_rf_gated, heard_is, heard_dummy, last_rf_at, last_rf_gated_at, last_is_at, last_dummy_at) VALUES (?, 'station', '', '/', '-', 60.1, 24.9, ?, ?, ?, '', '', ?, '', ?, ?, ?, ?, ?, ?, ?, ?)")
    db.execute(station, ("OH2MIX", STAMP, LATEST, STAMP, 9, 3, 2, 1, 3, STAMP, LATER, LATER, LATEST))        # (heard four ways: FM is rf + gated + dummy)
    db.execute(station, ("OH2NET", STAMP, LATER, STAMP, 4, 0, 0, 4, 0, None, None, LATER, None))            # (the internet alone: no FM at all)
    db.execute(station, ("OH2RDG", STAMP, STAMP, STAMP, 2, 2, 0, 0, 0, STAMP, None, None, None))
    messages(db)
    db.execute("INSERT INTO message_attempt (message_id, attempt, sent_at, path) VALUES (1, 1, ?, 'WIDE1-1'), (1, 2, ?, '')", (STAMP, LATER))
    db.execute("INSERT INTO own_object (name, kind, lat, lon, symbol_table, symbol_code, comment, alive, created_at, updated_at) VALUES ('LEIRI', 'object', 60.2, 25.0, '/', '-', 'camp', 1, ?, ?)", (STAMP, STAMP))
    db.close()
    migrated = opened(path, clock)
    assert migrated.version() == SCHEMA_VERSION >= 25 and [(r[0], r[2]) for r in migrated.history()][24:] == [(25, GOLDEN[25])]
    d = migrated.db
    assert d.execute("SELECT source, radio FROM packet ORDER BY id").fetchall() == [("OH2RDG", "fm"), ("OH7JHF-1", "fm"), ("OH2NET", ""), ("OH2GBA", "fm"), ("OH2DUM", "fm")], "the internet's packet has no radio"
    stations = {r[0]: r[1:] for r in d.execute("SELECT call, heard_fm, heard_hf, last_fm_at, last_hf_at FROM station")}
    assert stations["OH2MIX"] == (8, 0, LATEST, None), "rf + rf-gated + dummy, and the latest of their times"
    assert stations["OH2NET"] == (0, 0, None, None), "the internet alone is no radio's"
    assert stations["OH2RDG"] == (2, 0, STAMP, None)
    assert d.execute("SELECT direction, radio FROM message ORDER BY id").fetchall() == [("out", ""), ("in", "fm"), ("in", "fm")]
    assert d.execute("SELECT attempt, radio FROM message_attempt ORDER BY attempt").fetchall() == [(1, "fm"), (2, "fm")]
    assert d.execute("SELECT name, radio FROM own_object").fetchall() == [("LEIRI", "fm")]
    migrated.close()
