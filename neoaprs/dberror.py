"""The errors of the database layer.

`StoreError` is what the rest of the program catches; SQLite's own exceptions are never wrapped.
SQLite's names are re-exported here so that only the homes of SQL import sqlite3."""

import sqlite3
from collections.abc import Iterable, Sequence
from typing import Any

Connection = sqlite3.Connection
SqlError = sqlite3.Error
IntegrityError = sqlite3.IntegrityError
OperationalError = sqlite3.OperationalError

# A row from the *sql.py modules, columns in the module's order.
Row = tuple[Any, ...]


def rows(cursor: Iterable[Sequence[Any]]) -> list[Row]:
    """Return every row of a cursor as a plain tuple."""
    return [tuple(r) for r in cursor]


def limit(count: int) -> int:
    """Return a LIMIT for `count`, clamped at 0: SQLite treats a negative LIMIT as no limit."""
    return max(0, count)


class StoreError(Exception):
    pass


class DbError(StoreError):
    """The Db actor was used wrongly, or has stopped."""


class DbClosed(DbError):
    """The database is not open (not started, closed, or its thread has gone)."""

    def __init__(self, why: str = "the database is not open") -> None:
        super().__init__(why)


class NestedUse(DbError):
    """A function run by the database thread asked the database thread for something, which would
    deadlock."""
