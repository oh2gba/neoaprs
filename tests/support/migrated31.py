"""Migration 31 (neoaprs/migrationsteps31.py: the radios as rows) for the tests: a database as version 30 left it, the step run alone on it as the runner runs a step, what the step added taken out again
(`undo_31`, for `step_back` of tests/support/migrated.py), and the reading of a database that works before and after the step, for the tests of the older migrations that store today's flat keys of the radios.

    db = at_thirty(path, clock)      # a new file put back to version 30, open (autocommit), for the old rows of a test
    run_31(db)                       # migration 31 in a transaction of its own
    radio_tables(path)               # a file with the radios' tables whatever the newest migration is, for the tests of radiosql.py and of the Store
    station_rows(db)                 # the rows of `settings` that are the station's, with their revisions
    stored_config(db)                # the settings in force as the program reads this database: through the radios once they are rows
    state_row(db, "beacon/last_sent_at")     # a row of the daemon's state under the name it has in this database
    flat_row(db, "beacon/path")              # a radio's own setting that was stored under a flat key, with its revision, wherever it is in this database
"""
import json
import sqlite3
from pathlib import Path

from neoaprs.clock import Clock, utcnow
from neoaprs.config import LAST_PORT, STATION_KEYS, Config
from neoaprs.configradios import radios_from_rows
from neoaprs.migrationsteps31 import _v31
from neoaprs.radiosql import radio_rows, radio_settings
from neoaprs.storesql import read_settings

STATE_31 = {"serial/last_port": LAST_PORT, "beacon/last_sent_at": "radio/1/beacon_last_sent_at", "hf/beacon_last_sent_at": "radio/2/beacon_last_sent_at"}      # a state row of before, and its name once migration 31 ran
OWN_31 = {"serial/port": (1, "port"), "serial/baud": (1, "baud"), "tcp/host": (1, "tcp_host"), "tcp/port": (1, "tcp_port"), "beacon/path": (1, "path"), "digi/enabled": (1, "digipeat"),
          "mercury/sound_card": (2, "sound_card"), "mercury/keying": (2, "keying"), "mercury/tx_gain_db": (2, "tx_gain_db")}        # a flat key of before, and the radio and its own key it is once migration 31 ran
PATH_FORM = "path = '' OR (path NOT GLOB '*[^A-Z0-9,-]*' AND path NOT GLOB ',*' AND path NOT GLOB '*,' AND path NOT GLOB '*,,*')"                              # today's station_pref_path_form (migration 22)


def undo_31(db: sqlite3.Connection) -> None:
    """Takes out of a migrated database what migration 31 added to the schema: the tables of the radios, and `_m31` where migration 33 has not dropped it yet. Radios 1 and 2 go back into the flat rows
    first (`_flat_again`), so that migration 31 run again on the file makes the same radios with the same settings."""
    if has_table(db, "radio"):
        _flat_again(db)
    for table in ("_m31", "radio_setting", "radio"):
        db.execute(f"DROP TABLE IF EXISTS {table}")


def _flat_again(db: sqlite3.Connection) -> None:
    """Radios 1 and 2 as the flat settings rows of version 30: each radio's own settings under its flat key with its revision, its type and its tickbox, the state rows under their old names, and the
    stations' choices as the words `fm` and `hf` with the revision they had before migration 31 counted it up. The type and the tickbox rows are written at revision 1 in the program's words, whatever they were before 31. A radio of another id has no flat rows and is dropped with the tables."""
    for flat, (radio, own) in OWN_31.items():
        db.execute("INSERT OR REPLACE INTO settings (key, value, rev) SELECT ?, value, rev FROM radio_setting WHERE radio_id = ? AND key = ?", (flat, radio, own))
    for radio, profile, tickbox in ((1, "tnc/profile", "fm/enabled"), (2, "hf/profile", "hf/enabled")):
        for type_, enabled in db.execute("SELECT type, enabled FROM radio WHERE id = ?", (radio,)).fetchall():
            db.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ((profile, str(type_)), (tickbox, "true" if enabled else "false")))
    for old, new in STATE_31.items():
        db.execute("UPDATE OR REPLACE settings SET key = ? WHERE key = ?", (old, new))
    row = db.execute("SELECT value FROM settings WHERE key = 'messages/radio_by_station'").fetchone()
    if row is not None:
        words = {call: {1: "fm", 2: "hf"}[radio] for call, radio in json.loads(str(row[0])).items() if radio in (1, 2)}
        db.execute("UPDATE settings SET value = ?, rev = max(rev - 1, 1) WHERE key = 'messages/radio_by_station'", (json.dumps(words, sort_keys=True),))


def has_table(db: sqlite3.Connection, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def at_thirty(path: Path, clock: Clock = utcnow) -> sqlite3.Connection:
    """A new database file as version 30 left it (before the radios were rows), open in autocommit: the test inserts the rows of an old installation and runs migration 31 on them."""
    from tests.support.migrated import opened, step_back      # (here, not at the top: migrated.py's step_back calls undo_31 of this module)
    opened(path, clock).close()
    db = sqlite3.connect(path, isolation_level=None)
    db.execute("DELETE FROM schema_history WHERE version >= 31")
    step_back(db, 30)
    db.execute("PRAGMA user_version = 30")
    return db


def run_31(db: sqlite3.Connection) -> None:
    """Migration 31 alone, in a transaction of its own (all of it or none), as the runner runs a step."""
    db.execute("BEGIN IMMEDIATE")
    try:
        _v31(db)
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def radio_tables(path: Path, clock: Clock = utcnow) -> None:
    """A new database file with the tables of the radios and what Remove touches beside them, whatever the newest migration of this tree is: where migration 31 is not among the steps yet it is run here
    (the file keeps its version, so the program opens it), and where migration 33 is not, the objects' `radios` and the table `station_path` are made as the work breakdown's section 1.6 writes them."""
    from tests.support.migrated import opened
    opened(path, clock).close()
    db = sqlite3.connect(path, isolation_level=None)
    if not has_table(db, "radio"):
        run_31(db)
    if not db.execute("SELECT 1 FROM pragma_table_info('own_object') WHERE name = 'radios'").fetchone():
        db.execute("ALTER TABLE own_object ADD COLUMN radios TEXT NOT NULL DEFAULT '1' CHECK (radios GLOB '[1-9]*' AND radios NOT GLOB '*[^0-9,]*')")
    if not has_table(db, "station_path"):
        db.execute(f"""CREATE TABLE station_path (call TEXT NOT NULL CHECK (call <> ''), radio_id INTEGER NOT NULL REFERENCES radio (id), path TEXT NOT NULL CHECK ({PATH_FORM}),
            updated_at TEXT NOT NULL, PRIMARY KEY (call, radio_id)) STRICT""")
    db.close()


def station_rows(db: sqlite3.Connection) -> dict[str, tuple[str, int]]:
    """The rows of `settings` that are the station's own settings (config.STATION_KEYS), each with its value and its revision: the rows no migration of the radios moves."""
    return {str(key): (str(value), int(rev)) for key, value, rev in db.execute("SELECT key, value, rev FROM settings") if key in STATION_KEYS}


def stored_config(db: sqlite3.Connection) -> Config:
    """The settings in force as the program reads this database: from the rows of `settings` and, once the radios are rows (migration 31 ran), from the stored radios; before that from the flat keys."""
    rows = read_settings(db)
    return Config.from_data(rows, radios=radios_from_rows(radio_rows(db), radio_settings(db))) if has_table(db, "radio") else Config.from_data(rows)


def state_row(db: sqlite3.Connection, key: str) -> tuple[str, int] | None:
    """A row of the daemon's state that a version before the radios kept under `key`, with its revision: under that name, or under its radio's once migration 31 ran; None when there is none."""
    row = db.execute("SELECT value, rev FROM settings WHERE key IN (?, ?)", (key, STATE_31.get(key, key))).fetchone()
    return None if row is None else (str(row[0]), int(row[1]))


def flat_row(db: sqlite3.Connection, key: str) -> tuple[str, int] | None:
    """A radio's own setting that a version before the radios stored under the flat key `key` (OWN_31), with its revision: the row of `settings`, or the radio's own row once migration 31 ran; None when
    there is none."""
    radio, own = OWN_31[key]
    row = db.execute("SELECT value, rev FROM radio_setting WHERE radio_id = ? AND key = ?", (radio, own)).fetchone() if has_table(db, "radio_setting") else db.execute("SELECT value, rev FROM settings WHERE key = ?", (key,)).fetchone()
    return None if row is None else (str(row[0]), int(row[1]))
