"""What the safety tests share: a database connection that fails on demand, and a second, independent connection that sees only what is committed."""
import sqlite3
from pathlib import Path
from typing import Any


def raw(path: str | Path) -> sqlite3.Connection:
    """A second, independent connection (what a tool is): sees only what is committed."""
    db = sqlite3.connect(str(path), isolation_level=None, timeout=30)
    db.execute("PRAGMA busy_timeout=30000")
    return db


class Injected(sqlite3.OperationalError):
    pass


class FaultyConnection(sqlite3.Connection):
    """A connection whose Nth statement fails with what a full disk or a locked file raises. `fail_at`: the number of the statement (1 is the next one) or None;
    `sticky`: every statement from that one on fails (the disk stays full), but not the ROLLBACK, which needs no space; `statements`: how many were issued, `log`: their text."""
    fail_at: int | None = None
    sticky: bool = False
    message: str = "database or disk is full"
    statements: int = 0
    log: list[str]

    def _tick(self, sql: str) -> None:
        if not hasattr(self, "log"):
            self.log = []
        self.statements += 1
        self.log.append(" ".join(sql.split())[:80])
        if self.fail_at is not None and (self.statements == self.fail_at or (self.sticky and self.statements > self.fail_at and not sql.lstrip().upper().startswith("ROLLBACK"))):
            raise Injected(self.message)

    def execute(self, sql: str, *args: Any) -> sqlite3.Cursor:
        self._tick(sql)
        return super().execute(sql, *args)

    def executemany(self, sql: str, *args: Any) -> sqlite3.Cursor:
        self._tick(sql)
        return super().executemany(sql, *args)
