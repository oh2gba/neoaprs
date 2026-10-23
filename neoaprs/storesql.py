"""The statements of the settings, as functions of a connection (the packet and station statements are packetsql.py's, the messages' messagesql.py's).

`Store` (store.py) runs them on the database thread; the tools that own a connection of their own call them on it. Nothing here begins, commits or rolls back a transaction: a write that is
more than one statement (`write_settings`) is in the transaction of whoever runs it (`Db.write`, or `transaction()` of dbfile.py), and the single statements are each their own when the
connection is in autocommit.
"""
import sqlite3

from .dberror import SettingsConflict

Settings = dict[str, str]


def read_settings(db: sqlite3.Connection) -> Settings:
    return {str(key): str(value) for key, value in db.execute("SELECT key, value FROM settings ORDER BY key")}


def read_setting(db: sqlite3.Connection, key: str) -> str | None:
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else None


def read_setting_rev(db: sqlite3.Connection, key: str) -> int:
    """How many times the setting has been written, 0 when it is not there: what to compare to see that it changed."""
    row = db.execute("SELECT rev FROM settings WHERE key = ?", (key,)).fetchone()
    return int(row[0]) if row else 0


def write_setting(db: sqlite3.Connection, key: str, value: str, expect_rev: int | None = None) -> int:
    """The setting replaced in one statement; its new revision. With `expect_rev`, only if nobody has written it since that revision (0: since it was not there); otherwise
    SettingsConflict, and nothing is changed (the writer's copy is out of date)."""
    if expect_rev is not None and read_setting_rev(db, key) != expect_rev:
        raise SettingsConflict(f"the setting {key} was changed meanwhile (by another writer): it is read again, please make the change again")
    db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, rev = settings.rev + 1", (key, value))
    return read_setting_rev(db, key)


def write_settings(db: sqlite3.Connection, data: Settings) -> None:
    """Every key of `data` written, in the transaction of the caller; the other settings stay."""
    for key, value in data.items():
        write_setting(db, key, value)


def delete_setting(db: sqlite3.Connection, key: str) -> None:
    db.execute("DELETE FROM settings WHERE key = ?", (key,))
