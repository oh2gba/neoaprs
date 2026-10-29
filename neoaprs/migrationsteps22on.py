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
