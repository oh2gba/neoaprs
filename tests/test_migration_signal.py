"""Migration 30 (neoaprs/migrationsteps22on.py): the signal of what is heard. A packet keeps the SNR and the RSSI its radio measured (`packet.snr`, `packet.rssi`), a message those of the packet that carried it
(`message.snr`, `message.rssi`), a station its last reading and when it was heard (`station.snr`, `station.rssi`, `station.signal_at`). Every row of a database of the version before keeps what it had and has no
reading: nothing kept before measured one."""
import sqlite3
from pathlib import Path

from neoaprs import ax25
from neoaprs.messagelog import message_of
from neoaprs.messagesql import held_messages
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.packetcodec import PacketRow, packet_of, parse_stamp
from neoaprs.packetlog import station_of, station_row
from neoaprs.packetsql import PACKET_LIST, STATION_COLUMNS, all_stations
from neoaprs.station import Station
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, STAMP, raw, shape

FRAME = ax25.encode(ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("Q3TKU"), (), info=b">hi"))       # a status heard over HF
MESSAGE_COLUMNS = "id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route, seal, wire, radio, failure"
MESSAGES = [(1, STAMP, "out", "OH2GBA", "OH2RDG", "one", "1", "acked", 1, STAMP, STAMP, 4, "", "", None, "", None), (2, STAMP, "in", "OH2RDG", "OH2GBA", "two", "7", "received", 0, None, None, 4, "direct", "", None, "hf", None)]


def version_twenty_nine(path: Path, clock: FixedClock) -> None:
    """A database as version 29 left it, with a packet heard on HF, a station and the messages of MESSAGES."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 30")
    step_back(db, 29)
    db.execute("PRAGMA user_version = 29")
    db.execute("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded, error, via, radio) VALUES (?, 'in', ?, 'Q3TKU', 'APRS', '', 'status', 'status hi', "
               "'{\"type\":\"status\",\"text\":\"hi\",\"timestamp\":null,\"locator\":null,\"frequency\":null}', NULL, 'rf', 'hf')", (STAMP, FRAME))
    before = STATION_COLUMNS[:-3]                                                # (the columns of version 29: the last three are migration 30's)
    row = station_row(Station("Q3TKU", first_heard=parse_stamp(STAMP), last_heard=parse_stamp(STAMP), packets=1, heard_rf=1, heard_hf=1, last_hf_at=parse_stamp(STAMP)))[:len(before)]
    db.execute(f"INSERT INTO station ({', '.join(before)}) VALUES ({', '.join('?' * len(before))})", row)
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
    assert shape(migrated.db) == shape(fresh.db), "a migrated database has exactly the tables, indexes and checks of a new one"
    assert [(r[0], r[1], r[2]) for r in migrated.history()][29:] == [(30, "_v30", GOLDEN[30])]
    fresh.close()
    return migrated.db


def test_every_row_is_kept_and_none_has_a_reading(tmp_path: Path) -> None:
    db = migrate(tmp_path)
    assert db.execute(f"SELECT {MESSAGE_COLUMNS} FROM message ORDER BY id").fetchall() == MESSAGES
    assert db.execute("SELECT snr, rssi FROM message ORDER BY id").fetchall() == [(None, None)] * len(MESSAGES)
    assert [(r.id, r.snr, r.rssi) for r in sorted((message_of(row) for row in held_messages(db, 10)), key=lambda r: r.id)] == [(1, None, None), (2, None, None)]
    packet = packet_of(PacketRow(*db.execute(f"SELECT {PACKET_LIST} FROM packet").fetchone()))
    assert (packet.source, packet.radio, packet.snr, packet.rssi) == ("Q3TKU", "hf", None, None)
    station = station_of(all_stations(db)[0])
    assert (station.call, station.heard_hf, station.snr, station.rssi, station.signal_at) == ("Q3TKU", 1, None, None, None)
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
