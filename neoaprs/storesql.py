"""The statements of the settings, as functions of a connection (the packet and station statements are packetsql.py's, the messages' messagesql.py's).

`Store` (store.py) runs them on the database thread; the tools that own a connection of their own call them on it. Nothing here begins, commits or rolls back a transaction: a write that is
more than one statement (`write_settings`) is in the transaction of whoever runs it (`Db.write`, or `transaction()` of dbfile.py), and the single statements are each their own when the
connection is in autocommit.
"""
import sqlite3

Settings = dict[str, str]


def read_settings(db: sqlite3.Connection) -> Settings:
    return {str(key): str(value) for key, value in db.execute("SELECT key, value FROM settings ORDER BY key")}


def read_setting(db: sqlite3.Connection, key: str) -> str | None:
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else None


def write_setting(db: sqlite3.Connection, key: str, value: str) -> None:
    """The setting replaced in one statement."""
    db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, rev = settings.rev + 1", (key, value))


def write_settings(db: sqlite3.Connection, data: Settings) -> None:
    """Every key of `data` written, in the transaction of the caller; the other settings stay."""
    for key, value in data.items():
        write_setting(db, key, value)


def delete_setting(db: sqlite3.Connection, key: str) -> None:
    db.execute("DELETE FROM settings WHERE key = ?", (key,))
