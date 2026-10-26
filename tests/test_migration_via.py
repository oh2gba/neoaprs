"""Migration 21 (neoaprs/migrations2.py): the channel of a packet (`packet.via`: rf, rf-gated, is) and, in the station cache, the count and the latest time for each channel and the channel of the position.
A stored frame that holds a third-party packet becomes `rf-gated` (told from the stored `raw` alone), every other packet `rf`; a cached station has been heard on the radio, except for the packets of
it that are stored as rf-gated; a step that doubts changes nothing; the tables refuse a channel the program cannot produce."""
import sqlite3
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.migrations import MIGRATIONS, SCHEMA_VERSION
from neoaprs.migrations2 import _third_party_sender
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, STAMP, raw, shape

LATER = "2026-10-21T12:30:00.000000Z"
INSERT_PACKET = "INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded) VALUES (?, ?, ?, ?, ?, ?, 'status', 's', '{}')"
INSERT_STATION = ("INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, lat, lon, first_heard, last_heard, last_position_at, last_status, last_comment, packets, last_path) "
                  "VALUES (?, 'station', '', '/', '-', ?, ?, ?, ?, ?, '', '', ?, '')")


def frame(source: str, path: tuple[str, ...], info: bytes) -> bytes:
    return ax25.encode(ax25.Frame(ax25.Address("APRS"), ax25.Address.parse(source), tuple(ax25.Address.parse(p) for p in path), info=info))


GATED = frame("OH7JHF-1", ("OH2RCH-3*",), b"}OH2DPN>APJYC1,TCPIP,OH7JHF-1*::OH2GBA   :ack10")
GATED_AGAIN = frame("OH7JHF-1", (), b"}OH2DPN-0>APRS,TCPIP,OH7JHF-1*:>later")
NO_HEADER = frame("OH7JHF-1", (), b"}this is not a header")
PLAIN = frame("OH2RDG", ("OH2RCH-2*",), b">hello")
BRACE_LATER = frame("OH2RDG", (), b">hello } there")


def version_twenty(path: Path, clock: FixedClock) -> None:
    """A database as version 20 left it, with packets of every kind there was and stations that were counted by the packets they sent."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 21")
    step_back(db, 20)
    db.execute("PRAGMA user_version = 20")
    for blob, source, direction, at in ((PLAIN, "OH2RDG", "in", STAMP), (GATED, "OH7JHF-1", "in", STAMP), (GATED_AGAIN, "OH7JHF-1", "in", LATER), (NO_HEADER, "OH7JHF-1", "in", LATER),
                                        (BRACE_LATER, "OH2RDG", "in", LATER), (PLAIN, "OH2GBA", "out", LATER)):
        db.execute(INSERT_PACKET, (at, direction, blob, source, "APRS", ""))
    db.execute(INSERT_STATION, ("OH2RDG", 60.1, 24.9, STAMP, LATER, STAMP, 2))
    db.execute(INSERT_STATION, ("OH2DPN", 60.2, 25.0, STAMP, LATER, LATER, 5))               # (it sent 5 packets, 2 of which an iGate put on the air)
    db.execute(INSERT_STATION, ("OH7JHF-1", None, None, STAMP, LATER, None, 3))
    db.close()


def migrate(folder: Path) -> tuple[sqlite3.Connection, Path, FixedClock]:
    clock = FixedClock()
    old = folder / "old" / DB_NAME
    old.parent.mkdir()
    version_twenty(old, clock)
    migrated = opened(old, clock)
    assert migrated.version() == SCHEMA_VERSION >= 21
    assert [(r[0], r[1], r[2]) for r in migrated.history()][20:] == [(21, "_v21", GOLDEN[21])]
    return migrated.db, old, clock


def test_a_stored_third_party_frame_is_rf_gated_and_every_other_packet_rf(tmp_path: Path) -> None:
    db, _, _ = migrate(tmp_path)
    found = db.execute("SELECT source, direction, heard_at, via FROM packet ORDER BY id").fetchall()
    assert found == [("OH2RDG", "in", STAMP, "rf"), ("OH7JHF-1", "in", STAMP, "rf-gated"), ("OH7JHF-1", "in", LATER, "rf-gated"), ("OH7JHF-1", "in", LATER, "rf"),
                     ("OH2RDG", "in", LATER, "rf"), ("OH2GBA", "out", LATER, "rf")], "a brace that is not at the start of the information field, and a brace that opens no header, make no third-party packet"


def test_a_cached_station_is_counted_for_the_radio_and_the_third_party_packets_move_to_their_own_count(tmp_path: Path) -> None:
    db, _, _ = migrate(tmp_path)
    columns = "call, packets, heard_rf, heard_rf_gated, heard_is, last_rf_at, last_rf_gated_at, last_is_at, position_via"
    rows = {r[0]: r for r in db.execute(f"SELECT {columns} FROM station")}
    assert rows["OH2RDG"] == ("OH2RDG", 2, 2, 0, 0, LATER, None, None, "rf")
    assert rows["OH2DPN"] == ("OH2DPN", 5, 3, 2, 0, LATER, LATER, None, "rf")
    assert rows["OH7JHF-1"] == ("OH7JHF-1", 3, 3, 0, 0, LATER, None, None, None), "a station without a position has no channel of it"
    assert all(r[1] == r[2] + r[3] + r[4] for r in rows.values())


def test_a_station_all_of_whose_packets_came_by_a_gate_is_known_by_the_gate(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_twenty(old, clock)
    db = raw(old)
    db.execute("UPDATE station SET packets = 2 WHERE call = 'OH2DPN'")
    db.close()
    migrated = opened(old, clock)
    assert migrated.db.execute("SELECT packets, heard_rf, heard_rf_gated, last_rf_at, last_rf_gated_at, position_via FROM station WHERE call = 'OH2DPN'").fetchone() == (2, 0, 2, None, LATER, "rf-gated")


def test_a_migrated_database_has_exactly_the_tables_indexes_and_checks_of_a_new_one_and_a_copy_was_made(tmp_path: Path) -> None:
    db, old, clock = migrate(tmp_path)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert shape(db) == shape(fresh.db)
    assert db.execute("SELECT COUNT(*) FROM packet").fetchone()[0] == 6 and db.execute("SELECT COUNT(*) FROM station").fetchone()[0] == 3
    [copy_path] = sorted((old.parent / "backup").glob("premigrate-v20-to-v*.sqlite"))
    copy = raw(copy_path)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 20 and "via" not in {r[1] for r in copy.execute("PRAGMA table_info(packet)")}
    fresh.close()


@pytest.mark.parametrize(("statement", "check"), [
    ("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded, via) VALUES ('2026-10-21T12:00:00.000000Z', 'in', x'00', 'A', 'B', '', 'status', 's', '{}', 'tcp')", "packet_via"),
    ("UPDATE station SET heard_is = -1", "station_heard_is_count"),
    ("UPDATE station SET last_is_at = '2026-10-21 12:00'", "station_last_is_at_form"),
    ("UPDATE station SET position_via = 'wifi'", "station_position_via"),
    ("UPDATE station SET heard_dummy = -1", "station_heard_dummy_count"),
])
def test_the_tables_refuse_what_the_program_cannot_produce(tmp_path: Path, statement: str, check: str) -> None:
    db, _, _ = migrate(tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match=check):
        db.execute(statement)


def test_the_dummy_radios_channel_is_one_the_tables_take(tmp_path: Path) -> None:
    db, _, _ = migrate(tmp_path)
    db.execute("UPDATE station SET position_via = 'dummy', heard_dummy = 2, last_dummy_at = ? WHERE call = 'OH2RDG'", (STAMP,))
    db.execute("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded, via) VALUES (?, 'in', x'00', 'QDUMMY-1', 'APRS', '', 'status', 's', '{}', 'dummy')", (STAMP,))
    assert db.execute("SELECT via FROM packet ORDER BY id DESC LIMIT 1").fetchone() == ("dummy",)


def test_a_packet_inserted_without_a_channel_is_one_heard_on_the_radio(tmp_path: Path) -> None:
    db, _, _ = migrate(tmp_path)
    db.execute(INSERT_PACKET, (STAMP, "in", PLAIN, "OH2RDG", "APRS", ""))
    assert db.execute("SELECT via FROM packet ORDER BY id DESC LIMIT 1").fetchone() == ("rf",)


def test_the_sender_of_a_third_party_frame_is_read_from_the_frame_alone() -> None:
    assert _third_party_sender(GATED) == "OH2DPN" and _third_party_sender(GATED_AGAIN) == "OH2DPN", "an SSID of 0 is no SSID, as the station book names the station"
    assert _third_party_sender(NO_HEADER) is None and _third_party_sender(PLAIN) is None and _third_party_sender(BRACE_LATER) is None
    assert _third_party_sender(b"") is None and _third_party_sender(b"\x00" * 5) is None and _third_party_sender(GATED[:10]) is None


def test_the_step_is_pinned() -> None:
    assert len(MIGRATIONS) >= 21 and MIGRATIONS[20].__name__ == "_v21"
