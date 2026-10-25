"""Migration 14 (neoaprs/migrations2.py): an empty `beacon/path` meant no digipeaters, and now means the recommended path; the stored empty one becomes DIRECT so that nobody starts to digipeat on an upgrade."""
from pathlib import Path

from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, raw


def version_thirteen(path: Path, clock: FixedClock, stored: dict[str, str]) -> None:
    """A database as version 13 left it, with these settings."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 14")
    step_back(db, 13)
    db.execute("PRAGMA user_version = 13")
    for key, value in stored.items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.close()


def migrate(folder: Path, stored: dict[str, str]) -> dict[str, tuple[str, int]]:
    clock = FixedClock()
    folder.mkdir(parents=True, exist_ok=True)
    old = folder / DB_NAME
    version_thirteen(old, clock, stored)
    migrated = opened(old, clock)
    assert migrated.version() == SCHEMA_VERSION >= 14
    assert [(r[0], r[1], r[2]) for r in migrated.history()][13:] == [(14, "_v14", GOLDEN[14]), (15, "_v15", GOLDEN[15]), (16, "_v16", GOLDEN[16]), (17, "_v17", GOLDEN[17]), (18, "_v18", GOLDEN[18]), (19, "_v19", GOLDEN[19]), (20, "_v20", GOLDEN[20])]
    found = {str(k): (str(v), int(rev)) for k, v, rev in migrated.db.execute("SELECT key, value, rev FROM settings")}
    migrated.close()
    return found


def test_a_stored_empty_beacon_path_becomes_direct_only_and_nothing_else_is_touched(tmp_path: Path) -> None:
    found = migrate(tmp_path, {"beacon/path": "", "station/call": "OH2GBA"})
    assert found["beacon/path"] == ("DIRECT", 2), "cleared on purpose, so no digipeaters; the revision moves on"
    assert found["station/call"] == ("OH2GBA", 1)


def test_a_beacon_path_that_names_digipeaters_is_as_it_was(tmp_path: Path) -> None:
    assert migrate(tmp_path / "a", {"beacon/path": "WIDE1-1"})["beacon/path"] == ("WIDE1-1", 1)


def test_a_custom_beacon_path_is_as_it_was(tmp_path: Path) -> None:
    assert migrate(tmp_path / "b", {"beacon/path": "WIDE2-2"})["beacon/path"] == ("WIDE2-2", 1)


def test_a_database_with_no_beacon_path_stored_stays_so(tmp_path: Path) -> None:
    assert "beacon/path" not in migrate(tmp_path / "c", {"station/call": "OH2GBA"})
