"""The statements of the tables of what we send of our own accord, `own_object` and `own_bulletin`, as functions of a connection that the database thread runs (ownlog.py is the part that asks for them).

A row is a tuple in the order of OBJECT_COLUMNS or BULLETIN_COLUMNS; the codec between a row and a value is ownlog.py's. Nothing here begins or commits a transaction.

An object names the radios it goes out on in `radios`: their ids in the table `radio`, ascending, separated by commas (migration 33); a bulletin the same (migration 34)."""
import sqlite3
from collections.abc import Sequence

from .dberror import Row, rows

OBJECT_COLUMNS = ("name", "kind", "lat", "lon", "symbol_table", "symbol_code", "comment", "course_deg", "speed_kmh", "path", "alive", "created_at", "updated_at", "sent", "last_sent_at", "qru_group", "on_request", "radios")
BULLETIN_COLUMNS = ("slot", "group_name", "text", "created_at", "sent", "first_sent_at", "last_sent_at", "radios")


def object_columns() -> tuple[str, ...]:
    """The columns of own_object in the order of an object's row."""
    return OBJECT_COLUMNS


def _upsert(table: str, columns: tuple[str, ...]) -> str:
    update = ", ".join(f"{c} = excluded.{c}" for c in columns[1:])
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))}) ON CONFLICT({columns[0]}) DO UPDATE SET {update}"


_SAVE_BULLETIN = _upsert("own_bulletin", BULLETIN_COLUMNS)


def save_object(db: sqlite3.Connection, row: Sequence[object]) -> None:
    """Keeps an object, replacing the one of the same name."""
    db.execute(_upsert("own_object", object_columns()), tuple(row))


def delete_object(db: sqlite3.Connection, name: str) -> int:
    """Removes an object; how many rows it found (0 or 1)."""
    return db.execute("DELETE FROM own_object WHERE name = ?", (name,)).rowcount


def all_objects(db: sqlite3.Connection) -> list[Row]:
    """Every object, the oldest first."""
    return rows(db.execute(f"SELECT {', '.join(object_columns())} FROM own_object ORDER BY created_at, name"))


def save_bulletin(db: sqlite3.Connection, row: Sequence[object]) -> None:
    """Keeps a bulletin, replacing the one of the same slot."""
    db.execute(_SAVE_BULLETIN, tuple(row))


def delete_bulletin(db: sqlite3.Connection, slot: str) -> int:
    """Removes a bulletin; how many rows it found (0 or 1)."""
    return db.execute("DELETE FROM own_bulletin WHERE slot = ?", (slot,)).rowcount


def all_bulletins(db: sqlite3.Connection) -> list[Row]:
    """Every bulletin, the oldest first."""
    return rows(db.execute(f"SELECT {', '.join(BULLETIN_COLUMNS)} FROM own_bulletin ORDER BY created_at, slot"))
