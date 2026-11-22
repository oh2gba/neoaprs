"""SQL for the settings table, as functions of a connection.

Nothing here begins, commits or rolls back a transaction: a multi-statement write
(`write_settings`) runs in the caller's transaction.
"""
import sqlite3

Settings = dict[str, str]


def read_settings(db: sqlite3.Connection) -> Settings:
    return {str(key): str(value) for key, value in db.execute("SELECT key, value FROM settings ORDER BY key")}


def read_setting(db: sqlite3.Connection, key: str) -> str | None:
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else None


def write_setting(db: sqlite3.Connection, key: str, value: str) -> None:
    """Replace the setting and bump its revision."""
    db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, rev = settings.rev + 1", (key, value))


def write_settings(db: sqlite3.Connection, data: Settings) -> None:
    """Write every key of `data`; other settings stay."""
    for key, value in data.items():
        write_setting(db, key, value)


def delete_setting(db: sqlite3.Connection, key: str) -> None:
    db.execute("DELETE FROM settings WHERE key = ?", (key,))
