"""SQL for `own_object` and `own_bulletin`, the objects and bulletins we send ourselves.

Functions of a connection on the database thread; none begins or commits a transaction."""

import sqlite3
from collections.abc import Sequence

from .dberror import Row, rows

OBJECT_COLUMNS = (
    "name",
    "kind",
    "lat",
    "lon",
    "symbol_table",
    "symbol_code",
    "comment",
    "course_deg",
    "speed_kmh",
    "path",
    "alive",
    "created_at",
    "updated_at",
    "sent",
    "last_sent_at",
    "qru_group",
    "on_request",
    "radios",
)
BULLETIN_COLUMNS = (
    "slot",
    "group_name",
    "text",
    "created_at",
    "sent",
    "first_sent_at",
    "last_sent_at",
    "radios",
    "lasts_h",
)


def object_columns() -> tuple[str, ...]:
    """Return the own_object columns in row order."""
    return OBJECT_COLUMNS


def _upsert(table: str, columns: tuple[str, ...]) -> str:
    update = ", ".join(f"{c} = excluded.{c}" for c in columns[1:])
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))}) ON CONFLICT({columns[0]}) DO UPDATE SET {update}"


_SAVE_BULLETIN = _upsert("own_bulletin", BULLETIN_COLUMNS)


def save_object(db: sqlite3.Connection, row: Sequence[object]) -> None:
    """Store an object, replacing one of the same name."""
    db.execute(_upsert("own_object", object_columns()), tuple(row))


def delete_object(db: sqlite3.Connection, name: str) -> int:
    """Delete an object; return the row count (0 or 1)."""
    return db.execute("DELETE FROM own_object WHERE name = ?", (name,)).rowcount


def all_objects(db: sqlite3.Connection) -> list[Row]:
    """Return every object, oldest first."""
    return rows(db.execute(f"SELECT {', '.join(object_columns())} FROM own_object ORDER BY created_at, name"))


def save_bulletin(db: sqlite3.Connection, row: Sequence[object]) -> None:
    """Store a bulletin, writing over the row of its slot."""
    db.execute(_SAVE_BULLETIN, tuple(row))


def delete_bulletin(db: sqlite3.Connection, slot: str) -> int:
    """Delete a bulletin; return the row count (0 or 1)."""
    return db.execute("DELETE FROM own_bulletin WHERE slot = ?", (slot,)).rowcount


def all_bulletins(db: sqlite3.Connection) -> list[Row]:
    """Return every bulletin, oldest first."""
    return rows(db.execute(f"SELECT {', '.join(BULLETIN_COLUMNS)} FROM own_bulletin ORDER BY created_at, slot"))
