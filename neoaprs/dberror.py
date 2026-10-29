"""The errors of the database layer. `StoreError` is the one the rest of the program catches ("the database is not open", a settings read that failed); the actor's
own errors are kinds of it, so that every `except StoreError` also catches them. What SQLite raises (sqlite3.IntegrityError, OperationalError ...) is never wrapped:
it comes out of `await db.write(...)` as it was raised.

This is also the one place where the classes that use the database thread take SQLite's own names from (`Connection`, `SqlError`, `IntegrityError`, `OperationalError`: the same objects as
sqlite3's), so that nothing but the homes of SQL imports sqlite3 (tests/test_architecture.py, docs/ARCHITECTURE.md)."""
import sqlite3
from collections.abc import Iterable, Sequence
from typing import Any

Connection = sqlite3.Connection              # what the database thread hands to a statement function
SqlError = sqlite3.Error                     # what SQLite raises, and what `except` clauses catch
IntegrityError = sqlite3.IntegrityError
OperationalError = sqlite3.OperationalError

Row = tuple[Any, ...]                        # a row the statements of the *sql.py modules give back: the columns in the order of the module's column list


def rows(cursor: Iterable[Sequence[Any]]) -> list[Row]:
    """Every row of a cursor as a plain tuple."""
    return [tuple(r) for r in cursor]


def limit(count: int) -> int:
    """The LIMIT for a count somebody asked for: a count below zero asks for none (SQLite takes a negative LIMIT for no limit at all)."""
    return max(0, count)


class StoreError(Exception):
    pass


class DbError(StoreError):
    """The Db actor was used wrongly, or has stopped."""


class DbClosed(DbError):
    """The database is not open (not started, closed, or its thread has gone); the words are those of Store."""

    def __init__(self, why: str = "the database is not open") -> None:
        super().__init__(why)


class NestedUse(DbError):
    """A function that the database thread runs asked the database thread for something: it would wait for itself. Do the work in the same function, on the connection it was given."""
