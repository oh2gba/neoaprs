"""The statements of the radios, `radio` and `radio_setting` (migration 31), as functions of a connection that the database thread runs (`Store`, store.py, is the part that asks for them; the tools that own
a connection call them on it).

A row of `radio_rows` is a tuple in the order of RADIO_COLUMNS, one of `radio_settings` (radio_id, key, value); the codec between the rows and `RadioSpec` is configradios.radios_from_rows. Nothing here
begins or commits a transaction: a write of more than one statement (`put_radio_settings`, `remove_radio`) is whole in the transaction of whoever runs it (`Db.write`, or `transaction()` of dbfile.py)."""
import json
import sqlite3
from collections.abc import Mapping

from .config import MESSAGE_RADIOS as CHOICES          # the state row of the stations' radios, by call, as JSON ({"OH2GAX-2": 2})
from .dberror import Row, rows
from .storesql import write_setting

RADIO_COLUMNS = ("id", "kind", "type", "name", "enabled", "position", "removed_at")
CHANGEABLE = ("type", "name", "enabled", "position")      # what `update_radio` may set: the kind is the radio's for good, and it is removed by `remove_radio`


def radio_rows(db: sqlite3.Connection) -> list[Row]:
    """Every radio, removed ones too, by id."""
    return rows(db.execute(f"SELECT {', '.join(RADIO_COLUMNS)} FROM radio ORDER BY id"))


def radio_settings(db: sqlite3.Connection) -> list[Row]:
    """The radios' own settings: (radio_id, key, value)."""
    return rows(db.execute("SELECT radio_id, key, value FROM radio_setting ORDER BY radio_id, key"))


def insert_radio(db: sqlite3.Connection, kind: str, type: str, name: str, enabled: bool, position: int, *, id: int | None = None) -> int:
    """A new radio; its id, which no radio had before it and none has after it (AUTOINCREMENT). `id`: the id it is to have, for the two radios of today's flat keys (1 the FM radio, 2 the HF radio)
    on a database that has no row for them; a row with that id refuses it (sqlite3.IntegrityError)."""
    cursor = db.execute("INSERT INTO radio (id, kind, type, name, enabled, position) VALUES (?, ?, ?, ?, ?, ?)", (id, kind, type, name, int(enabled), position))
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def update_radio(db: sqlite3.Connection, id: int, /, **columns: object) -> int:
    """Sets columns of a radio (CHANGEABLE: type, name, enabled, position); how many rows it found (0 or 1: a radio that is not there or is removed is not changed). ValueError for any other column."""
    if not columns or not set(columns) <= set(CHANGEABLE):
        raise ValueError(f"a radio's {', '.join(sorted(set(columns) - set(CHANGEABLE))) or 'nothing'} cannot be set: its columns are {', '.join(CHANGEABLE)}")
    values = [int(value) if isinstance(value, bool) else value for value in columns.values()]
    return db.execute(f"UPDATE radio SET {', '.join(f'{c} = ?' for c in columns)} WHERE id = ? AND removed_at IS NULL", (*values, id)).rowcount


def put_radio_settings(db: sqlite3.Connection, id: int, values: Mapping[str, str]) -> bool:
    """A radio's own settings written, in the transaction of the caller: each key replaced and its revision counted up, as `write_settings` does; the radio's other settings stay. False, and nothing
    written, for a radio that is not there or is removed (the table's REFERENCES is not enforced: foreign keys are off)."""
    if db.execute("SELECT 1 FROM radio WHERE id = ? AND removed_at IS NULL", (id,)).fetchone() is None:
        return False
    for key, value in values.items():
        db.execute("INSERT INTO radio_setting (radio_id, key, value) VALUES (?, ?, ?) ON CONFLICT(radio_id, key) DO UPDATE SET value = excluded.value, rev = radio_setting.rev + 1", (id, key, value))
    return True


def remove_radio(db: sqlite3.Connection, id: int, at: str) -> int:
    """Removes a radio, in the transaction of the caller; how many rows it found (0 for a radio that is not there or is removed already, and then nothing is touched). The row stays, with the time
    in `removed_at`, so that what came by the radio still says so, and its own settings and what it heard of the stations stay with it. What chooses it is taken back: its id out of the objects' sets
    (an object that goes out on no other radio keeps it: such a set is read as the main radio), the stations' paths on it, the stations' choices of it (the state row messages/radio_by_station), and
    the rows of its own state (`radio/<id>/*`)."""
    if not db.execute("UPDATE radio SET removed_at = ? WHERE id = ? AND removed_at IS NULL", (at, id)).rowcount:
        return 0
    for name, radios in db.execute("SELECT name, radios FROM own_object").fetchall():
        kept = [part for part in str(radios).split(",") if part != str(id)]
        if kept and len(kept) != len(str(radios).split(",")):
            db.execute("UPDATE own_object SET radios = ? WHERE name = ?", (",".join(kept), name))
    db.execute("DELETE FROM station_path WHERE radio_id = ?", (id,))
    row = db.execute("SELECT value FROM settings WHERE key = ?", (CHOICES,)).fetchone()
    if row is not None:
        chosen = _choices(str(row[0]))
        if id in chosen.values():
            write_setting(db, CHOICES, json.dumps({call: radio for call, radio in chosen.items() if radio != id}, sort_keys=True))
    db.execute("DELETE FROM settings WHERE key GLOB ?", (f"radio/{int(id)}/*",))
    return 1


def _choices(text: str) -> dict[str, object]:
    """The stations' radios of the state row, by call; a row that is not one says nothing."""
    try:
        kept = json.loads(text)
    except ValueError:
        return {}
    return kept if isinstance(kept, dict) else {}
