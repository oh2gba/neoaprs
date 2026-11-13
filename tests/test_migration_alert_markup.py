"""Migration 27 (neoaprs/migrationsteps22on.py): the default alert command of Linux and macOS escapes & < > for the notifier. A stored `messages/alert_command` that is exactly the default of migration 22 is deleted, so
that the new default (`neoaprs.alertcommand.LINUX_ALERT_COMMAND`) is in force, with one line in the log; a command of the operator's own, the default of Windows and a database without the row are left alone."""
import logging
from pathlib import Path

import pytest

from neoaprs.alertcommand import LINUX_ALERT_COMMAND, WINDOWS_ALERT_COMMAND
from neoaprs.config import DEFAULTS, Config
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, raw

V22_LINUX_ALERT = ('(notify-send -- "$NEOAPRS_TITLE" "$NEOAPRS_TEXT" 2>/dev/null || kdialog --title "$NEOAPRS_TITLE" --passivepopup "$NEOAPRS_TEXT" 10); '
                   'paplay /usr/share/sounds/freedesktop/stereo/message-new-instant.oga')       # what every save of the settings stored from migration 22 on, on Linux and macOS


def version_twenty_six(path: Path, clock: FixedClock, stored: dict[str, str]) -> None:
    """A database as version 26 left it, with these settings."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 27")
    step_back(db, 26)
    db.execute("PRAGMA user_version = 26")
    for key, value in stored.items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.close()


def migrate(folder: Path, stored: dict[str, str]) -> dict[str, str]:
    clock = FixedClock()
    old = folder / DB_NAME
    version_twenty_six(old, clock, stored)
    migrated = opened(old, clock)
    assert migrated.version() == SCHEMA_VERSION >= 27
    assert [(r[0], r[1], r[2]) for r in migrated.history()][26:] == [(27, "_v27", GOLDEN[27]), (28, "_v28", GOLDEN[28]), (29, "_v29", GOLDEN[29])]
    found = {str(k): str(v) for k, v in migrated.db.execute("SELECT key, value FROM settings")}
    migrated.close()
    return found


def test_the_default_of_migration_22_is_dropped_and_the_new_one_is_in_force(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        found = migrate(tmp_path, {"messages/alert_command": V22_LINUX_ALERT, "station/call": "OH2GBA"})
    assert found == {"station/call": "OH2GBA"}
    assert Config.from_data(found).messages_alert_command == DEFAULTS.messages_alert_command
    assert V22_LINUX_ALERT != LINUX_ALERT_COMMAND and "sed" in LINUX_ALERT_COMMAND
    assert "messages/alert_command was the old default" in caplog.text


@pytest.mark.parametrize("own", ['curl -s -d "$NEOAPRS_TEXT" https://ntfy.sh/x', V22_LINUX_ALERT + " ", LINUX_ALERT_COMMAND, WINDOWS_ALERT_COMMAND])
def test_a_command_of_the_operators_own_the_new_default_and_the_default_of_windows_are_kept(tmp_path: Path, own: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        found = migrate(tmp_path, {"messages/alert_command": own})
    assert found == {"messages/alert_command": own} and "old default" not in caplog.text


def test_a_database_without_the_row_is_left_alone(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        found = migrate(tmp_path, {"station/call": "OH2GBA"})
    assert found == {"station/call": "OH2GBA"} and "alert_command" not in caplog.text
