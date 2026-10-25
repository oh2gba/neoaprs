"""The migrations of the one database file and its opening: the file is versioned (SQLite's user_version) and brought up to date by the steps below, one after the other; a file from
a newer NeoAPRS than this one is refused, not damaged. Before the first migration step that is going to run on a file that holds anything, the file is copied whole into backup/ next to it
(premigrate-v<from>-to-v<to>-<time>.sqlite, a name nothing removes); if that copy cannot be made, nothing is migrated. Every step that ran is written to the table
schema_history (version, name, a checksum of the function's source, the time). A migration that has been applied is never edited: a change is a new migration (the checksum of the
source of each step is pinned by tests/test_migrations.py; the steps keep the names and the annotations they were written with, which is why they name sqlite3 and not dberror.py's aliases).

This is run on the thread that calls it, before the database thread (db.py) opens the file for good, and by the tools that own a connection of their own; the statements of the daemon
are not made through it. The settings and the other rows are store.py's, through the database thread."""
import hashlib
import inspect
import logging
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .backupfolder import sweep
from .clock import Clock, from_unix, to_unix, utcnow
from .dberror import StoreError
from .dbfile import DEFAULT_BUSY_MS, configure, copy_database as _copy_database
from .migrations2 import MIGRATION_LOG, _v12, _v13, _v14, _v15, _v16, _v17, _v18, _v19

log = logging.getLogger(MIGRATION_LOG)                    # the migrations' lines are on stderr too (daemon.py), because they change what the operator has stored


def _v1(db: sqlite3.Connection) -> None:
    """The settings, one row per key ("station/call"), a revision per row counted up by every write; and schema_history, what was applied and when (the checksum is of the source of the function that ran)."""
    db.execute("""CREATE TABLE settings (
        key TEXT PRIMARY KEY CONSTRAINT settings_key_present CHECK (key <> ''),
        value TEXT NOT NULL,
        rev INTEGER NOT NULL DEFAULT 1 CONSTRAINT settings_rev_positive CHECK (rev >= 1)
    ) STRICT""")
    db.execute("""CREATE TABLE schema_history (version INTEGER PRIMARY KEY, name TEXT NOT NULL, sha256 TEXT NOT NULL, applied INTEGER NOT NULL,
        note TEXT NOT NULL DEFAULT '') STRICT""")


def _v2(db: sqlite3.Connection) -> None:
    """The heard and sent packets, and the stations the packets make known. `packet` is the log (the frame as it came, what the parser made of it as JSON); `station` is a cache of the
    station book that the daemon rebuilds from the packets and may be dropped by a later migration without loss. A time is text in one fixed form that sorts as time does."""
    db.execute("""CREATE TABLE packet (
        id INTEGER PRIMARY KEY,
        heard_at TEXT NOT NULL CONSTRAINT packet_heard_at_form CHECK (heard_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'),
        direction TEXT NOT NULL CONSTRAINT packet_direction CHECK (direction IN ('in', 'out')),
        raw BLOB NOT NULL,
        source TEXT NOT NULL CONSTRAINT packet_source_present CHECK (source <> ''),
        destination TEXT NOT NULL,
        path TEXT NOT NULL,
        kind TEXT NOT NULL CONSTRAINT packet_kind CHECK (kind IN ('position', 'message', 'object', 'item', 'status', 'other', 'undecoded')),
        summary TEXT NOT NULL,
        decoded TEXT NOT NULL CONSTRAINT packet_decoded_json CHECK (json_valid(decoded)),
        error TEXT,
        CONSTRAINT packet_error_when_undecoded CHECK ((kind = 'undecoded') = (error IS NOT NULL))
    ) STRICT""")
    db.execute("CREATE INDEX packet_heard_at ON packet (heard_at)")
    db.execute("CREATE INDEX packet_source ON packet (source)")
    db.execute("""CREATE TABLE station (
        call TEXT NOT NULL PRIMARY KEY CONSTRAINT station_call_present CHECK (call <> ''),
        kind TEXT NOT NULL CONSTRAINT station_kind CHECK (kind IN ('station', 'object', 'item')),
        reported_by TEXT NOT NULL,
        symbol_table TEXT NOT NULL,
        symbol_code TEXT NOT NULL,
        lat REAL CONSTRAINT station_lat_range CHECK (lat BETWEEN -90 AND 90),
        lon REAL CONSTRAINT station_lon_range CHECK (lon BETWEEN -180 AND 180),
        altitude_m REAL,
        course_deg INTEGER,
        speed_kmh REAL,
        first_heard TEXT NOT NULL,
        last_heard TEXT NOT NULL,
        last_position_at TEXT,
        last_status TEXT NOT NULL,
        last_comment TEXT NOT NULL,
        packets INTEGER NOT NULL CONSTRAINT station_packets_count CHECK (packets >= 0),
        last_path TEXT NOT NULL,
        CONSTRAINT station_position_together CHECK ((lat IS NULL) = (lon IS NULL))
    ) STRICT""")


def _v3(db: sqlite3.Connection) -> None:
    """The messages: those we sent, with the state of their delivery and the attempts made, those that were sent to us and those we only overheard (`overheard`: to another station). A time is text in
    the form of the packet table's; `msg_id` is the APRS message id (1 to 5 letters or digits) and is null for a message that has none; a message came in if and only if it is `received` or `overheard`.
    And the path of each station we write to: operator data kept apart from the station cache, `path` being digipeater calls separated by commas, empty for a direct path."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    db.execute(f"""CREATE TABLE message (
        id INTEGER PRIMARY KEY,
        at TEXT NOT NULL CONSTRAINT message_at_form CHECK (at GLOB {form}),
        direction TEXT NOT NULL CONSTRAINT message_direction CHECK (direction IN ('in', 'out')),
        from_call TEXT NOT NULL CONSTRAINT message_from_present CHECK (from_call <> ''),
        to_call TEXT NOT NULL CONSTRAINT message_to_present CHECK (to_call <> ''),
        text TEXT NOT NULL,
        msg_id TEXT CONSTRAINT message_msg_id_form CHECK (msg_id IS NULL OR (length(msg_id) BETWEEN 1 AND 5 AND msg_id NOT GLOB '*[^A-Za-z0-9]*')),
        state TEXT NOT NULL CONSTRAINT message_state CHECK (state IN ('sending', 'acked', 'rejected', 'failed', 'cancelled', 'received', 'overheard')),
        attempts INTEGER NOT NULL DEFAULT 0 CONSTRAINT message_attempts_count CHECK (attempts >= 0),
        last_attempt_at TEXT CONSTRAINT message_last_attempt_form CHECK (last_attempt_at GLOB {form}),
        acked_at TEXT CONSTRAINT message_acked_at_form CHECK (acked_at GLOB {form}),
        CONSTRAINT message_in_when_heard CHECK ((direction = 'in') = (state IN ('received', 'overheard')))
    ) STRICT""")
    db.execute("CREATE INDEX message_calls ON message (to_call, from_call, at)")
    db.execute(f"""CREATE TABLE station_path (
        call TEXT NOT NULL PRIMARY KEY CONSTRAINT station_path_call_present CHECK (call <> ''),
        path TEXT NOT NULL CONSTRAINT station_path_form CHECK (path = '' OR (path NOT GLOB '*[^A-Z0-9,-]*' AND path NOT GLOB ',*' AND path NOT GLOB '*,' AND path NOT GLOB '*,,*')),
        updated_at TEXT NOT NULL CONSTRAINT station_path_updated_form CHECK (updated_at GLOB {form})
    ) STRICT""")


def _v4(db: sqlite3.Connection) -> None:
    """What the operator says about a station, apart from what the packets say: `station_path` becomes `station_pref`. A station may have a path (digipeater calls separated by commas, empty for a direct path,
    null for none set: the beacon's path), a timeout (`hide_after_min`: minutes after its last position that it leaves the map, 0 for never, null for the setting `map/hide_after_min`), or both; a row with
    neither is not kept. The old table is rebuilt into the new one with every row (the new CHECKs are the old ones relaxed, so nothing needs repairing), the rows are counted and compared, and any doubt
    raises: the rollback leaves the old table."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    db.execute(f"""CREATE TABLE station_pref (
        call TEXT NOT NULL PRIMARY KEY CONSTRAINT station_pref_call_present CHECK (call <> ''),
        path TEXT CONSTRAINT station_pref_path_form CHECK (path = '' OR (path NOT GLOB '*[^A-Z0-9,-]*' AND path NOT GLOB ',*' AND path NOT GLOB '*,' AND path NOT GLOB '*,,*')),
        hide_after_min INTEGER CONSTRAINT station_pref_hide_range CHECK (hide_after_min BETWEEN 0 AND 10080),
        updated_at TEXT NOT NULL CONSTRAINT station_pref_updated_form CHECK (updated_at GLOB {form}),
        CONSTRAINT station_pref_says_something CHECK (path IS NOT NULL OR hide_after_min IS NOT NULL)
    ) STRICT""")
    db.execute("INSERT INTO station_pref (call, path, updated_at) SELECT call, path, updated_at FROM station_path")
    before = int(db.execute("SELECT COUNT(*) FROM station_path").fetchone()[0])
    after = int(db.execute("SELECT COUNT(*) FROM station_pref").fetchone()[0])
    same = int(db.execute("SELECT COUNT(*) FROM station_path o JOIN station_pref n ON n.call = o.call AND n.path = o.path AND n.updated_at = o.updated_at").fetchone()[0])
    if not before == after == same:
        raise StoreError(f"station_path has {before} rows, station_pref got {after} of which {same} are the same; nothing was changed")
    db.execute("DROP TABLE station_path")


def _v5(db: sqlite3.Connection) -> None:
    """How many attempts a message was given when it was sent (the setting `messages/attempts`, 1 to 10): a column on the message table, 6 for every message there already is (the number every message had until now)."""
    db.execute("ALTER TABLE message ADD COLUMN attempts_max INTEGER NOT NULL DEFAULT 6 CONSTRAINT message_attempts_max_range CHECK (attempts_max BETWEEN 1 AND 10)")


def _v6(db: sqlite3.Connection) -> None:
    """How a message that was heard reached us (`route`: "direct", "via OH2RCH-2", "via OH2RCH-1 → OH2RCH-3"), worked out from the packet when it was heard and kept so that the thread can show it without the packet: a column on the
    message table, empty for every message there already is and for every message of ours."""
    db.execute("ALTER TABLE message ADD COLUMN route TEXT NOT NULL DEFAULT ''")


def _v7(db: sqlite3.Connection) -> None:
    """The message board: the bulletins, announcements, group bulletins and group messages (to ALL, CQ and QST) that were heard, one row for each sender and slot (the addressee: `BLN1`, `BLNA`,
    `BLN3HAMS`, `QST`). A sender that sends the slot again replaces the text; `group_name` is the group of a group bulletin and empty for any other, `times_heard` counts the hearings of the text
    and starts again at 1 when it changes. A time is text in the form of the packet table's. Rows are forgotten when they age (hours without a repeat), so the table holds the board of the moment."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    db.execute(f"""CREATE TABLE bulletin (
        sender TEXT NOT NULL CONSTRAINT bulletin_sender_present CHECK (sender <> ''),
        slot TEXT NOT NULL CONSTRAINT bulletin_slot_present CHECK (slot <> ''),
        group_name TEXT NOT NULL,
        text TEXT NOT NULL,
        first_heard TEXT NOT NULL CONSTRAINT bulletin_first_heard_form CHECK (first_heard GLOB {form}),
        last_heard TEXT NOT NULL CONSTRAINT bulletin_last_heard_form CHECK (last_heard GLOB {form}),
        times_heard INTEGER NOT NULL DEFAULT 1 CONSTRAINT bulletin_times_heard_count CHECK (times_heard >= 1),
        PRIMARY KEY (sender, slot),
        CONSTRAINT bulletin_heard_in_order CHECK (last_heard >= first_heard)
    ) STRICT""")
    db.execute("CREATE INDEX bulletin_last_heard ON bulletin (last_heard)")


def _v8(db: sqlite3.Connection) -> None:
    """The weather: every observation of a weather station, for the trend graphs. One row for each weather packet heard (a position with the weather symbol, a positionless weather report, an object that is
    a weather station): the station's call or object name, the time it was heard, the values in metric units (wind in km/h and the degrees it blows from, temperature in degrees C, humidity in per cent,
    pressure in hPa, rain in mm in the last hour, 24 hours and since midnight, luminosity in W/m2), each null where the report did not have it, and `raw`, the fields as they were sent. The ranges are those
    the fields can have (three digits of mph, three characters of degrees F, five digits of tenths of hPa). A time is text in the form of the packet table's; the index serves a station's series."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    db.execute(f"""CREATE TABLE weather (
        station TEXT NOT NULL CONSTRAINT weather_station_present CHECK (station <> ''),
        at TEXT NOT NULL CONSTRAINT weather_at_form CHECK (at GLOB {form}),
        wind_dir INTEGER CONSTRAINT weather_wind_dir_range CHECK (wind_dir BETWEEN 0 AND 360),
        wind_kmh REAL CONSTRAINT weather_wind_kmh_range CHECK (wind_kmh BETWEEN 0 AND 1610),
        gust_kmh REAL CONSTRAINT weather_gust_kmh_range CHECK (gust_kmh BETWEEN 0 AND 1610),
        temp_c REAL CONSTRAINT weather_temp_c_range CHECK (temp_c BETWEEN -73 AND 538),
        humidity INTEGER CONSTRAINT weather_humidity_range CHECK (humidity BETWEEN 1 AND 100),
        pressure_hpa REAL CONSTRAINT weather_pressure_hpa_range CHECK (pressure_hpa BETWEEN 0 AND 10000),
        rain_1h_mm REAL CONSTRAINT weather_rain_1h_mm_range CHECK (rain_1h_mm BETWEEN 0 AND 254),
        rain_24h_mm REAL CONSTRAINT weather_rain_24h_mm_range CHECK (rain_24h_mm BETWEEN 0 AND 254),
        rain_today_mm REAL CONSTRAINT weather_rain_today_mm_range CHECK (rain_today_mm BETWEEN 0 AND 254),
        luminosity INTEGER CONSTRAINT weather_luminosity_range CHECK (luminosity BETWEEN 0 AND 1999),
        raw TEXT NOT NULL
    ) STRICT""")
    db.execute("CREATE INDEX weather_station_at ON weather (station, at)")


def _v9(db: sqlite3.Connection) -> None:
    """The attempts a message to a station is given (`attempts`: 1 to 10, null for none set: the setting `messages/attempts`) join the path and the timeout in `station_pref`; a row now says something when any of the three is
    set. CHECKs cannot be changed in place, so the table is rebuilt into a new one with every row (the new CHECKs are the old ones relaxed, so nothing needs repairing), the rows are counted and compared, and any doubt raises:
    the rollback leaves the old table."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    db.execute("ALTER TABLE station_pref RENAME TO station_pref_old")
    db.execute(f"""CREATE TABLE station_pref (
        call TEXT NOT NULL PRIMARY KEY CONSTRAINT station_pref_call_present CHECK (call <> ''),
        path TEXT CONSTRAINT station_pref_path_form CHECK (path = '' OR (path NOT GLOB '*[^A-Z0-9,-]*' AND path NOT GLOB ',*' AND path NOT GLOB '*,' AND path NOT GLOB '*,,*')),
        hide_after_min INTEGER CONSTRAINT station_pref_hide_range CHECK (hide_after_min BETWEEN 0 AND 10080),
        attempts INTEGER CONSTRAINT station_pref_attempts_range CHECK (attempts BETWEEN 1 AND 10),
        updated_at TEXT NOT NULL CONSTRAINT station_pref_updated_form CHECK (updated_at GLOB {form}),
        CONSTRAINT station_pref_says_something CHECK (path IS NOT NULL OR hide_after_min IS NOT NULL OR attempts IS NOT NULL)
    ) STRICT""")
    db.execute("INSERT INTO station_pref (call, path, hide_after_min, updated_at) SELECT call, path, hide_after_min, updated_at FROM station_pref_old")
    before = int(db.execute("SELECT COUNT(*) FROM station_pref_old").fetchone()[0])
    after = int(db.execute("SELECT COUNT(*) FROM station_pref").fetchone()[0])
    same = int(db.execute("SELECT COUNT(*) FROM station_pref_old o JOIN station_pref n ON n.call = o.call AND n.path IS o.path AND n.hide_after_min IS o.hide_after_min AND n.updated_at = o.updated_at").fetchone()[0])
    if not before == after == same:
        raise StoreError(f"station_pref has {before} rows, the new one got {after} of which {same} are the same; nothing was changed")
    db.execute("DROP TABLE station_pref_old")


def _v10(db: sqlite3.Connection) -> None:
    """A message that was given one or two attempts and got no ack is not a failure: the state `unconfirmed` joins the others in the CHECK of the message table. A CHECK cannot be changed in place, so the table is
    rebuilt with the columns in the order they have (those of migration 3, `attempts_max` and `route`), every row is copied, the rows are counted and compared, the index is made again, and any doubt raises:
    the rollback leaves the old table."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    columns = "id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route"
    db.execute("ALTER TABLE message RENAME TO message_old")
    db.execute("DROP INDEX message_calls")
    db.execute(f"""CREATE TABLE message (
        id INTEGER PRIMARY KEY,
        at TEXT NOT NULL CONSTRAINT message_at_form CHECK (at GLOB {form}),
        direction TEXT NOT NULL CONSTRAINT message_direction CHECK (direction IN ('in', 'out')),
        from_call TEXT NOT NULL CONSTRAINT message_from_present CHECK (from_call <> ''),
        to_call TEXT NOT NULL CONSTRAINT message_to_present CHECK (to_call <> ''),
        text TEXT NOT NULL,
        msg_id TEXT CONSTRAINT message_msg_id_form CHECK (msg_id IS NULL OR (length(msg_id) BETWEEN 1 AND 5 AND msg_id NOT GLOB '*[^A-Za-z0-9]*')),
        state TEXT NOT NULL CONSTRAINT message_state CHECK (state IN ('sending', 'acked', 'rejected', 'failed', 'unconfirmed', 'cancelled', 'received', 'overheard')),
        attempts INTEGER NOT NULL DEFAULT 0 CONSTRAINT message_attempts_count CHECK (attempts >= 0),
        last_attempt_at TEXT CONSTRAINT message_last_attempt_form CHECK (last_attempt_at GLOB {form}),
        acked_at TEXT CONSTRAINT message_acked_at_form CHECK (acked_at GLOB {form}),
        attempts_max INTEGER NOT NULL DEFAULT 6 CONSTRAINT message_attempts_max_range CHECK (attempts_max BETWEEN 1 AND 10),
        route TEXT NOT NULL DEFAULT '',
        CONSTRAINT message_in_when_heard CHECK ((direction = 'in') = (state IN ('received', 'overheard')))
    ) STRICT""")
    db.execute(f"INSERT INTO message ({columns}) SELECT {columns} FROM message_old")
    before = int(db.execute("SELECT COUNT(*) FROM message_old").fetchone()[0])
    after = int(db.execute("SELECT COUNT(*) FROM message").fetchone()[0])
    same = int(db.execute("SELECT COUNT(*) FROM message_old o JOIN message n ON n.id = o.id AND n.at = o.at AND n.direction = o.direction AND n.from_call = o.from_call AND n.to_call = o.to_call "
                          "AND n.text = o.text AND n.msg_id IS o.msg_id AND n.state = o.state AND n.attempts = o.attempts AND n.last_attempt_at IS o.last_attempt_at AND n.acked_at IS o.acked_at "
                          "AND n.attempts_max = o.attempts_max AND n.route = o.route").fetchone()[0])
    if not before == after == same:
        raise StoreError(f"message has {before} rows, the new one got {after} of which {same} are the same; nothing was changed")
    db.execute("DROP TABLE message_old")
    db.execute("CREATE INDEX message_calls ON message (to_call, from_call, at)")


def _v11(db: sqlite3.Connection) -> None:
    """The delivery chain of the messages we sent. `message_attempt`: each transmission of a message (`attempt` counts from 1), when it was sent and the digipeaters it went by (`path`, calls separated by commas,
    empty for direct). `message_hop`: for an attempt, which hop of that path a copy of our own message was heard back with (`position` from 1; the call that did it, which is the one heard when the path had an
    alias), when, and whether it was a third-party copy gated back over the internet; position 0 is such a copy whose own path names no hop, `call` the iGate's. Both go with the message (the statements that
    delete a message delete these rows in the same transaction). A time is text in the form of the packet table's."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    db.execute(f"""CREATE TABLE message_attempt (
        message_id INTEGER NOT NULL,
        attempt INTEGER NOT NULL CONSTRAINT message_attempt_number CHECK (attempt >= 1),
        sent_at TEXT NOT NULL CONSTRAINT message_attempt_sent_form CHECK (sent_at GLOB {form}),
        path TEXT NOT NULL CONSTRAINT message_attempt_path_form CHECK (path = '' OR (path NOT GLOB '*[^A-Z0-9,-]*' AND path NOT GLOB ',*' AND path NOT GLOB '*,' AND path NOT GLOB '*,,*')),
        PRIMARY KEY (message_id, attempt)
    ) STRICT""")
    db.execute(f"""CREATE TABLE message_hop (
        message_id INTEGER NOT NULL,
        attempt INTEGER NOT NULL CONSTRAINT message_hop_attempt_number CHECK (attempt >= 1),
        position INTEGER NOT NULL CONSTRAINT message_hop_position_range CHECK (position BETWEEN 0 AND 8),
        call TEXT NOT NULL CONSTRAINT message_hop_call_present CHECK (call <> ''),
        heard_at TEXT NOT NULL CONSTRAINT message_hop_heard_form CHECK (heard_at GLOB {form}),
        via_internet INTEGER NOT NULL CONSTRAINT message_hop_via_internet CHECK (via_internet IN (0, 1)),
        PRIMARY KEY (message_id, attempt, position, via_internet),
        CONSTRAINT message_hop_gate_is_internet CHECK (position > 0 OR via_internet = 1)
    ) STRICT""")
    db.execute("CREATE INDEX message_hop_message ON message_hop (message_id)")


def source_hash(step: Callable[[sqlite3.Connection], None]) -> str:
    """sha256 of the source text of a migration function; "unknown" when the source is not to be had (compiled only)."""
    try:
        return hashlib.sha256(inspect.getsource(step).encode("utf-8")).hexdigest()
    except (OSError, TypeError):
        return "unknown"


# one function per version, in order: version N is reached by running MIGRATIONS[N - 1] on version N - 1
MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_v1, _v2, _v3, _v4, _v5, _v6, _v7, _v8, _v9, _v10, _v11, _v12, _v13, _v14, _v15, _v16, _v17, _v18, _v19]
SCHEMA_VERSION = len(MIGRATIONS)


def schema_version(db: sqlite3.Connection) -> int:
    return int(db.execute("PRAGMA user_version").fetchone()[0])


def open_database(path: str | Path, busy_ms: int = DEFAULT_BUSY_MS, clock: Clock = utcnow) -> tuple[sqlite3.Connection | None, str]:
    """The connection to the database file, brought up to date, and "" -- or None and the reason when the file cannot be opened or is of a newer version. ":memory:" for tests.
    `busy_ms`: how long a write waits for another writer; the daemon asks for a few seconds (it must not stand still), the tools for longer. This runs on the thread that calls
    it, before the database thread (db.py) opens the file for good, and in the tools; it is the migrations' own, the daemon's statements are not made through it.

    When a migration is going to run on a file that holds anything, the file is copied whole first (see `premigration_backup`); if the copy cannot be made, nothing is migrated and
    the file is as it was."""
    db: sqlite3.Connection | None = None
    try:
        db = sqlite3.connect(str(path), isolation_level=None, timeout=busy_ms / 1000.0)         # the transactions are ours: BEGIN and COMMIT where a write needs more than one statement
        version = schema_version(db)                        # first: nothing of a file is changed before it is known to be ours

        if version > SCHEMA_VERSION:
            db.close()
            return None, f"{path} is of version {version}, made by a newer NeoAPRS than this one (it knows {SCHEMA_VERSION}); not touched"

        configure(db, path, busy_ms)                        # WAL, synchronous=FULL, the busy time, the bound of the log, the file private (dbfile.py)

        if version < SCHEMA_VERSION and str(path) != ":memory:" and db.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is not None:
            copy = premigration_backup(db, Path(path), version, clock)
            log.info("the database %s is of version %d, this NeoAPRS needs %d: a copy of it is in %s", path, version, SCHEMA_VERSION, copy)

        for number in range(version + 1, SCHEMA_VERSION + 1):
            if _step(db, number, clock) and version:
                log.info("the database %s is now version %d (was %d)", path, number, number - 1)
        for problem in _history_problems(db):
            log.warning("%s: %s", path, problem)
    except sqlite3.Error as e:
        return _refused(db, str(e))
    except (OSError, StoreError) as e:
        log.error("the database %s was not migrated: %s", path, e)
        return _refused(db, f"the database {path} was not migrated, and is as it was: {e}")
    except Exception as e:
        # whatever else a step raises (a corrupt row ...) is a refusal with a reason, and the daemon ends with 2 (the unit does not restart that). A raw exception
        # out of here would end it with 1, which the unit restarts every five seconds, and each start would make another full copy of the file
        log.error("the database %s was not migrated: %s: %s", path, type(e).__name__, e)
        return _refused(db, f"the database {path} was not migrated: {type(e).__name__}: {e} (the step that failed is rolled back; the copy taken before it is in backup/)")

    if str(path) != ":memory:":
        sweep(Path(path).absolute().parent / "backup", clock().timestamp())      # the temporary files of a copy that a kill ended before this start
    return db, ""


def _refused(db: sqlite3.Connection | None, why: str) -> tuple[None, str]:
    """The file is not ours to use: the connection is closed and the reason is the answer of open_database()."""
    if db is not None:
        db.close()
    return None, why


def _step(db: sqlite3.Connection, number: int, clock: Clock) -> bool:
    """Migration `number` in a transaction of its own, with its row in the history: all of it or none. False when another process (the daemon, neoaprs-db) got there first."""
    db.execute("BEGIN IMMEDIATE")
    try:
        if schema_version(db) >= number:
            db.execute("ROLLBACK")
            return False
        MIGRATIONS[number - 1](db)
        db.execute(f"PRAGMA user_version = {number}")
        _record_step(db, number, clock)
        db.execute("COMMIT")
    except Exception:
        try:
            db.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    return True


def premigration_backup(db: sqlite3.Connection, path: Path, version: int, clock: Clock) -> Path:
    """The file as it is, whole, in backup/ next to it: premigrate-v<from>-to-v<to>-<time>.sqlite. Nothing removes it:
    it stays until somebody removes it. Raises StoreError when it cannot be made, and the caller migrates nothing."""
    folder = path.absolute().parent / "backup"
    stem = f"premigrate-v{version}-to-v{SCHEMA_VERSION}-{clock():%Y%m%d-%H%M%S}"
    dest = folder / f"{stem}.sqlite"
    n = 1
    while dest.exists():
        n += 1
        dest = folder / f"{stem}-{n}.sqlite"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _copy_database(db, dest)
    except (sqlite3.Error, OSError) as e:
        raise StoreError(f"the copy of the database before the migration could not be made ({e}); nothing was changed") from e
    return dest


def _record_step(db: sqlite3.Connection, number: int, clock: Clock) -> None:
    """The step that has just run, into schema_history (the first step makes the table, so every step has its row)."""
    step = MIGRATIONS[number - 1]
    db.execute("INSERT INTO schema_history (version, name, sha256, applied) VALUES (?, ?, ?, ?)", (number, step.__name__, source_hash(step), to_unix(clock())))


def history(db: sqlite3.Connection) -> list[tuple[int, str, str, datetime, str]]:
    """(version, name, sha256, applied, note) of every migration step that was applied, oldest first; empty for a file that predates the table."""
    try:
        return [(int(v), str(n), str(h), from_unix(int(t)), str(note)) for v, n, h, t, note
                in db.execute("SELECT version, name, sha256, applied, note FROM schema_history ORDER BY version")]
    except sqlite3.Error:
        return []


def _history_problems(db: sqlite3.Connection) -> list[str]:
    """What schema_history says that is not so: a step whose source is not what it was when it ran (an applied migration was edited), or a step
    the file recorded that this NeoAPRS does not have."""
    try:
        rows = db.execute("SELECT version, sha256 FROM schema_history ORDER BY version").fetchall()
    except sqlite3.Error:
        return []
    out: list[str] = []
    for version, digest in rows:
        if not 1 <= version <= len(MIGRATIONS):
            out.append(f"schema_history has a step {version} that this NeoAPRS does not know")
        elif digest != "unknown" and source_hash(MIGRATIONS[version - 1]) not in (digest, "unknown"):
            out.append(f"migration {version} ({MIGRATIONS[version - 1].__name__}) is not the code that was applied: its source has changed since")
    return out
