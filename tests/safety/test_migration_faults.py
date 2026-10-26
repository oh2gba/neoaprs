"""The migrations under failure (neoaprs/migrations.py, migrationsteps12to21.py): a step that doubts its own copy of a table, a step that raises what is not an SQLite error, a rollback that fails, a disk that is
full at the commit, a file another writer holds, another process that migrated first, a history that cannot be read or a source that cannot be hashed. In each the file is as it was or at the step before,
the copy taken before the first step is in backup/, and the next start with the cause gone migrates it."""
import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from neoaprs import migrations as migrations_module
from neoaprs.migrations import MIGRATIONS, SCHEMA_VERSION, _history_problems, history, open_database, source_hash
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, try_open
from tests.support.riggedsql import fails_at, rig_connect, then_runs
from tests.test_migration_rf_only import version_eleven
from tests.test_migration_via import version_twenty
from tests.test_migrations import NEXT, broken, raw, v_next, version_eight, version_nine, version_three, with_steps

Seed = Callable[[Path, FixedClock], None]
DELETE_A_ROW = "DELETE FROM {table} WHERE rowid = (SELECT MIN(rowid) FROM {table})"

# (the version a file is at, how to make it, the statement that makes the new table hold what the old one did, what makes it hold less, the old table and the new one)
DOUBTS = [
    pytest.param(3, version_three, "INSERT INTO station_pref (call, path, updated_at)", DELETE_A_ROW.format(table="station_pref"), "station_path", id="4: station_pref"),
    pytest.param(8, version_eight, "INSERT INTO station_pref (call, path, hide_after_min, updated_at)", DELETE_A_ROW.format(table="station_pref"), "station_pref_old", id="9: station_pref"),
    pytest.param(9, version_nine, "INSERT INTO message (id,", DELETE_A_ROW.format(table="message"), "message_old", id="10: message"),
    pytest.param(11, version_eleven, "INSERT INTO station_pref (call, path, hide_after_min, attempts, updated_at)", DELETE_A_ROW.format(table="station_pref"), "station_pref_old", id="12: station_pref"),
    pytest.param(20, version_twenty, "UPDATE station SET heard_rf = packets", "UPDATE station SET packets = packets + 1", "packet", id="21: station"),
]


def tables_and_version(path: Path) -> tuple[int, dict[str, int]]:
    db = raw(path)
    try:
        names = [str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        return int(db.execute("PRAGMA user_version").fetchone()[0]), {n: int(db.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]) for n in names}
    finally:
        db.close()


@pytest.mark.expects_errors
@pytest.mark.parametrize("version, seed, after, sabotage, old_table", DOUBTS)
def test_a_step_that_finds_its_new_table_unlike_the_old_one_changes_nothing_and_the_next_start_migrates(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: int, seed: Seed, after: str, sabotage: str, old_table: str) -> None:
    clock = FixedClock()
    path = tmp_path / DB_NAME
    seed(path, clock)
    was = tables_and_version(path)
    assert was[0] == version and was[1][old_table.removesuffix("_old") if old_table != "station_path" else old_table] > 0
    with monkeypatch.context() as patch:
        rig_connect(patch, after=then_runs(after, sabotage))
        ok, why = try_open(path, clock)
    assert not ok and "nothing was changed" in why, why
    assert tables_and_version(path) == was, "the step is rolled back whole: the version, the tables and every row are what they were"
    [copy] = sorted((tmp_path / "backup").glob(f"premigrate-v{version}-to-v{SCHEMA_VERSION}-*.sqlite"))
    assert tables_and_version(copy) == was, "and the copy taken before the first step holds the file as it was"
    s = opened(path, clock)
    assert s.version() == SCHEMA_VERSION and [r[0] for r in s.history()][version:] == [*range(version + 1, SCHEMA_VERSION + 1)]
    s.close()


@pytest.mark.expects_errors
def test_a_step_that_raises_what_is_not_an_sqlite_error_is_a_refusal_with_its_name_and_the_copy_is_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def corrupt_row(db: sqlite3.Connection) -> None:
        db.execute("CREATE TABLE half (x INTEGER)")
        raise ValueError("a row that no step can read")

    path = tmp_path / DB_NAME
    opened(path).close()
    with_steps(monkeypatch, corrupt_row)
    ok, why = try_open(path)
    assert not ok and "ValueError: a row that no step can read" in why and "backup/" in why
    assert any("ValueError" in r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)
    version, tables = tables_and_version(path)
    assert version == SCHEMA_VERSION and "half" not in tables
    assert len(list((tmp_path / "backup").glob(f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-*.sqlite"))) == 1
    monkeypatch.setattr(migrations_module, "MIGRATIONS", [*MIGRATIONS, v_next])
    s = opened(path)
    assert s.version() == NEXT and "beacon" in s.tables()
    s.close()


@pytest.mark.parametrize("failing", ["COMMIT", "PRAGMA user_version"])
def test_a_disk_that_is_full_at_the_end_of_a_step_refuses_the_file_at_the_step_before_and_it_migrates_once_there_is_room(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing: str) -> None:
    path = tmp_path / DB_NAME
    opened(path).close()
    with_steps(monkeypatch, v_next)
    with monkeypatch.context() as patch:
        rig_connect(patch, before=fails_at(failing, sqlite3.OperationalError("database or disk is full")))
        ok, why = try_open(path)
    assert not ok and "disk is full" in why
    version, tables = tables_and_version(path)
    assert version == SCHEMA_VERSION and "beacon" not in tables, "the step is rolled back: no table of it, no new version"
    s = opened(path)
    assert s.version() == NEXT and "beacon" in s.tables()
    s.close()


@pytest.mark.expects_errors
def test_a_rollback_that_fails_does_not_hide_why_the_step_failed_and_the_file_is_not_changed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / DB_NAME
    opened(path).close()
    with_steps(monkeypatch, broken)
    with monkeypatch.context() as patch:
        rig_connect(patch, before=fails_at("ROLLBACK", sqlite3.OperationalError("disk I/O error")))
        ok, why = try_open(path)
    assert not ok and "the disk is full" in why, "the reason is the step's, not the rollback's"
    version, tables = tables_and_version(path)
    assert version == SCHEMA_VERSION and "half" not in tables, "the connection was closed with the step open: SQLite rolls it back"


def test_a_file_that_another_writer_holds_is_refused_as_locked_and_not_touched_and_opens_when_it_is_let_go(tmp_path: Path) -> None:
    clock = FixedClock()
    path = tmp_path / DB_NAME
    version_three(path, clock)
    was = tables_and_version(path)
    holder = raw(path)
    holder.execute("BEGIN IMMEDIATE")
    db, why = open_database(path, busy_ms=20, clock=clock)
    assert db is None and "locked" in why
    assert tables_and_version(path) == was
    holder.execute("ROLLBACK")
    holder.close()
    s = opened(path, clock)
    assert s.version() == SCHEMA_VERSION
    s.close()


def test_a_step_that_another_process_has_run_meanwhile_is_not_run_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    clock = FixedClock()
    path = tmp_path / DB_NAME
    opened(path, clock).close()
    with_steps(monkeypatch, v_next)
    nested: list[bool] = []

    def other_process_first(conn: sqlite3.Connection, sql: str) -> None:
        if sql.startswith("BEGIN IMMEDIATE") and not nested:
            nested.append(True)                              # (the first step of this open is about to begin: the other open, which is whole, gets there first)
            other, why = open_database(path, clock=clock)
            assert other is not None, why
            other.close()

    caplog.set_level(logging.INFO, MIGRATION_LOG)
    rig_connect(monkeypatch, before=other_process_first)
    s = opened(path, clock)
    assert nested == [True] and s.version() == NEXT
    assert [r[0] for r in s.history()] == [*range(1, NEXT + 1)], "the step has one row in the history, not two"
    assert s.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'beacon'").fetchone() == (1,)
    s.close()
    assert len([r for r in caplog.records if r.name == MIGRATION_LOG and "is now version" in r.getMessage()]) == 1, "told once, by the open that ran it"


def test_a_source_that_cannot_be_read_hashes_as_unknown_and_is_not_held_against_the_file() -> None:
    namespace: dict[str, object] = {}
    exec("def made_at_run_time(db):\n    pass\n", namespace)                      # (no file to read the source from)
    assert source_hash(namespace["made_at_run_time"]) == "unknown"        # type: ignore[arg-type]
    assert source_hash(len) == "unknown"                                   # type: ignore[arg-type]


def test_a_history_that_is_not_there_or_cannot_be_read_is_empty_and_the_file_still_opens(tmp_path: Path) -> None:
    assert history(sqlite3.connect(":memory:")) == [] and _history_problems(sqlite3.connect(":memory:")) == []
    path = tmp_path / DB_NAME
    opened(path).close()
    db = raw(path)
    db.execute("DROP TABLE schema_history")
    db.close()
    s = opened(path)
    assert s.version() == SCHEMA_VERSION and s.history() == []
    s.close()

