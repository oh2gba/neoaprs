"""The statements of the radios, `radio` and `radio_setting` (migration 31), as functions of a connection that the database thread runs (`Store`, store.py, is the part that asks for them; the tools that own
a connection call them on it).

A row of `radio_rows` is a tuple in the order of RADIO_COLUMNS, one of `radio_settings` (radio_id, key, value); the codec between the rows and `RadioSpec` is configradios.radios_from_rows. Nothing here
begins or commits a transaction: a write of more than one statement (`put_radio_settings`, `remove_radio`) is whole in the transaction of whoever runs it (`Db.write`, or `transaction()` of dbfile.py)."""
import json
import sqlite3
from collections.abc import Iterable, Mapping

from .config import MESSAGE_RADIOS as CHOICES          # the state row of the stations' radios, by call, as JSON ({"OH2GAX-2": 2})
from .config import EMAIL_RADIO, NEW_BULLETINS, NEW_OBJECTS
from .configradios import radio_key_of, radios_from_rows
from .dberror import Row, rows
from .radiospec import RadioSpec
from .sendonrule import Kept, ids_of, kept_in_force, text_of
from .storesql import write_setting

RADIO_COLUMNS = ("id", "kind", "type", "name", "enabled", "position", "removed_at")
CHANGEABLE = ("type", "name", "enabled", "position")      # what `update_radio` may set: the kind is the radio's for good, and it is removed by `remove_radio`


def radio_rows(db: sqlite3.Connection) -> list[Row]:
    """Every radio, removed ones too, by id."""
    return rows(db.execute(f"SELECT {', '.join(RADIO_COLUMNS)} FROM radio ORDER BY id"))


def radio_settings(db: sqlite3.Connection) -> list[Row]:
    """The radios' own settings: (radio_id, key, value)."""
    return rows(db.execute("SELECT radio_id, key, value FROM radio_setting ORDER BY radio_id, key"))


def insert_radio(db: sqlite3.Connection, kind: str, type: str, name: str, enabled: bool, position: int) -> int:
    """A new radio; its id, which no radio had before it and none has after it (AUTOINCREMENT)."""
    cursor = db.execute("INSERT INTO radio (kind, type, name, enabled, position) VALUES (?, ?, ?, ?, ?)", (kind, type, name, int(enabled), position))
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


def of_removed_radio(db: sqlite3.Connection, keys: Iterable[str]) -> bool:
    """Whether one of `keys` is a row of a removed radio's own state (`radio/<id>/<name>`: a beacon's last send, a port found, written by a task that waited behind the removal). `remove_radio` took
    those away, and nothing would take one away again, for the id never comes back: the Store writes none (Store.put_setting). A radio with no row at all (a database whose radios are not stored yet)
    is not a removed one."""
    ids = {found[0] for key in keys if (found := radio_key_of(key)) is not None}
    return any(db.execute("SELECT 1 FROM radio WHERE id = ? AND removed_at IS NOT NULL", (id,)).fetchone() for id in ids)


def _out_of_sets(db: sqlite3.Connection, id: int) -> None:
    """A removed radio's id out of the objects' and the bulletins' sets (one that goes out on no other radio keeps it: a set is never empty) and out of what a new object and a new bulletin start with."""
    for table, key in (("own_object", "name"), ("own_bulletin", "slot")):
        for name, radios in db.execute(f"SELECT {key}, radios FROM {table}").fetchall():
            kept = [part for part in str(radios).split(",") if part != str(id)]
            if kept and len(kept) != len(str(radios).split(",")):
                db.execute(f"UPDATE {table} SET radios = ? WHERE {key} = ?", (",".join(kept), name))
    for key in (NEW_OBJECTS, NEW_BULLETINS):
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is not None and id in (ids := ids_of(str(row[0]))):
            if left := tuple(radio for radio in ids if radio != id):
                write_setting(db, key, text_of(left))
            else:
                db.execute("DELETE FROM settings WHERE key = ?", (key,))


def remove_radio(db: sqlite3.Connection, id: int, at: str) -> int:
    """Removes a radio, in the transaction of the caller; how many rows it found (0 for a radio that is not there or is removed already, and then nothing is touched). The row stays, with the time
    in `removed_at`, so that what came by the radio still says so, and its own settings and what it heard of the stations stay with it. What chooses it is taken back: its id out of the objects' and the
    bulletins' sets (one that goes out on no other radio keeps it, for a set is never empty: it is ticked nowhere), out of what a new object and a new bulletin start with, the e-mail radio where it is
    that one, the stations' paths on it, the stations' choices of it (the state row messages/radio_by_station), and the rows of its own state (`radio/<id>/*`)."""
    if not db.execute("UPDATE radio SET removed_at = ? WHERE id = ? AND removed_at IS NULL", (at, id)).rowcount:
        return 0
    _out_of_sets(db, id)
    db.execute("DELETE FROM settings WHERE key = ? AND trim(value) = ?", (EMAIL_RADIO, str(id)))
    db.execute("DELETE FROM station_path WHERE radio_id = ?", (id,))
    row = db.execute("SELECT value FROM settings WHERE key = ?", (CHOICES,)).fetchone()
    if row is not None:
        chosen = _choices(str(row[0]))
        if id in chosen.values():
            write_setting(db, CHOICES, json.dumps({call: radio for call, radio in chosen.items() if radio != id}, sort_keys=True))
    db.execute("DELETE FROM settings WHERE key GLOB ?", (f"radio/{int(id)}/*",))
    return 1


def put_kept(db: sqlite3.Connection, kept: Kept) -> None:
    """What a change of the radios keeps in force (sendonrule.kept_in_force), written in the transaction of that change: the ticks, the e-mail radio, the objects' and the bulletins' sets."""
    for radio, key in kept.ticks:
        put_radio_settings(db, radio, {key: "true"})
    if kept.email is not None:
        write_setting(db, EMAIL_RADIO, str(kept.email))
    for table, column, sets in (("own_object", "name", kept.objects), ("own_bulletin", "slot", kept.bulletins)):
        for name, radios in sets.items():
            db.execute(f"UPDATE {table} SET radios = ? WHERE {column} = ?", (text_of(radios), name))


def kept_by_rows(db: sqlite3.Connection, before: Iterable[RadioSpec]) -> Kept:
    """What the change of the radios from `before` to the radios the database holds now keeps in force (sendonrule.kept_in_force), read from the rows (the objects', the bulletins' sets and `email/radio`):
    for a tool that changes the radios while no daemon runs (`neoaprs db radios add`), whose rows are all there is. Written with `put_kept` in the same transaction."""
    after = radios_from_rows(radio_rows(db), radio_settings(db))
    sets = [{str(name): ids_of(str(radios)) for name, radios in db.execute(f"SELECT {key}, radios FROM {table}")} for table, key in (("own_object", "name"), ("own_bulletin", "slot"))]
    row = db.execute("SELECT value FROM settings WHERE key = ?", (EMAIL_RADIO,)).fetchone()
    email = ids_of(str(row[0])) if row is not None else ()
    return kept_in_force(before, after, sets[0], sets[1], email[0] if len(email) == 1 else None)


def _choices(text: str) -> dict[str, object]:
    """The stations' radios of the state row, by call; a row that is not one says nothing."""
    try:
        kept = json.loads(text)
    except ValueError:
        return {}
    return kept if isinstance(kept, dict) else {}
