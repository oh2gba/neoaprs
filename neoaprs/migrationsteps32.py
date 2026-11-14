"""Migrations 32 and 33, the radio round's steps after 31 (migrationsteps31.py, which makes the table `radio` and decides which radios a database has), frozen here beside migrations.py (which lists them in
MIGRATIONS and runs them): the same rules as for the earlier ones (migrationsteps22on.py), a step is never edited once it has been released. Both read only the database: what 31 decided is in the table `radio`
(today's FM radio is radio 1, today's HF radio is radio 2, where the database has them)."""
import sqlite3

from .dberror import StoreError


def _v32(db: sqlite3.Connection) -> None:
    """Any number of radios: a packet, a message that came in and an attempt of ours name their radio by its id in the table `radio` (migration 31), no longer by the word of one of two. `packet.radio`,
    `message.radio` and `message_attempt.radio` become INTEGER, null for none: `fm` is radio 1 and `hf` is radio 2; a packet with no word that did not come from the internet is radio 1 (as migration 25 set
    the packets of the air it found); a packet from the internet, a message of ours (its attempts say) and a row kept before there were two radios have none, as they had.

    A column's type cannot be changed in place: the id goes into a new column, the old one is dropped and the new one takes its name, so that every statement that names `radio` reads the id. Dropping a
    column writes every row of the table again where it lies, so the file does not grow, and the write-ahead log holds the table once until the step is committed (the packet table is nearly all of a
    file). That needs SQLite 3.35; an older one is refused before anything is changed."""
    version = str(db.execute("SELECT sqlite_version()").fetchone()[0])
    if tuple(int(part) for part in version.split(".")[:2]) < (3, 35):
        raise StoreError(f"this step needs SQLite 3.35 or later and this Python has SQLite {version}; nothing was changed (the copy made before the migration is in backup/ beside the database)")
    for table in ("packet", "message", "message_attempt"):
        db.execute(f"ALTER TABLE {table} ADD COLUMN radio_id INTEGER CONSTRAINT {table}_radio_known REFERENCES radio (id)")
    db.execute("UPDATE packet SET radio_id = CASE radio WHEN 'hf' THEN 2 ELSE 1 END WHERE radio <> '' OR via <> 'is'")
    for table in ("message", "message_attempt"):
        db.execute(f"UPDATE {table} SET radio_id = CASE radio WHEN 'fm' THEN 1 WHEN 'hf' THEN 2 END WHERE radio <> ''")
    for table in ("packet", "message", "message_attempt"):
        db.execute(f"ALTER TABLE {table} DROP COLUMN radio")
        db.execute(f"ALTER TABLE {table} RENAME COLUMN radio_id TO radio")


def _v33(db: sqlite3.Connection) -> None:
    """Any number of radios, the stations and our objects. What each radio heard of a station is a row of `station_radio` (the station, the radio, how many packets, when the last, and the digipeaters of the
    last packet that radio heard): `station.heard_fm` and `last_fm_at` are radio 1's row, `heard_hf` and `last_hf_at` radio 2's, each where the count is not 0, and `station.last_path` goes to the radio that
    heard the station last (radio 1 when both did at the same time; the one row when there is one); the five columns leave the station. The path the operator gave a station is the path on a radio,
    `station_path` (the station, the radio, the path, when it was set): every `station_pref.path` is the station's path on radio 1, the column leaves `station_pref` (rebuilt: its CHECK names the column),
    and a row that said nothing but a path is gone with it; RF only and the alerts stay by station. An object of ours names the radios it goes out on, `own_object.radios` (their ids, ascending, separated
    by commas) in place of `radio`: `fm` is 1, `hf` is 2, `both` is 1,2; `hf` and `both` are 1 on a database without radio 2. A radio that is off keeps its
    objects: the operator's choice is there when it is switched on again. The table `_m31`, migration 31's note of what it decided, is dropped: the table `radio` says it. Any doubt raises: the rollback leaves everything as it was."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    fm_last = "(last_fm_at IS NOT NULL AND (last_hf_at IS NULL OR last_fm_at >= last_hf_at))"
    db.execute("""CREATE TABLE station_radio (
        call TEXT NOT NULL CONSTRAINT station_radio_station REFERENCES station (call) ON DELETE CASCADE,
        radio_id INTEGER NOT NULL CONSTRAINT station_radio_radio_known REFERENCES radio (id),
        heard INTEGER NOT NULL CONSTRAINT station_radio_heard_count CHECK (heard >= 0),
        last_at TEXT, last_path TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (call, radio_id)
    ) STRICT""")
    db.execute(f"INSERT INTO station_radio (call, radio_id, heard, last_at, last_path) SELECT call, 1, heard_fm, last_fm_at, CASE WHEN heard_hf = 0 OR {fm_last} THEN last_path ELSE '' END FROM station WHERE heard_fm <> 0")
    db.execute(f"INSERT INTO station_radio (call, radio_id, heard, last_at, last_path) SELECT call, 2, heard_hf, last_hf_at, CASE WHEN heard_fm = 0 OR NOT {fm_last} THEN last_path ELSE '' END FROM station WHERE heard_hf <> 0")
    for column in ("heard_fm", "heard_hf", "last_fm_at", "last_hf_at", "last_path"):
        db.execute(f"ALTER TABLE station DROP COLUMN {column}")
    db.execute(f"""CREATE TABLE station_path (
        call TEXT NOT NULL CONSTRAINT station_path_call_present CHECK (call <> ''),
        radio_id INTEGER NOT NULL CONSTRAINT station_path_radio_known REFERENCES radio (id),
        path TEXT NOT NULL CONSTRAINT station_path_form CHECK (path = '' OR (path NOT GLOB '*[^A-Z0-9,-]*' AND path NOT GLOB ',*' AND path NOT GLOB '*,' AND path NOT GLOB '*,,*')),
        updated_at TEXT NOT NULL CONSTRAINT station_path_updated_form CHECK (updated_at GLOB {form}),
        PRIMARY KEY (call, radio_id)
    ) STRICT""")
    db.execute("INSERT INTO station_path (call, radio_id, path, updated_at) SELECT call, 1, path, updated_at FROM station_pref WHERE path IS NOT NULL")
    says = "hide_after_min IS NOT NULL OR attempts IS NOT NULL OR rf_only = 1 OR alert_on_air = 1 OR alert_within_km IS NOT NULL OR alert_direct = 1"
    db.execute("ALTER TABLE station_pref RENAME TO station_pref_old")
    db.execute(f"""CREATE TABLE station_pref (
        call TEXT NOT NULL PRIMARY KEY CONSTRAINT station_pref_call_present CHECK (call <> ''),
        hide_after_min INTEGER CONSTRAINT station_pref_hide_range CHECK (hide_after_min BETWEEN 0 AND 10080), attempts INTEGER CONSTRAINT station_pref_attempts_range CHECK (attempts BETWEEN 1 AND 10),
        rf_only INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_pref_rf_only CHECK (rf_only IN (0, 1)),
        alert_on_air INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_pref_alert_on_air CHECK (alert_on_air IN (0, 1)),
        alert_within_km INTEGER CONSTRAINT station_pref_alert_within_range CHECK (alert_within_km BETWEEN 1 AND 1000),
        alert_direct INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_pref_alert_direct CHECK (alert_direct IN (0, 1)),
        updated_at TEXT NOT NULL CONSTRAINT station_pref_updated_form CHECK (updated_at GLOB {form}),
        CONSTRAINT station_pref_says_something CHECK ({says})
    ) STRICT""")
    columns = "call, hide_after_min, attempts, rf_only, alert_on_air, alert_within_km, alert_direct, updated_at"
    db.execute(f"INSERT INTO station_pref ({columns}) SELECT {columns} FROM station_pref_old WHERE {says}")
    before, with_path, only_path = (int(n) for n in db.execute(f"SELECT COUNT(*), COUNT(path), COALESCE(SUM(NOT ({says})), 0) FROM station_pref_old").fetchone())
    kept = int(db.execute("SELECT COUNT(*) FROM station_pref").fetchone()[0])
    same = int(db.execute("SELECT COUNT(*) FROM station_pref_old o JOIN station_pref n ON n.call = o.call AND n.hide_after_min IS o.hide_after_min AND n.attempts IS o.attempts AND n.rf_only = o.rf_only "
                          "AND n.alert_on_air = o.alert_on_air AND n.alert_within_km IS o.alert_within_km AND n.alert_direct = o.alert_direct AND n.updated_at = o.updated_at").fetchone()[0])
    moved = int(db.execute("SELECT COUNT(*) FROM station_pref_old o JOIN station_path p ON p.call = o.call AND p.radio_id = 1 AND p.path = o.path AND p.updated_at = o.updated_at").fetchone()[0])
    if not (kept == same == before - only_path and moved == with_path):
        raise StoreError(f"station_pref has {before} rows, {with_path} with a path, {only_path} with nothing else: the new one got {kept} of which {same} are the same, and station_path {moved} of the paths; nothing was changed")
    db.execute("DROP TABLE station_pref_old")
    db.execute("ALTER TABLE own_object ADD COLUMN radios TEXT NOT NULL DEFAULT '1' CONSTRAINT own_object_radios CHECK "
               "(radios GLOB '[1-9]*' AND radios NOT GLOB '*[^0-9,]*' AND radios NOT GLOB '*,' AND radios NOT GLOB '*,,*' AND radios NOT GLOB '*,0*')")
    if db.execute("SELECT 1 FROM radio WHERE id = 2").fetchone() is not None:
        db.execute("UPDATE own_object SET radios = CASE radio WHEN 'hf' THEN '2' WHEN 'both' THEN '1,2' ELSE '1' END")
    db.execute("ALTER TABLE own_object DROP COLUMN radio")
    db.execute("DROP TABLE IF EXISTS _m31")
