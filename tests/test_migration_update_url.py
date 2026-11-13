"""Migration 26 (neoaprs/migrationsteps22on.py): the version page moved to the project's own name. A stored `update/url` that still holds the old default is deleted, so that the new default
(`neoaprs.versions.UPDATE_URL`) is in force, with one line in the log; an address set by hand is kept; a database without the row is left alone."""
import logging
from pathlib import Path

import pytest

from neoaprs.config import DEFAULTS, Config
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from neoaprs.versions import OLD_UPDATE_URL, UPDATE_URL
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, raw


def version_twenty_five(path: Path, clock: FixedClock, stored: dict[str, str]) -> None:
    """A database as version 25 left it, with these settings."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 26")
    step_back(db, 25)
    db.execute("PRAGMA user_version = 25")
    for key, value in stored.items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.close()


def migrate(folder: Path, stored: dict[str, str]) -> dict[str, str]:
    clock = FixedClock()
    old = folder / DB_NAME
    version_twenty_five(old, clock, stored)
    migrated = opened(old, clock)
    assert migrated.version() == SCHEMA_VERSION >= 26
    assert [(r[0], r[1], r[2]) for r in migrated.history()][25:] == [(26, "_v26", GOLDEN[26]), (27, "_v27", GOLDEN[27]), (28, "_v28", GOLDEN[28]), (29, "_v29", GOLDEN[29])]
    found = {str(k): str(v) for k, v in migrated.db.execute("SELECT key, value FROM settings")}
    migrated.close()
    return found


def test_the_old_default_is_dropped_and_the_new_one_is_in_force(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        found = migrate(tmp_path, {"update/url": OLD_UPDATE_URL, "station/call": "OH2GBA"})
    assert found == {"station/call": "OH2GBA"}
    assert Config.from_data(found).update_url == UPDATE_URL == DEFAULTS.update_url
    assert "update/url reset to the default: https://oh2gba.eu/neoaprs/version.php → https://neo.oh2gba.eu/version.php" in caplog.text


def test_an_address_set_by_hand_is_kept(tmp_path: Path) -> None:
    found = migrate(tmp_path, {"update/url": "http://127.0.0.1:8000/version.php", "station/call": "OH2GBA"})
    assert found == {"update/url": "http://127.0.0.1:8000/version.php", "station/call": "OH2GBA"}


def test_a_database_without_the_row_is_left_alone(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIGRATION_LOG):
        found = migrate(tmp_path, {"station/call": "OH2GBA"})
    assert found == {"station/call": "OH2GBA"} and "update/url" not in caplog.text
