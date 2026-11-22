"""Migration 30 (neoaprs/migrationsteps22on.py): the signal of what is heard: SNR and RSSI on
packets, messages and stations (`station.signal_at`). Existing rows get none.
"""

import sqlite3
from pathlib import Path

from neoaprs import ax25
from neoaprs.messagelog import message_of
from neoaprs.messagesql import held_messages
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.packetcodec import PacketRow, packet_of
from neoaprs.packetlog import heard_of, station_of
from neoaprs.packetsql import PACKET_LIST, all_stations, heard_by_radio
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, STAMP, raw, shape

FRAME = ax25.encode(
    ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("Q3TKU"), (), info=b">hi")
)  # a status heard over HF
MESSAGE_COLUMNS = "id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route, seal, wire, radio, failure"
MESSAGES = [
    (1, STAMP, "out", "OH2GBA", "OH2RDG", "one", "1", "acked", 1, STAMP, STAMP, 4, "", "", None, "", None),
    (2, STAMP, "in", "OH2RDG", "OH2GBA", "two", "7", "received", 0, None, None, 4, "direct", "", None, "hf", None),
]


def version_twenty_nine(path: Path, clock: FixedClock) -> None:
    """A database as version 29 left it, with a packet heard on HF, a station and the messages of
    MESSAGES."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 30")
    step_back(db, 29)
    db.execute("PRAGMA user_version = 29")
    db.execute(
        "INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded, error, via, radio) VALUES (?, 'in', ?, 'Q3TKU', 'APRS', '', 'status', 'status hi', "
        '\'{"type":"status","text":"hi","timestamp":null,"locator":null,"frequency":null}\', NULL, \'rf\', \'hf\')',
        (STAMP, FRAME),
    )
    # The columns of version 29
    db.execute(
        "INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, first_heard, last_heard, last_status, last_comment, packets, last_path, heard_rf, heard_hf, last_hf_at) "
        "VALUES ('Q3TKU', 'station', '', '', '', ?, ?, '', '', 1, '', 1, 1, ?)",
        (STAMP, STAMP, STAMP),
    )
    # The HF radio was on: migration 31 gives the database radio 2
    db.execute("INSERT INTO settings (key, value) VALUES ('hf/enabled', 'true')")
    for row in MESSAGES:
        db.execute(f"INSERT INTO message ({MESSAGE_COLUMNS}) VALUES ({', '.join('?' * len(row))})", row)
    db.close()


def migrate(folder: Path) -> sqlite3.Connection:
    clock = FixedClock()
    old = folder / "old" / DB_NAME
    old.parent.mkdir()
    version_twenty_nine(old, clock)
    migrated = opened(old, clock)
    fresh = opened(folder / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 30
    assert shape(migrated.db) == shape(fresh.db), (
        "a migrated database has exactly the tables, indexes and checks of a new one"
    )
    assert [(r[0], r[1], r[2]) for r in migrated.history()][29:] == [
        (30, "_v30", GOLDEN[30]),
        (31, "_v31", GOLDEN[31]),
        (32, "_v32", GOLDEN[32]),
        (33, "_v33", GOLDEN[33]),
        (34, "_v34", GOLDEN[34]),
        (35, "_v35", GOLDEN[35]),
        (36, "_v36", GOLDEN[36]),
    ]
    fresh.close()
    return migrated.db


def test_every_row_is_kept_and_none_has_a_reading(tmp_path: Path) -> None:
    db = migrate(tmp_path)
    assert db.execute(f"SELECT {MESSAGE_COLUMNS} FROM message ORDER BY id").fetchall() == [
        (*row[:15], {"": None, "hf": 2}[row[15]], row[16]) for row in MESSAGES
    ], "every column as it was, the radio by its id (migration 32)"
    assert db.execute("SELECT snr, rssi FROM message ORDER BY id").fetchall() == [(None, None)] * len(MESSAGES)
    assert [
        (r.id, r.snr, r.rssi) for r in sorted((message_of(row) for row in held_messages(db, 10)), key=lambda r: r.id)
    ] == [(1, None, None), (2, None, None)]
    packet = packet_of(PacketRow(*db.execute(f"SELECT {PACKET_LIST} FROM packet").fetchone()))
    assert (packet.source, packet.radio_id, packet.snr, packet.rssi) == ("Q3TKU", 2, None, None)
    station = station_of(
        all_stations(db)[0], heard={radio: heard for _, radio, heard in map(heard_of, heard_by_radio(db))}
    )
    assert (station.call, station.heard_on(2).count, station.snr, station.rssi, station.signal_at) == (
        "Q3TKU",
        1,
        None,
        None,
        None,
    )
    db.close()


def test_the_columns_take_a_reading(tmp_path: Path) -> None:
    db = migrate(tmp_path)
    db.execute("UPDATE packet SET snr = -2.5, rssi = -112")
    db.execute("UPDATE message SET snr = 6.1 WHERE id = 1")
    db.execute("UPDATE station SET snr = -2.5, signal_at = ?", (STAMP,))
    packet = packet_of(PacketRow(*db.execute(f"SELECT {PACKET_LIST} FROM packet").fetchone()))
    assert (packet.snr, packet.rssi) == (-2.5, -112.0)
    assert {r.id: r.snr for r in (message_of(row) for row in held_messages(db, 10))} == {1: 6.1, 2: None}
    assert station_of(all_stations(db)[0]).snr == -2.5
    db.close()
