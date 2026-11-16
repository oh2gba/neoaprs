"""Migration 34 (neoaprs/migrationsteps34.py) for the tests: a database as 0.20.0 and 0.20.1 leave it (version 33: made by every step, then put back by tests/support/migrated.step_back), with the radios,
the main radio, the ticks, the objects and the bulletins a test gives it, and the rows read back after the step.

    path = version_33(tmp_path / DB_NAME, Old(radios=(fm(1), hf(2)), chosen=2))      # the file, closed: the runner opens it (`opened`), or a test runs the step on it (`connect`, `run`)
    ticks(db, "status")                                                                # each radio's stored row of a key, by id
"""
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from neoaprs.clock import Clock, utcnow
from tests.support.migrated import opened, step_back

STAMP = "2026-11-16T05:59:00.000000Z"                 # (a minute before the day of tests/test_no_main_radio.py: what was kept is due at its start)
GONE = "2026-11-15T12:00:00.000000Z"


@dataclass(frozen=True)
class Radio:
    """A radio as 0.20.0 stored it: its row of `radio` and its own settings (`radio_setting`)."""
    id: int
    kind: str
    type: str
    enabled: bool = True
    position: int | None = None          # (None: its id)
    removed: bool = False
    own: Mapping[str, str] = field(default_factory=dict)


def radio(id: int, kind: str, type: str, enabled: bool = True, position: int | None = None, removed: bool = False, **own: str) -> Radio:
    return Radio(id, kind, type, enabled, position, removed, own)


def fm(id: int, enabled: bool = True, position: int | None = None, removed: bool = False, type: str = "dummy", **own: str) -> Radio:
    return radio(id, "fm", type, enabled, position, removed, **own)


def hf(id: int, enabled: bool = True, position: int | None = None, removed: bool = False, type: str = "dummy-hf", **own: str) -> Radio:
    return radio(id, "hf", type, enabled, position, removed, **own)


def lora(id: int, enabled: bool = True, position: int | None = None, removed: bool = False, type: str = "dummy-lora", **own: str) -> Radio:
    return radio(id, "lora", type, enabled, position, removed, **own)


def monitor(id: int, enabled: bool = True, position: int | None = None) -> Radio:
    return radio(id, "fm", "tnc-text", enabled, position)


@dataclass(frozen=True)
class Old:
    """A station as 0.20.0 or 0.20.1 left it: its radios, the main radio chosen (`station/main_radio`, None for no row), the station's rows (`settings`), our objects (name to their radios, "1,2") and
    bulletins (slot to text)."""
    radios: tuple[Radio, ...] = ()
    chosen: int | None = None
    settings: Mapping[str, str] = field(default_factory=dict)
    objects: Mapping[str, str] = field(default_factory=dict)
    bulletins: Mapping[str, str] = field(default_factory=dict)


def connect(path: str | Path) -> sqlite3.Connection:
    return sqlite3.connect(str(path), isolation_level=None)


def version_33(path: Path, old: Old, clock: Clock = utcnow) -> Path:
    """A database file of version 33 with the rows of `old`, closed; the path."""
    opened(path, clock).close()
    db = connect(path)
    db.execute("DELETE FROM schema_history WHERE version >= 34")
    step_back(db, 33)
    db.execute("PRAGMA user_version = 33")
    fill(db, old)
    db.close()
    return path


def fill(db: sqlite3.Connection, old: Old) -> None:
    """The rows of `old` in a database of version 33."""
    for r in old.radios:
        db.execute("INSERT INTO radio (id, kind, type, name, enabled, position, removed_at) VALUES (?, ?, ?, '', ?, ?, ?)", (r.id, r.kind, r.type, int(r.enabled), r.id if r.position is None else r.position,
                                                                                                                   GONE if r.removed else None))
        db.executemany("INSERT INTO radio_setting (radio_id, key, value) VALUES (?, ?, ?)", [(r.id, key, value) for key, value in r.own.items()])
    rows = {**old.settings, **({} if old.chosen is None else {"station/main_radio": str(old.chosen)})}
    db.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", list(rows.items()))
    for name, radios in old.objects.items():
        db.execute("INSERT INTO own_object (name, kind, lat, lon, symbol_table, symbol_code, comment, alive, created_at, updated_at, radios) VALUES (?, 'object', 60.2, 24.9, '/', 'r', 'ours', 1, ?, ?, ?)",
                   (name, STAMP, STAMP, radios))
    for slot, text in old.bulletins.items():
        db.execute("INSERT INTO own_bulletin (slot, group_name, text, created_at) VALUES (?, '', ?, ?)", (slot, text, STAMP))


def ticks(db: sqlite3.Connection, key: str) -> dict[int, str]:
    """Each radio's stored row of the key, by id (a radio without one is not there)."""
    return {int(id): str(value) for id, value in db.execute("SELECT radio_id, value FROM radio_setting WHERE key = ? ORDER BY radio_id", (key,))}


def settings(db: sqlite3.Connection) -> dict[str, str]:
    return {str(key): str(value) for key, value in db.execute("SELECT key, value FROM settings")}


def places(db: sqlite3.Connection) -> dict[int, int]:
    """The place of each live radio, by id."""
    return {int(id): int(position) for id, position in db.execute("SELECT id, position FROM radio WHERE removed_at IS NULL ORDER BY id")}


def sets(db: sqlite3.Connection, table: str) -> dict[str, str]:
    """The radios of each object (`own_object`) or bulletin (`own_bulletin`), by name or slot."""
    key = "name" if table == "own_object" else "slot"
    return {str(name): str(radios) for name, radios in db.execute(f"SELECT {key}, radios FROM {table}")}
