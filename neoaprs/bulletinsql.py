"""SQL statements of the bulletin table, run on the database thread (asked for by bulletinlog.py).

A row is a tuple in the order of BULLETIN_COLUMNS. Nothing here begins or commits a transaction."""

import sqlite3
from collections.abc import Sequence

from .dberror import Row as Row, rows

BULLETIN_COLUMNS = ("sender", "slot", "group_name", "text", "first_heard", "last_heard", "times_heard")
_LIST = ", ".join(BULLETIN_COLUMNS)
_PLACES = ", ".join("?" * len(BULLETIN_COLUMNS))
_UPDATE = ", ".join(f"{c} = excluded.{c}" for c in BULLETIN_COLUMNS[2:])


def save_bulletin(db: sqlite3.Connection, row: Sequence[object]) -> None:
    """Insert a bulletin, replacing the one with the same sender and slot."""
    db.execute(
        f"INSERT INTO bulletin ({_LIST}) VALUES ({_PLACES}) ON CONFLICT(sender, slot) DO UPDATE SET {_UPDATE}",
        tuple(row),
    )


def delete_bulletin(db: sqlite3.Connection, sender: str, slot: str) -> int:
    """Delete a bulletin; return the number of rows removed (0 or 1)."""
    return db.execute("DELETE FROM bulletin WHERE sender = ? AND slot = ?", (sender, slot)).rowcount


def all_bulletins(db: sqlite3.Connection) -> list[Row]:
    """Return every bulletin, last heard first."""
    return rows(db.execute(f"SELECT {_LIST} FROM bulletin ORDER BY last_heard DESC, sender, slot"))
