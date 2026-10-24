"""The migrations from the twelfth on, frozen here beside neoaprs/migrations.py (which lists them in MIGRATIONS and runs them): the same rules, a step is never edited once it has been released."""
import sqlite3

from .dberror import StoreError


def _v12(db: sqlite3.Connection) -> None:
    """`rf_only` joins the path, the timeout and the attempts in `station_pref`: 1 when everything sent to the station goes with RFONLY at the end of its path (0 for not), and a row now says something when any of
    the four is set. CHECKs cannot be changed in place, so the table is rebuilt into a new one with every row (rf_only 0), the rows are counted and compared, and any doubt raises: the rollback leaves the old table."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    db.execute("ALTER TABLE station_pref RENAME TO station_pref_old")
    db.execute(f"""CREATE TABLE station_pref (
        call TEXT NOT NULL PRIMARY KEY CONSTRAINT station_pref_call_present CHECK (call <> ''),
        path TEXT CONSTRAINT station_pref_path_form CHECK (path = '' OR (path NOT GLOB '*[^A-Z0-9,-]*' AND path NOT GLOB ',*' AND path NOT GLOB '*,' AND path NOT GLOB '*,,*')),
        hide_after_min INTEGER CONSTRAINT station_pref_hide_range CHECK (hide_after_min BETWEEN 0 AND 10080),
        attempts INTEGER CONSTRAINT station_pref_attempts_range CHECK (attempts BETWEEN 1 AND 10),
        rf_only INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_pref_rf_only CHECK (rf_only IN (0, 1)),
        updated_at TEXT NOT NULL CONSTRAINT station_pref_updated_form CHECK (updated_at GLOB {form}),
        CONSTRAINT station_pref_says_something CHECK (path IS NOT NULL OR hide_after_min IS NOT NULL OR attempts IS NOT NULL OR rf_only = 1)
    ) STRICT""")
    db.execute("INSERT INTO station_pref (call, path, hide_after_min, attempts, updated_at) SELECT call, path, hide_after_min, attempts, updated_at FROM station_pref_old")
    before = int(db.execute("SELECT COUNT(*) FROM station_pref_old").fetchone()[0])
    after = int(db.execute("SELECT COUNT(*) FROM station_pref").fetchone()[0])
    same = int(db.execute("SELECT COUNT(*) FROM station_pref_old o JOIN station_pref n ON n.call = o.call AND n.path IS o.path AND n.hide_after_min IS o.hide_after_min AND n.attempts IS o.attempts "
                          "AND n.rf_only = 0 AND n.updated_at = o.updated_at").fetchone()[0])
    if not before == after == same:
        raise StoreError(f"station_pref has {before} rows, the new one got {after} of which {same} are the same; nothing was changed")
    db.execute("DROP TABLE station_pref_old")


def _v13(db: sqlite3.Connection) -> None:
    """The objects, items and bulletins of our own, which the daemon sends on a schedule of their own. `own_object`: one row for each name (the name of an object, 1 to 9 characters, or of an item, 3 to 9), its
    position, symbol, comment, the course and speed, the path it goes by (NULL: the beacon's), whether it is alive or being killed, when it was made and last changed, how often it was sent since
    then and when last. `own_bulletin`: one row for each slot (`BLN1`, `BLNA`, `BLN3HAMS`) with its text, the group of a group bulletin, when it was first posted, how often it was sent and when it was first and
    last sent. Times are text in the form of the packet table's."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    db.execute(f"""CREATE TABLE own_object (
        name TEXT NOT NULL PRIMARY KEY CONSTRAINT own_object_name_length CHECK (length(name) BETWEEN 1 AND 9),
        kind TEXT NOT NULL CONSTRAINT own_object_kind CHECK (kind IN ('object', 'item')),
        lat REAL NOT NULL CONSTRAINT own_object_lat_range CHECK (lat BETWEEN -90 AND 90),
        lon REAL NOT NULL CONSTRAINT own_object_lon_range CHECK (lon BETWEEN -180 AND 180),
        symbol_table TEXT NOT NULL CONSTRAINT own_object_table_one CHECK (length(symbol_table) = 1),
        symbol_code TEXT NOT NULL CONSTRAINT own_object_code_one CHECK (length(symbol_code) = 1),
        comment TEXT NOT NULL CONSTRAINT own_object_comment_length CHECK (length(comment) <= 43),
        course_deg INTEGER CONSTRAINT own_object_course_range CHECK (course_deg BETWEEN 0 AND 359),
        speed_kmh REAL CONSTRAINT own_object_speed_range CHECK (speed_kmh BETWEEN 0 AND 1850),
        path TEXT CONSTRAINT own_object_path_form CHECK (path IS NULL OR (path <> '' AND path NOT GLOB '*[^A-Z0-9,-]*' AND path NOT GLOB ',*' AND path NOT GLOB '*,' AND path NOT GLOB '*,,*')),
        alive INTEGER NOT NULL CONSTRAINT own_object_alive CHECK (alive IN (0, 1)),
        created_at TEXT NOT NULL CONSTRAINT own_object_created_form CHECK (created_at GLOB {form}),
        updated_at TEXT NOT NULL CONSTRAINT own_object_updated_form CHECK (updated_at GLOB {form}),
        sent INTEGER NOT NULL DEFAULT 0 CONSTRAINT own_object_sent_count CHECK (sent >= 0),
        last_sent_at TEXT CONSTRAINT own_object_last_sent_form CHECK (last_sent_at GLOB {form}),
        CONSTRAINT own_object_item_name CHECK (kind = 'object' OR length(name) >= 3),
        CONSTRAINT own_object_sent_has_time CHECK (sent = 0 OR last_sent_at IS NOT NULL)
    ) STRICT""")
    db.execute(f"""CREATE TABLE own_bulletin (
        slot TEXT NOT NULL PRIMARY KEY CONSTRAINT own_bulletin_slot_form CHECK (slot GLOB 'BLN[0-9A-Z]*' AND length(slot) BETWEEN 4 AND 9 AND slot NOT GLOB '*[^A-Z0-9-]*'),
        group_name TEXT NOT NULL,
        text TEXT NOT NULL CONSTRAINT own_bulletin_text_length CHECK (length(text) BETWEEN 1 AND 67),
        created_at TEXT NOT NULL CONSTRAINT own_bulletin_created_form CHECK (created_at GLOB {form}),
        sent INTEGER NOT NULL DEFAULT 0 CONSTRAINT own_bulletin_sent_count CHECK (sent >= 0),
        first_sent_at TEXT CONSTRAINT own_bulletin_first_sent_form CHECK (first_sent_at GLOB {form}),
        last_sent_at TEXT CONSTRAINT own_bulletin_last_sent_form CHECK (last_sent_at GLOB {form}),
        CONSTRAINT own_bulletin_sent_has_times CHECK (sent = 0 OR (first_sent_at IS NOT NULL AND last_sent_at IS NOT NULL)),
        CONSTRAINT own_bulletin_sent_in_order CHECK (first_sent_at IS NULL OR last_sent_at IS NULL OR last_sent_at >= first_sent_at)
    ) STRICT""")


def _v14(db: sqlite3.Connection) -> None:
    """The path settings: an empty `beacon/path` now means the recommended path (WIDE1-1,WIDE2-1) and `DIRECT` means no digipeaters at all. A stored empty path was cleared on purpose and meant none, so it becomes
    DIRECT: nobody starts to digipeat on an upgrade. Any other stored value is as it was (WIDE1-1,WIDE2-1 is the recommended path, the rest is a custom one)."""
    db.execute("UPDATE settings SET value = 'DIRECT', rev = rev + 1 WHERE key = 'beacon/path' AND trim(value) = ''")
