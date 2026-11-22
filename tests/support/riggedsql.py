"""A real SQLite connection that a test can sabotage statement by statement, for code that makes its
own connection (the migrations make theirs in `open_database`).
"""
import sqlite3
from collections.abc import Callable
from typing import Any

import pytest

Hook = Callable[[sqlite3.Connection, str], None]


def plain(conn: sqlite3.Connection, sql: str, *args: Any) -> sqlite3.Cursor:
    """A statement of the test's own on the connection, which the hooks do not see."""
    return sqlite3.Connection.execute(conn, sql, *args)


def rig_connect(monkeypatch: pytest.MonkeyPatch, before: Hook | None = None, after: Hook | None = None) -> list[str]:
    seen: list[str] = []
    real = sqlite3.connect

    class Rigged(sqlite3.Connection):
        def execute(self, sql: str, *args: Any) -> sqlite3.Cursor:
            seen.append(" ".join(sql.split())[:100])
            if before is not None:
                before(self, sql)
            cursor = super().execute(sql, *args)
            if after is not None:
                after(self, sql)
            return cursor

    def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        return real(*args, factory=Rigged, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    return seen


def fails_at(prefix: str, error: sqlite3.Error, times: int | None = None) -> Hook:
    """Raises `error` ahead of the statements that begin with `prefix` (the first `times` of them,
    all when None)."""
    count = [0]

    def hook(conn: sqlite3.Connection, sql: str) -> None:
        if sql.lstrip().upper().startswith(prefix.upper()):
            count[0] += 1
            if times is None or count[0] <= times:
                raise error

    return hook


def then_runs(prefix: str, statement: str) -> Hook:
    """After the statement that begins with `prefix`, runs `statement` on the same connection (the
    data changes under the code that has just written it)."""
    def hook(conn: sqlite3.Connection, sql: str) -> None:
        if sql.lstrip().startswith(prefix):
            plain(conn, statement)

    return hook
