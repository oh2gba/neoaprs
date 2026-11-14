"""Migrations 32 and 33 (neoaprs/migrationsteps32.py) for the tests: a database of the version before them, the steps run on it one by one, the shape they leave for the tests of the stores, and
the way back for `tests/support/migrated.step_back`.

    s = newest(path)                     # a database as the runner and then the radio round's steps leave it: what the tests of the older migrations read back
    db = old_database(path)              # a file of version 30, the connection a test inserts old rows on
    step_31(db)                          # what migration 31 leaves (the tables radio, radio_setting and _m31), decided from the rows
    run(db, _v32); run(db, _v33)         # a step as the runner runs it: in a transaction of its own, rolled back when it raises
    stepped(db)                          # the file says the version its shape is of, so that a Db opens it as it is
    through_33(db)                       # whatever of 31, 32 and 33 the file has not been through
    path = shaped(path)                  # a new file of the shape the stores are set to write (packetcodec.BY_RADIO), for a Db
    undo_33(db); undo_32(db)             # a database of the shape of 33 put back to that of 31 (the rows of radios 1 and 2 with it), for step_back
    f"SELECT call, path FROM {SAID}"     # what is said of each station as the one row it was before 33, for the read-backs of the older migrations' tests

`step_31` is a STAND-IN while migration 31 (package D1a) is not on this branch: it makes the radios as D1a's step decides them (the tables, a new installation only where no settings row and no row of
an installation is, radio 2 where a row names the HF radio, each radio's type and tickbox), as far as 32, 33 and the stores read it, and moves no settings row. The integration puts D1a's step in its
place: `step_31` becomes `_v31(db)` and `_KEPT`, `_HF_ROWS`, `_FM_TYPES` and `_on` go.

`SHAPES` and `shaped` end with the integration too: once migrations 32 and 33 are listed in MIGRATIONS every database is of the new shape, `SHAPES` is `(True,)` and `shaped` gives the path back."""
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from neoaprs import packetcodec
from neoaprs.clock import Clock, utcnow
from neoaprs.migrations import SCHEMA_VERSION, schema_version
from neoaprs.migrationsteps32 import _v32, _v33

if TYPE_CHECKING:
    from tests.support.migrated import Opened            # (only the name: migrated.py's step_back takes undo_32 and undo_33 from this module)

FORM = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
SHAPES: tuple[bool, ...] = (True,) if SCHEMA_VERSION >= 33 else (False, True)          # the shapes the stores are tested in: that of version 30 while it is the program's, and that of 33
SHAPE_IDS = {False: "version 30", True: "version 33"}
FM, HF = (1, "fm", "kiss", 1, 1), (2, "hf", "mercury", 1, 2)                           # (id, kind, type, enabled, position) of today's two radios, both on


def connect(path: str | Path) -> sqlite3.Connection:
    return sqlite3.connect(str(path), isolation_level=None)


def tables(db: sqlite3.Connection) -> set[str]:
    return {str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def columns(db: sqlite3.Connection, table: str) -> dict[str, str]:
    """The columns of a table: name to declared type."""
    return {str(r[1]): str(r[2]) for r in db.execute(f"PRAGMA table_info({table})")}


def old_database(path: str | Path, clock: Clock = utcnow) -> sqlite3.Connection:
    """A new database file put at version 30, the one before the radio round's steps, empty: the connection on which a test inserts rows of that version and then runs the steps."""
    from tests.support.migrated import opened, step_back            # (here, not at the top: migrated.py's step_back takes undo_32 and undo_33 from this module)
    opened(path, clock).close()
    db = connect(path)
    if schema_version(db) > 30:
        db.execute("DELETE FROM schema_history WHERE version > 30")
        step_back(db, 30)
        db.execute("PRAGMA user_version = 30")
    return db


_KEPT = ("own_object", "station_pref", "message", "message_attempt", "station", "packet")          # (as D1a's migration 31: a row in any is no new installation)
_HF_ROWS = (("message_attempt", "radio = 'hf'"), ("message", "radio = 'hf'"), ("own_object", "radio IN ('hf', 'both')"), ("station", "heard_hf > 0"), ("packet", "radio = 'hf'"))     # (rows that name the HF radio)
_FM_TYPES = ("kenwood-tnc2", "kenwood-d710", "kantronics", "kiss", "kiss-tcp", "dummy")


def _on(text: str | None, default: bool) -> bool:
    """A stored tickbox as the settings read it (D1a's `_on31`)."""
    word = (text or "").strip().lower()
    return True if word in ("1", "true", "yes", "on") else False if word in ("0", "false", "no", "off") else default


def step_31(db: sqlite3.Connection) -> None:
    """What migration 31 leaves in a database of version 30 (the STAND-IN, see the module), by the rules of D1a's step: the tables `radio`, `radio_setting` and `_m31`; no radio in a new installation (no
    settings row and no row of `_KEPT`); else radio 1 (fm), and radio 2 (hf) where a settings row or a row of `_HF_ROWS` names the HF radio; each radio's type and whether it is enabled written plainly,
    by the old rules. It moves no settings row."""
    db.execute(f"""CREATE TABLE radio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL CONSTRAINT radio_kind CHECK (kind IN ('fm', 'hf', 'lora')),
        type TEXT NOT NULL CONSTRAINT radio_type_present CHECK (type <> ''),
        name TEXT NOT NULL DEFAULT '' CONSTRAINT radio_name_length CHECK (length(name) <= 8),
        enabled INTEGER NOT NULL CONSTRAINT radio_enabled CHECK (enabled IN (0, 1)),
        position INTEGER NOT NULL,
        removed_at TEXT CONSTRAINT radio_removed_form CHECK (removed_at IS NULL OR removed_at GLOB {FORM})
    ) STRICT""")
    db.execute("CREATE UNIQUE INDEX radio_name ON radio (lower(name)) WHERE name <> '' AND removed_at IS NULL")
    db.execute("""CREATE TABLE radio_setting (
        radio_id INTEGER NOT NULL REFERENCES radio (id),
        key TEXT NOT NULL CONSTRAINT radio_setting_key_form CHECK (key <> '' AND key NOT GLOB '*/*'),
        value TEXT NOT NULL,
        rev INTEGER NOT NULL DEFAULT 1 CONSTRAINT radio_setting_rev_positive CHECK (rev >= 1),
        PRIMARY KEY (radio_id, key)
    ) STRICT""")
    db.execute("CREATE TABLE _m31 (hf_exists INTEGER NOT NULL CHECK (hf_exists IN (0, 1)), fm_on INTEGER NOT NULL CHECK (fm_on IN (0, 1)), hf_on INTEGER NOT NULL CHECK (hf_on IN (0, 1))) STRICT")
    settings = {str(key): str(value) for key, value in db.execute("SELECT key, value FROM settings")}
    if not settings and not any(db.execute(f"SELECT EXISTS (SELECT 1 FROM {table})").fetchone()[0] for table in _KEPT):
        db.execute("INSERT INTO _m31 (hf_exists, fm_on, hf_on) VALUES (0, 0, 0)")           # a new installation: no radio at all
        return
    try:
        choices = json.loads(settings.get("messages/radio_by_station", "{}"))
    except ValueError:
        choices = {}
    hf_exists = (any(key.startswith(("hf/", "mercury/")) for key in settings) or settings.get("tnc/profile", "").strip() == "mercury"
                 or (isinstance(choices, dict) and "hf" in choices.values()) or any(db.execute(f"SELECT EXISTS (SELECT 1 FROM {t} WHERE {where})").fetchone()[0] for t, where in _HF_ROWS))
    alone = settings.get("tnc/profile", "").strip() == "mercury" and "fm/enabled" not in settings and "hf/enabled" not in settings
    profile = None if alone else settings.get("tnc/profile")
    fm_type = "kenwood-tnc2" if profile is None and _on(settings.get("tnc/enter_kiss"), False) else profile.strip() if profile and profile.strip() in _FM_TYPES else "kiss"
    fm_on, hf_on = (False, True) if alone else (_on(settings.get("fm/enabled"), True), _on(settings.get("hf/enabled"), False))
    hf_type = settings.get("hf/profile", "").strip()
    db.execute("INSERT INTO radio (id, kind, type, name, enabled, position) VALUES (1, 'fm', ?, '', ?, 1)", (fm_type, int(fm_on)))
    if hf_exists:
        db.execute("INSERT INTO radio (id, kind, type, name, enabled, position) VALUES (2, 'hf', ?, '', ?, 2)", (hf_type if hf_type in ("mercury", "dummy-hf") else "mercury", int(hf_on)))
    db.execute("INSERT INTO _m31 (hf_exists, fm_on, hf_on) VALUES (?, ?, ?)", (int(hf_exists), int(fm_on), int(hf_on and hf_exists)))


def run(db: sqlite3.Connection, step: Callable[[sqlite3.Connection], None]) -> None:
    """A step as the runner of the migrations runs it (migrations._step): in a transaction of its own, all of it or none; what it raises comes out after the rollback."""
    db.execute("BEGIN IMMEDIATE")
    try:
        step(db)
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def stepped(db: sqlite3.Connection) -> None:
    """A database a test has run the round's steps on, one by one, says the version its shape is of where the runner lists them (it would run them again on the file otherwise); where it does not
    list them yet the file stays at version 30, which is the version this program opens."""
    if SCHEMA_VERSION >= 33 and "station_radio" in tables(db):
        db.execute("PRAGMA user_version = 33")


def through_33(db: sqlite3.Connection) -> None:
    """Whatever of migrations 31, 32 and 33 the database has not been through, each run as the runner runs it (the version and the history are left as they are): a database the runner brought to 33 is
    not touched."""
    if "radio" not in tables(db):
        run(db, step_31)
    if columns(db, "packet")["radio"] == "TEXT":
        run(db, _v32)
    if "station_radio" not in tables(db):
        run(db, _v33)


def newest(path: str | Path, clock: Clock = utcnow) -> "Opened":
    """A database file as this program's migrations and then the radio round's steps leave it: opened by the runner (a copy before, the steps it lists, the history), and brought through 33 where the
    runner does not list the round's steps yet. What a test of an older migration reads its rows back from."""
    from tests.support.migrated import opened
    found = opened(path, clock)
    through_33(found.db)
    return found


def heard_by(db: sqlite3.Connection) -> dict[str, dict[int, tuple[int, str | None, str]]]:
    """What each radio heard of each station (`station_radio`): call to (radio to (how many, when the last, the path of the last))."""
    found: dict[str, dict[int, tuple[int, str | None, str]]] = {}
    for call, radio, heard, last_at, last_path in db.execute("SELECT call, radio_id, heard, last_at, last_path FROM station_radio ORDER BY call, radio_id"):
        found.setdefault(str(call), {})[int(radio)] = (int(heard), last_at, str(last_path))
    return found


# What is said of each station as one row again, as `station_pref` held it before migration 33 moved the path to `station_path`: a subquery to read in the place of the table, for the tests of the older
# migrations (`f"SELECT call, path, hide_after_min FROM {SAID} ORDER BY call"`). The path is the station's on radio 1; a station of which only a path is said has the time its path was set.
SAID = ("(SELECT c.call AS call, (SELECT path FROM station_path p WHERE p.call = c.call AND p.radio_id = 1) AS path, s.hide_after_min AS hide_after_min, s.attempts AS attempts, COALESCE(s.rf_only, 0) AS rf_only, "
        "COALESCE(s.alert_on_air, 0) AS alert_on_air, s.alert_within_km AS alert_within_km, COALESCE(s.alert_direct, 0) AS alert_direct, "
        "COALESCE(s.updated_at, (SELECT updated_at FROM station_path p WHERE p.call = c.call AND p.radio_id = 1)) AS updated_at "
        "FROM (SELECT call FROM station_pref UNION SELECT call FROM station_path WHERE radio_id = 1) c LEFT JOIN station_pref s ON s.call = c.call)")


def said_of(db: sqlite3.Connection) -> list[tuple[str, str | None, int]]:
    """(call, its path on radio 1, RF only) of every station the operator said something of, by call: the path from `station_path`, RF only from `station_pref`, as migration 33 keeps them."""
    return [(str(call), path, int(rf_only)) for call, path, rf_only in db.execute(f"SELECT call, path, rf_only FROM {SAID} ORDER BY call")]


def shaped(path: Path, clock: Clock = utcnow, radios: tuple[tuple[int, str, str, int, int], ...] = (FM, HF)) -> Path:
    """A new database file of the shape the stores are set to write, for a Db to open: with `packetcodec.BY_RADIO` on it is brought through 33 and has `radios` (today's two, both on, when not given); else
    it is not made here at all (the Db makes it). The path, so that `store_at(shaped(path))` reads as one."""
    if packetcodec.BY_RADIO:
        from tests.support.migrated import opened
        opened(path, clock).close()
        db = connect(path)
        through_33(db)
        db.executemany("INSERT OR IGNORE INTO radio (id, kind, type, name, enabled, position) VALUES (?, ?, ?, '', ?, ?)", radios)
        db.close()
    return path


# The station table of version 30 as migration 1 made it and the later steps added to it (the columns after `packets`), word for word: `undo_33` makes it again from this text, so that a test of an older
# migration has the table a file of version 30 has (`last_path` NOT NULL with no default, every column in its place), which a column added back could not give.
STATION_30 = ("CREATE TABLE station (\n        call TEXT NOT NULL PRIMARY KEY CONSTRAINT station_call_present CHECK (call <> ''),\n        kind TEXT NOT NULL CONSTRAINT station_kind CHECK (kind IN ('station', 'object', 'item')),\n"
              "        reported_by TEXT NOT NULL,\n        symbol_table TEXT NOT NULL,\n        symbol_code TEXT NOT NULL,\n        lat REAL CONSTRAINT station_lat_range CHECK (lat BETWEEN -90 AND 90),\n"
              "        lon REAL CONSTRAINT station_lon_range CHECK (lon BETWEEN -180 AND 180),\n        altitude_m REAL,\n        course_deg INTEGER,\n        speed_kmh REAL,\n        first_heard TEXT NOT NULL,\n"
              "        last_heard TEXT NOT NULL,\n        last_position_at TEXT,\n        last_status TEXT NOT NULL,\n        last_comment TEXT NOT NULL,\n        packets INTEGER NOT NULL CONSTRAINT station_packets_count CHECK (packets >= 0),\n"
              "        last_path TEXT NOT NULL, heard_rf INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_heard_rf_count CHECK (heard_rf >= 0), heard_rf_gated INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_heard_rf_gated_count CHECK (heard_rf_gated >= 0), "
              "heard_is INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_heard_is_count CHECK (heard_is >= 0), heard_dummy INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_heard_dummy_count CHECK (heard_dummy >= 0), "
              f"last_rf_at TEXT CONSTRAINT station_last_rf_at_form CHECK (last_rf_at GLOB {FORM}), last_rf_gated_at TEXT CONSTRAINT station_last_rf_gated_at_form CHECK (last_rf_gated_at GLOB {FORM}), "
              f"last_is_at TEXT CONSTRAINT station_last_is_at_form CHECK (last_is_at GLOB {FORM}), last_dummy_at TEXT CONSTRAINT station_last_dummy_at_form CHECK (last_dummy_at GLOB {FORM}), "
              "position_via TEXT CONSTRAINT station_position_via CHECK (position_via IN ('rf', 'rf-gated', 'is', 'dummy')), heard_fm INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_heard_fm_count CHECK (heard_fm >= 0), "
              "heard_hf INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_heard_hf_count CHECK (heard_hf >= 0), last_fm_at TEXT, last_hf_at TEXT, snr REAL, rssi REAL, signal_at TEXT,\n"
              "        CONSTRAINT station_position_together CHECK ((lat IS NULL) = (lon IS NULL))\n    ) STRICT")


def undo_33(db: sqlite3.Connection) -> None:
    """Takes back what migration 33 did to the schema, with the rows of radios 1 and 2: the station table is that of version 30 again (`STATION_30`) with the counts and times of radios 1 and 2 and the
    path of the radio that heard the station last (radio 1 on a tie), `station_pref` has its path (the table as migration 22 made it), an object its word, and `_m31` says what the table `radio` says."""
    db.execute("ALTER TABLE station RENAME TO station_33")
    db.execute(STATION_30)
    kept = ", ".join(name for name in columns(db, "station_33"))
    of = "FROM station_radio r WHERE r.call = s.call"
    db.execute(f"INSERT INTO station ({kept}, heard_fm, last_fm_at, heard_hf, last_hf_at, last_path) SELECT {kept}, COALESCE((SELECT heard {of} AND r.radio_id = 1), 0), (SELECT last_at {of} AND r.radio_id = 1), "
               f"COALESCE((SELECT heard {of} AND r.radio_id = 2), 0), (SELECT last_at {of} AND r.radio_id = 2), COALESCE((SELECT last_path {of} ORDER BY r.last_at DESC, r.radio_id LIMIT 1), '') FROM station_33 s")
    db.execute("DROP TABLE station_radio")
    db.execute("DROP TABLE station_33")
    db.execute("ALTER TABLE station_pref RENAME TO station_pref_33")
    db.execute(f"""CREATE TABLE station_pref (
        call TEXT NOT NULL PRIMARY KEY CONSTRAINT station_pref_call_present CHECK (call <> ''),
        path TEXT CONSTRAINT station_pref_path_form CHECK (path = '' OR (path NOT GLOB '*[^A-Z0-9,-]*' AND path NOT GLOB ',*' AND path NOT GLOB '*,' AND path NOT GLOB '*,,*')),
        hide_after_min INTEGER CONSTRAINT station_pref_hide_range CHECK (hide_after_min BETWEEN 0 AND 10080),
        attempts INTEGER CONSTRAINT station_pref_attempts_range CHECK (attempts BETWEEN 1 AND 10),
        rf_only INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_pref_rf_only CHECK (rf_only IN (0, 1)),
        alert_on_air INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_pref_alert_on_air CHECK (alert_on_air IN (0, 1)),
        alert_within_km INTEGER CONSTRAINT station_pref_alert_within_range CHECK (alert_within_km BETWEEN 1 AND 1000),
        alert_direct INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_pref_alert_direct CHECK (alert_direct IN (0, 1)),
        updated_at TEXT NOT NULL CONSTRAINT station_pref_updated_form CHECK (updated_at GLOB {FORM}),
        CONSTRAINT station_pref_says_something CHECK (path IS NOT NULL OR hide_after_min IS NOT NULL OR attempts IS NOT NULL OR rf_only = 1 OR alert_on_air = 1 OR alert_within_km IS NOT NULL OR alert_direct = 1)
    ) STRICT""")
    kept = "hide_after_min, attempts, rf_only, alert_on_air, alert_within_km, alert_direct, updated_at"
    db.execute(f"INSERT INTO station_pref (call, path, {kept}) SELECT call, (SELECT path FROM station_path p WHERE p.call = s.call AND p.radio_id = 1), {kept} FROM station_pref_33 s")
    db.execute("INSERT INTO station_pref (call, path, updated_at) SELECT call, path, updated_at FROM station_path WHERE radio_id = 1 AND call NOT IN (SELECT call FROM station_pref)")
    db.execute("DROP TABLE station_pref_33")
    db.execute("DROP TABLE station_path")
    db.execute("ALTER TABLE own_object ADD COLUMN radio TEXT NOT NULL DEFAULT 'fm' CONSTRAINT own_object_radio CHECK (radio IN ('fm', 'hf', 'both'))")
    db.execute("UPDATE own_object SET radio = CASE radios WHEN '2' THEN 'hf' WHEN '1,2' THEN 'both' ELSE 'fm' END")
    db.execute("ALTER TABLE own_object DROP COLUMN radios")
    if "_m31" not in tables(db):
        db.execute("CREATE TABLE _m31 (hf_exists INTEGER NOT NULL, fm_on INTEGER NOT NULL, hf_on INTEGER NOT NULL) STRICT")
        db.execute("INSERT INTO _m31 (hf_exists, fm_on, hf_on) SELECT EXISTS (SELECT 1 FROM radio WHERE id = 2), COALESCE((SELECT enabled FROM radio WHERE id = 1), 0), COALESCE((SELECT enabled FROM radio WHERE id = 2), 0)")


def undo_32(db: sqlite3.Connection) -> None:
    """Takes back what migration 32 did to the schema, with the rows of radios 1 and 2: `packet.radio`, `message.radio` and `message_attempt.radio` are the words again (`fm`, `hf`, '' for none), each
    column as migration 25 made it and in its place among the columns of version 30."""
    for table, after in (("packet", (("snr", "REAL"), ("rssi", "REAL"))), ("message", (("failure", "TEXT CONSTRAINT message_failure CHECK (failure_back IN ('too_long_for_radio'))"), ("snr", "REAL"), ("rssi", "REAL"))),
                         ("message_attempt", ())):
        db.execute(f"ALTER TABLE {table} ADD COLUMN radio_word TEXT NOT NULL DEFAULT '' CONSTRAINT {table}_radio CHECK (radio_word IN ('', 'fm', 'hf'))")
        db.execute(f"UPDATE {table} SET radio_word = CASE radio WHEN 1 THEN 'fm' WHEN 2 THEN 'hf' ELSE '' END")
        db.execute(f"ALTER TABLE {table} DROP COLUMN radio")
        db.execute(f"ALTER TABLE {table} RENAME COLUMN radio_word TO radio")
        for column, declared in after:                  # (the columns that version 30 has after the word go after it again, each with its values)
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column}_back {declared}")
            db.execute(f"UPDATE {table} SET {column}_back = {column}")
            db.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            db.execute(f"ALTER TABLE {table} RENAME COLUMN {column}_back TO {column}")
