"""SQL for the `radio` and `radio_setting` tables, as functions of a connection.

Nothing here begins or commits a transaction: a write is atomic in the caller's transaction.
"""

import json
import sqlite3
from collections.abc import Iterable, Mapping

# the state row of the stations' radios, by call, as JSON
from .config import MESSAGE_RADIOS as CHOICES
from .config import EMAIL_RADIO, NEW_BULLETINS, NEW_OBJECTS
from .configradios import radio_key_of, radios_from_rows
from .dberror import Row, rows
from .pairsetting import pair_key_of
from .radiospec import RadioSpec
from .sendonrule import Kept, ids_of, kept_in_force, text_of
from .storesql import write_setting

RADIO_COLUMNS = ("id", "kind", "type", "name", "enabled", "position", "removed_at")
# Columns `update_radio` may set; the kind is fixed for good.
CHANGEABLE = ("type", "name", "enabled", "position")


def radio_rows(db: sqlite3.Connection) -> list[Row]:
    """Return every radio, removed ones too, by id."""
    return rows(db.execute(f"SELECT {', '.join(RADIO_COLUMNS)} FROM radio ORDER BY id"))


def radio_settings(db: sqlite3.Connection) -> list[Row]:
    """Return the radios' settings as (radio_id, key, value)."""
    return rows(db.execute("SELECT radio_id, key, value FROM radio_setting ORDER BY radio_id, key"))


def insert_radio(db: sqlite3.Connection, kind: str, type: str, name: str, enabled: bool, position: int) -> int:
    """Insert a radio and return its id, which is never reused (AUTOINCREMENT)."""
    cursor = db.execute(
        "INSERT INTO radio (kind, type, name, enabled, position) VALUES (?, ?, ?, ?, ?)",
        (kind, type, name, int(enabled), position),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def update_radio(db: sqlite3.Connection, id: int, /, **columns: object) -> int:
    """Set CHANGEABLE columns of a radio; return the rows changed (0 if missing or removed).

    Raise ValueError for any other column.
    """
    if not columns or not set(columns) <= set(CHANGEABLE):
        raise ValueError(
            f"a radio's {', '.join(sorted(set(columns) - set(CHANGEABLE))) or 'nothing'} cannot be set: its columns are {', '.join(CHANGEABLE)}"
        )
    values = [int(value) if isinstance(value, bool) else value for value in columns.values()]
    return db.execute(
        f"UPDATE radio SET {', '.join(f'{c} = ?' for c in columns)} WHERE id = ? AND removed_at IS NULL", (*values, id)
    ).rowcount


def put_radio_settings(db: sqlite3.Connection, id: int, values: Mapping[str, str]) -> bool:
    """Write a radio's settings, bumping each revision; False for a missing or removed radio."""
    if db.execute("SELECT 1 FROM radio WHERE id = ? AND removed_at IS NULL", (id,)).fetchone() is None:
        return False
    for key, value in values.items():
        db.execute(
            "INSERT INTO radio_setting (radio_id, key, value) VALUES (?, ?, ?) ON CONFLICT(radio_id, key) DO UPDATE SET value = excluded.value, rev = radio_setting.rev + 1",
            (id, key, value),
        )
    return True


def of_removed_radio(db: sqlite3.Connection, keys: Iterable[str]) -> bool:
    """Return whether a `radio/<id>/..` or `pair/..` key belongs to a removed radio."""
    ids = {found[0] for key in keys if (found := radio_key_of(key)) is not None} | {
        id for key in keys if (pair := pair_key_of(key)) is not None for id in pair[:2]
    }
    return any(
        db.execute("SELECT 1 FROM radio WHERE id = ? AND removed_at IS NOT NULL", (id,)).fetchone() for id in ids
    )


def _out_of_sets(db: sqlite3.Connection, id: int) -> None:
    """Drop a removed radio's id from the object and bulletin radio sets and the new-item defaults.

    A set that would become empty keeps the id: a set is never empty.
    """
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
    """Mark a radio removed (rows changed: 0 if missing or removed) and clear whatever selects it.

    The row and its settings stay, so history still names the radio.
    """
    if not db.execute("UPDATE radio SET removed_at = ? WHERE id = ? AND removed_at IS NULL", (at, id)).rowcount:
        return 0
    _out_of_sets(db, id)
    db.execute("DELETE FROM settings WHERE key = ? AND trim(value) = ?", (EMAIL_RADIO, str(id)))
    db.execute("DELETE FROM station_path WHERE radio_id = ?", (id,))
    row = db.execute("SELECT value FROM settings WHERE key = ?", (CHOICES,)).fetchone()
    if row is not None:
        chosen = _choices(str(row[0]))
        if id in chosen.values():
            write_setting(
                db, CHOICES, json.dumps({call: radio for call, radio in chosen.items() if radio != id}, sort_keys=True)
            )
    db.execute("DELETE FROM settings WHERE key GLOB ?", (f"radio/{int(id)}/*",))
    for (key,) in db.execute("SELECT key FROM settings WHERE key GLOB 'pair/*'").fetchall():
        if (pair := pair_key_of(str(key))) is not None and id in pair[:2]:
            db.execute("DELETE FROM settings WHERE key = ?", (key,))
    return 1


def put_kept(db: sqlite3.Connection, kept: Kept) -> None:
    """Write what a radio change keeps in force: ticks, e-mail radio, object and bulletin sets."""
    for radio, key in kept.ticks:
        put_radio_settings(db, radio, {key: "true"})
    if kept.email is not None:
        write_setting(db, EMAIL_RADIO, str(kept.email))
    for table, column, sets in (("own_object", "name", kept.objects), ("own_bulletin", "slot", kept.bulletins)):
        for name, radios in sets.items():
            db.execute(f"UPDATE {table} SET radios = ? WHERE {column} = ?", (text_of(radios), name))


def kept_by_rows(db: sqlite3.Connection, before: Iterable[RadioSpec]) -> Kept:
    """Return what the change from `before` to the stored radios keeps in force."""
    after = radios_from_rows(radio_rows(db), radio_settings(db))
    sets = [
        {str(name): ids_of(str(radios)) for name, radios in db.execute(f"SELECT {key}, radios FROM {table}")}
        for table, key in (("own_object", "name"), ("own_bulletin", "slot"))
    ]
    row = db.execute("SELECT value FROM settings WHERE key = ?", (EMAIL_RADIO,)).fetchone()
    email = ids_of(str(row[0])) if row is not None else ()
    return kept_in_force(before, after, sets[0], sets[1], email[0] if len(email) == 1 else None)


def _choices(text: str) -> dict[str, object]:
    """Return the stations' radios by call; an invalid row gives an empty dict."""
    try:
        kept = json.loads(text)
    except ValueError:
        return {}
    return kept if isinstance(kept, dict) else {}
