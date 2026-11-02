"""The migrations from 22 on, frozen here beside migrations.py (which lists them in MIGRATIONS and runs them): the same rules as for the earlier ones (migrationsteps1to11.py, migrationsteps12to21.py), a step is
never edited once it has been released."""
import sqlite3

from .dberror import StoreError
from .migrationlog import log

# The default of `messages/alert_command` up to migration 22, as every save of the settings stored it (on Linux and macOS, and on Windows): it titled every notification "APRS message from", which a station alert is not.
_OLD_LINUX_ALERT = ('(notify-send -- "APRS message from $NEOAPRS_FROM" "$NEOAPRS_TEXT" 2>/dev/null || kdialog --title "APRS message from $NEOAPRS_FROM" --passivepopup "$NEOAPRS_TEXT" 10); '
                    'paplay /usr/share/sounds/freedesktop/stereo/message-new-instant.oga')
_OLD_WINDOWS_ALERT = ("$null=[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime];$null=[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime];"
                      "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);$t=$x.GetElementsByTagName('text');"
                      "$t.Item(0).InnerText='APRS message from '+$env:NEOAPRS_FROM;$t.Item(1).InnerText=$env:NEOAPRS_TEXT;"
                      "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show([Windows.UI.Notifications.ToastNotification]::new($x));"
                      "[System.Media.SystemSounds]::Asterisk.Play()")


def _v22(db: sqlite3.Connection) -> None:
    """The alerts of a station join its path and RF only in `station_pref`: `alert_on_air` (1: tell when it comes on the air after half an hour of silence), `alert_within_km` (1 to 1000: tell when it comes from farther to
    that near us; null: not watched) and `alert_direct` (1: tell when it is heard direct after half an hour without), and a row now says something when any of them is set. CHECKs cannot be changed in place, so the table is
    rebuilt into a new one with every row (no alert), the rows are counted and compared, and any doubt raises: the rollback leaves the old table. The alert command now has a title of its own for each kind of alert
    (NEOAPRS_TITLE): a stored `messages/alert_command` that is exactly the old default of either system, which every save wrote, is deleted, so that the new default counts, with one INFO line in the log; a command of the operator's own is not touched."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    db.execute("ALTER TABLE station_pref RENAME TO station_pref_old")
    db.execute(f"""CREATE TABLE station_pref (
        call TEXT NOT NULL PRIMARY KEY CONSTRAINT station_pref_call_present CHECK (call <> ''),
        path TEXT CONSTRAINT station_pref_path_form CHECK (path = '' OR (path NOT GLOB '*[^A-Z0-9,-]*' AND path NOT GLOB ',*' AND path NOT GLOB '*,' AND path NOT GLOB '*,,*')),
        hide_after_min INTEGER CONSTRAINT station_pref_hide_range CHECK (hide_after_min BETWEEN 0 AND 10080),
        attempts INTEGER CONSTRAINT station_pref_attempts_range CHECK (attempts BETWEEN 1 AND 10),
        rf_only INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_pref_rf_only CHECK (rf_only IN (0, 1)),
        alert_on_air INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_pref_alert_on_air CHECK (alert_on_air IN (0, 1)),
        alert_within_km INTEGER CONSTRAINT station_pref_alert_within_range CHECK (alert_within_km BETWEEN 1 AND 1000),
        alert_direct INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_pref_alert_direct CHECK (alert_direct IN (0, 1)),
        updated_at TEXT NOT NULL CONSTRAINT station_pref_updated_form CHECK (updated_at GLOB {form}),
        CONSTRAINT station_pref_says_something CHECK (path IS NOT NULL OR hide_after_min IS NOT NULL OR attempts IS NOT NULL OR rf_only = 1 OR alert_on_air = 1 OR alert_within_km IS NOT NULL OR alert_direct = 1)
    ) STRICT""")
    db.execute("INSERT INTO station_pref (call, path, hide_after_min, attempts, rf_only, updated_at) SELECT call, path, hide_after_min, attempts, rf_only, updated_at FROM station_pref_old")
    before = int(db.execute("SELECT COUNT(*) FROM station_pref_old").fetchone()[0])
    after = int(db.execute("SELECT COUNT(*) FROM station_pref").fetchone()[0])
    same = int(db.execute("SELECT COUNT(*) FROM station_pref_old o JOIN station_pref n ON n.call = o.call AND n.path IS o.path AND n.hide_after_min IS o.hide_after_min AND n.attempts IS o.attempts "
                          "AND n.rf_only = o.rf_only AND n.alert_on_air = 0 AND n.alert_within_km IS NULL AND n.alert_direct = 0 AND n.updated_at = o.updated_at").fetchone()[0])
    if not before == after == same:
        raise StoreError(f"station_pref has {before} rows, the new one got {after} of which {same} are the same; nothing was changed")
    db.execute("DROP TABLE station_pref_old")
    if db.execute("DELETE FROM settings WHERE key = 'messages/alert_command' AND value IN (?, ?)", (_OLD_LINUX_ALERT, _OLD_WINDOWS_ALERT)).rowcount:
        log.info("messages/alert_command was the old default: the new default, which titles each kind of alert, is in force")


def _v23(db: sqlite3.Connection) -> None:
    """A message never gets the id of one that was deleted: `message.id` is now AUTOINCREMENT, so the next id is above every one the table has held (SQLite kept the highest only while the row was there). The page marks
    what it has shown by id, and a new message with the id of a deleted one was taken for one already read. The delivery chain of a message (`message_attempt`, `message_hop`) is keyed by the id and may hold rows of a
    message that is gone, so the next id is above those too. The table is rebuilt from its own statement (the one migration 10 left, read from the schema) with that one word added, every row keeps its id, the rows
    are counted and compared, the index is made again, and any doubt raises: the rollback leaves the old table."""
    key = "id INTEGER PRIMARY KEY,"
    statement = str(db.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'message'").fetchone()[0])
    if statement.count(key) != 1:
        raise StoreError("the message table is not the one migration 10 made; nothing was changed")
    db.execute("ALTER TABLE message RENAME TO message_old")
    db.execute("DROP INDEX message_calls")
    db.execute(statement.replace(key, "id INTEGER PRIMARY KEY AUTOINCREMENT,"))
    db.execute("INSERT INTO message SELECT * FROM message_old")
    before, after = (int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in ("message_old", "message"))
    lost = int(db.execute("SELECT COUNT(*) FROM (SELECT * FROM message_old EXCEPT SELECT * FROM message)").fetchone()[0])
    if before != after or lost:
        raise StoreError(f"message has {before} rows, the new one got {after} and {lost} differ; nothing was changed")
    db.execute("DROP TABLE message_old")
    db.execute("CREATE INDEX message_calls ON message (to_call, from_call, at)")
    top = int(db.execute("SELECT MAX(COALESCE((SELECT MAX(id) FROM message), 0), COALESCE((SELECT MAX(message_id) FROM message_attempt), 0), COALESCE((SELECT MAX(message_id) FROM message_hop), 0))").fetchone()[0])
    db.execute("DELETE FROM sqlite_sequence WHERE name = 'message'")
    if top:
        db.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('message', ?)", (top,))


def _v24(db: sqlite3.Connection) -> None:
    """Encrypted messages (neoaprs/cipher.py). `station_key` holds the public key each station announced: one row per call, the key as 43 characters of base64 and when it was heard. A message has `seal`, what it
    is: '' plain (every message there is), 'key' an announcement of the sender's key, 'key_other' an announcement that differs from the key kept for the station and was not taken, 'open' encrypted and read,
    'shut' encrypted and not readable here; and `wire`, the text as it went on the air for an encrypted message of ours (the ciphertext; the text is what was written), null for every other."""
    form = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'"
    db.execute(f"""CREATE TABLE station_key (
        call TEXT NOT NULL PRIMARY KEY CONSTRAINT station_key_call_present CHECK (call <> ''),
        pubkey TEXT NOT NULL CONSTRAINT station_key_pubkey_form CHECK (length(pubkey) = 43 AND pubkey NOT GLOB '*[^A-Za-z0-9+/]*'),
        heard_at TEXT NOT NULL CONSTRAINT station_key_heard_form CHECK (heard_at GLOB {form})
    ) STRICT""")
    db.execute("ALTER TABLE message ADD COLUMN seal TEXT NOT NULL DEFAULT '' CONSTRAINT message_seal CHECK (seal IN ('', 'key', 'key_other', 'open', 'shut'))")
    db.execute("ALTER TABLE message ADD COLUMN wire TEXT")


def _v25(db: sqlite3.Connection) -> None:
    """Two radios (neoaprs/radios.py): a packet of the air names the radio it came on, `packet.radio` ('fm' the FM radio, the KISS TNC; 'hf' the HF modem; '' a packet from the internet), and a station keeps how many
    of its packets came on each and when the last did (`heard_fm`, `heard_hf`, `last_fm_at`, `last_hf_at`), which is what chooses the radio a message to it goes out on; a message that came in and an attempt of ours
    name their radio too (`message.radio`, `message_attempt.radio`: the page's chain marks an attempt over HF), and an object of ours the radio it goes out on (`own_object.radio`: fm, hf or both; fm for every one there is). Every packet of the air kept so far came on the one radio there was, the FM one: the rows are
    backfilled so, and a station's FM counts and time are its radio counts and time."""
    db.execute("ALTER TABLE packet ADD COLUMN radio TEXT NOT NULL DEFAULT '' CONSTRAINT packet_radio CHECK (radio IN ('', 'fm', 'hf'))")
    db.execute("UPDATE packet SET radio = 'fm' WHERE via <> 'is'")
    for column in ("heard_fm", "heard_hf"):
        db.execute(f"ALTER TABLE station ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0 CONSTRAINT station_{column}_count CHECK ({column} >= 0)")
    for column in ("last_fm_at", "last_hf_at"):
        db.execute(f"ALTER TABLE station ADD COLUMN {column} TEXT")
    db.execute("UPDATE station SET heard_fm = heard_rf + heard_rf_gated + heard_dummy, last_fm_at = max(coalesce(last_rf_at, ''), coalesce(last_rf_gated_at, ''), coalesce(last_dummy_at, '')) WHERE heard_rf + heard_rf_gated + heard_dummy > 0")
    db.execute("ALTER TABLE message ADD COLUMN radio TEXT NOT NULL DEFAULT '' CONSTRAINT message_radio CHECK (radio IN ('', 'fm', 'hf'))")
    db.execute("ALTER TABLE message_attempt ADD COLUMN radio TEXT NOT NULL DEFAULT '' CONSTRAINT message_attempt_radio CHECK (radio IN ('', 'fm', 'hf'))")
    db.execute("UPDATE message SET radio = 'fm' WHERE direction = 'in'")
    db.execute("UPDATE message_attempt SET radio = 'fm'")
    db.execute("ALTER TABLE own_object ADD COLUMN radio TEXT NOT NULL DEFAULT 'fm' CONSTRAINT own_object_radio CHECK (radio IN ('fm', 'hf', 'both'))")

