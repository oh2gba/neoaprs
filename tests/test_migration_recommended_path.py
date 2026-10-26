"""Migration 15 (neoaprs/migrationsteps12to21.py): the recommended path follows the station's type. A save stores every setting, so the old default `WIDE1-1,WIDE2-1` of `beacon/path` is in the database of nearly every install
whether its operator chose it or not; it becomes empty (the recommended path). Any other stored path is as it was."""
from pathlib import Path

from neoaprs.config import Config
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, step_back
from tests.test_migrations import GOLDEN, raw


def version_fourteen(path: Path, clock: FixedClock, stored: dict[str, str]) -> None:
    """A database as version 14 left it, with these settings."""
    opened(path, clock).close()
    db = raw(path)
    db.execute("DELETE FROM schema_history WHERE version >= 15")
    step_back(db, 14)
    db.execute("PRAGMA user_version = 14")
    for key, value in stored.items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.close()


def migrate(folder: Path, stored: dict[str, str]) -> dict[str, tuple[str, int]]:
    clock = FixedClock()
    folder.mkdir(parents=True, exist_ok=True)
    old = folder / DB_NAME
    version_fourteen(old, clock, stored)
    migrated = opened(old, clock)
    assert migrated.version() == SCHEMA_VERSION >= 15
    assert [(r[0], r[1], r[2]) for r in migrated.history()][14:] == [(15, "_v15", GOLDEN[15]), (16, "_v16", GOLDEN[16]), (17, "_v17", GOLDEN[17]), (18, "_v18", GOLDEN[18]), (19, "_v19", GOLDEN[19]), (20, "_v20", GOLDEN[20]), (21, "_v21", GOLDEN[21])]
    found = {str(k): (str(v), int(rev)) for k, v, rev in migrated.db.execute("SELECT key, value, rev FROM settings")}
    migrated.close()
    return found


def test_the_old_default_path_becomes_the_recommended_one_and_nothing_else_is_touched(tmp_path: Path) -> None:
    found = migrate(tmp_path, {"beacon/path": "WIDE1-1,WIDE2-1", "station/call": "OH2GBA", "station/symbol_code": "-"})
    assert found["beacon/path"] == ("", 2), "the default that every save stored is the recommended path of the station's type; the revision moves on"
    assert found["station/call"] == ("OH2GBA", 1) and found["station/symbol_code"] == ("-", 1)


def test_a_custom_path_and_direct_only_are_as_they_were(tmp_path: Path) -> None:
    assert migrate(tmp_path / "a", {"beacon/path": "WIDE2-2"})["beacon/path"] == ("WIDE2-2", 1), "the owner's own WIDE2-2"
    assert migrate(tmp_path / "b", {"beacon/path": "DIRECT"})["beacon/path"] == ("DIRECT", 1)
    assert migrate(tmp_path / "c", {"beacon/path": "WIDE2-1"})["beacon/path"] == ("WIDE2-1", 1)
    assert migrate(tmp_path / "d", {"beacon/path": "WIDE1-1,WIDE2-2"})["beacon/path"] == ("WIDE1-1,WIDE2-2", 1)
    assert migrate(tmp_path / "e", {"beacon/path": ""})["beacon/path"] == ("", 1)


def test_a_database_with_no_beacon_path_stored_stays_so(tmp_path: Path) -> None:
    assert "beacon/path" not in migrate(tmp_path / "f", {"station/call": "OH2GBA"})


def test_after_the_migration_the_path_follows_the_symbol_and_the_custom_path_stays() -> None:
    house = Config.from_data({"beacon/path": "", "station/symbol_table": "/", "station/symbol_code": "-"})
    car = Config.from_data({"beacon/path": "", "station/symbol_table": "/", "station/symbol_code": ">"})
    owner = Config.from_data({"beacon/path": "WIDE2-2", "station/symbol_table": "/", "station/symbol_code": ">"})
    assert house.beacon_path_calls == ("WIDE2-1",) and car.beacon_path_calls == ("WIDE1-1", "WIDE2-1") and owner.beacon_path_calls == ("WIDE2-2",)
