"""The migrations under failure (neoaprs/migrations.py, migrationsteps12to21.py): a step that doubts its own copy of a table, a step that raises what is not an SQLite error, a rollback that fails, a disk that is
full at the commit, a file another writer holds, another process that migrated first, a history that cannot be read or a source that cannot be hashed. In each the file is as it was or at the step before,
the copy taken before the first step is in backup/, and the next start with the cause gone migrates it."""
import logging
import os
import signal
import sqlite3
import subprocess
import sys
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
    """The other gets there between this one's lock and its first step: one that takes no migration lock (a NeoAPRS before 0.20, or an open within an open, as here); the step's own check keeps it from
    running twice."""
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


# ---- a migration killed (SIGKILL, the OOM killer, a power cut) at each place, once, twice and three times: a child process runs it with three made-up steps and kills itself where it is told

KILLED = r'''
import os, signal, sqlite3, sys
from neoaprs import migrations
path, where = sys.argv[1], sys.argv[2]

def die(*_):
    os.kill(os.getpid(), signal.SIGKILL)

def first(db):
    db.execute("CREATE TABLE k1_first (x INTEGER)")
    db.execute("INSERT INTO k1_first VALUES (1)")

def second(db):
    db.execute("UPDATE settings SET value = value || ' (changed by the second step)'")
    db.execute("CREATE TABLE k1_second (x INTEGER)")

def third(db):
    db.execute("UPDATE settings SET value = value || ' (and by the third)'")
    db.execute("CREATE TABLE k1_third (x INTEGER)")

def killed_in(step, marker):
    def run(db):
        db.set_trace_callback(lambda statement: die() if statement.startswith(marker) else None)
        step(db)
    run.__name__ = step.__name__
    return run

steps = [first, second, third]
if where.startswith("step"):
    n = int(where[4:])
    steps[n - 1] = killed_in(steps[n - 1], "CREATE TABLE")      # (after the step's first statement: the step is half done in its transaction)
migrations.MIGRATIONS = [*migrations.MIGRATIONS, *steps]
migrations.SCHEMA_VERSION = len(migrations.MIGRATIONS)
if where == "copy":
    def half_a_copy(src, dest):
        out = sqlite3.connect(str(dest.with_name(dest.name + ".tmp")))
        src.backup(out, pages=2, progress=die)       # (killed after the first two pages: the temporary file is half written)
    migrations._copy_database = half_a_copy
elif where == "before":
    migrations._step = die
elif where == "drop":
    migrations.drop_older_copies = die
db, why = migrations.open_database(path)
if db is None:
    print(why)
    raise SystemExit(3)
db.close()
'''


def run_killed(path: Path, where: str) -> int:
    """The migration of `path` in a child process that kills itself at `where` (`copy`: while the copy is written; `before`: between the copy and the first step; `stepN`: in the made-up step N;
    `drop`: after the last step, before the older copies are removed; `none`: not at all). Its exit code."""
    root = Path(__file__).resolve().parents[2]
    return subprocess.run([sys.executable, "-c", KILLED, str(path), where], cwd=root, capture_output=True, timeout=120).returncode


def a_kept_file(path: Path) -> dict[str, int]:
    """A file at the program's version with settings, packets and a station, and what it holds."""
    s = opened(path)
    s.db.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", [("station/call", "OH2GBA"), ("station/symbol", "/-")])
    s.db.executemany("INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded) VALUES (?, 'in', ?, ?, 'APRS', '', 'other', ?, '{}')",
                     [(f"2026-11-14T12:{i // 60:02d}:{i % 60:02d}.000000Z", f"OH{i}>APRS:x".encode(), f"OH{i}", "x" * 300) for i in range(300)])
    s.close()
    return tables_and_version(path)[1]


def taken(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.glob("premigrate-*.sqlite"))


def at_the_old_version_as_it_was(copy: Path, held: dict[str, int]) -> bool:
    version, tables = tables_and_version(copy)
    db = raw(copy)
    try:
        settings = db.execute("SELECT value FROM settings ORDER BY key").fetchall()
    finally:
        db.close()
    return version == SCHEMA_VERSION and tables == held and settings == [("OH2GBA",), ("/-",)]


KILLED_BY = getattr(signal, "SIGKILL", 9)            # (the exit code of a child that the kill ended is its negative)
KILLS_HERE = pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL is POSIX's; Windows ends a process with TerminateProcess, which these children cannot ask for themselves")


@KILLS_HERE
@pytest.mark.parametrize("kills", [
    pytest.param([("step2", NEXT), ("step2", NEXT), ("step3", NEXT + 1)], id="in the second step twice, then in the third"),
    pytest.param([("step1", SCHEMA_VERSION), ("before", SCHEMA_VERSION), ("step1", SCHEMA_VERSION)], id="in the first step, between the copy and the first step, in the first step again"),
    pytest.param([("copy", SCHEMA_VERSION), ("step2", NEXT), ("step3", NEXT + 1)], id="while the copy is written, in the second step, in the third"),
])
def test_a_migration_killed_again_and_again_ends_with_one_copy_the_one_of_the_old_version(tmp_path: Path, kills: list[tuple[str, int]]) -> None:
    """Whatever kills it where: the file is at the version of the last step that was in, every start after the first copy makes no other (a station that a power cut or the OOM killer stops again and again
    does not fill its disk), and the start that gets through leaves backup/ with the copy of the file as the program before left it; the copy of the migration before goes, a copy made by hand stays."""
    path = tmp_path / DB_NAME
    held = a_kept_file(path)
    folder = tmp_path / "backup"
    folder.mkdir()
    (folder / "premigrate-v29-to-v30-20261001-120000.sqlite").write_bytes(b"the copy of the migration before")
    made_by_hand = folder / "before-the-update.sqlite"
    made_by_hand.write_bytes(path.read_bytes())
    copies: list[str] = []
    for where, version in kills:
        assert run_killed(path, where) == -KILLED_BY
        assert tables_and_version(path)[0] == version, f"killed at {where}: the file is at the version of the last step that was in"
        now = [n for n in taken(folder) if n not in ("premigrate-v29-to-v30-20261001-120000.sqlite",)]
        assert len(now) <= 1 and (not copies or now == copies), f"killed at {where}: one copy at most, the first one made: {now}"
        copies = now
    assert run_killed(path, "none") == 0
    version, tables = tables_and_version(path)
    assert version == NEXT + 2 and {"k1_first", "k1_second", "k1_third"} <= set(tables)
    [kept] = taken(folder)
    assert kept.startswith(f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT + 2}-") and at_the_old_version_as_it_was(folder / kept, held)
    assert made_by_hand.is_file(), "the hand's copy stays"
    assert all(n.endswith((".sqlite.tmp", ".sqlite.tmp-journal")) for n in {p.name for p in folder.iterdir()} - {kept, made_by_hand.name}), "what else is there is the litter of a copy a kill ended, for the sweep"
    db = raw(path)
    assert db.execute("SELECT value FROM settings WHERE key = 'station/call'").fetchone() == ("OH2GBA (changed by the second step) (and by the third)",), "each step ran once"
    db.close()


@KILLS_HERE
def test_a_copy_of_a_middle_version_an_earlier_program_left_goes_and_the_old_one_stays(tmp_path: Path) -> None:
    """Killed in the second step, a copy of the middle version beside the one of the old version (as the join's rule of 14 November made them): the start that gets through stands on the old one and removes the other."""
    path = tmp_path / DB_NAME
    held = a_kept_file(path)
    folder = tmp_path / "backup"
    assert run_killed(path, "step2") == -KILLED_BY
    [old] = taken(folder)
    middle = folder / f"premigrate-v{NEXT}-to-v{NEXT + 2}-20991231-235959.sqlite"
    source = raw(path)
    try:
        from neoaprs.dbfile import copy_database
        copy_database(source, middle)
    finally:
        source.close()
    assert run_killed(path, "none") == 0
    assert taken(folder) == [old] and at_the_old_version_as_it_was(folder / old, held)


@KILLS_HERE
def test_a_start_killed_after_the_last_step_leaves_the_copies_of_the_migration_before_to_the_next_one(tmp_path: Path) -> None:
    """The one place where backup/ keeps more after a migration that ended whole: a kill between the last step and the removal of the older copies (the next start has nothing to migrate)."""
    path = tmp_path / DB_NAME
    held = a_kept_file(path)
    folder = tmp_path / "backup"
    folder.mkdir()
    (folder / "premigrate-v29-to-v30-20261001-120000.sqlite").write_bytes(b"the copy of the migration before")
    assert run_killed(path, "drop") == -KILLED_BY
    assert tables_and_version(path)[0] == NEXT + 2
    names = taken(folder)
    assert len(names) == 2 and names[0] == "premigrate-v29-to-v30-20261001-120000.sqlite" and at_the_old_version_as_it_was(folder / names[1], held)


def test_a_migration_killed_while_two_others_wait_for_it_is_taken_over_by_one_and_the_third_waits_for_that_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """A tool migrates (in a step longer than any busy time), and two more NeoAPRS start meanwhile: this process (the daemon) and a child (another tool). Both wait. The tool is killed in its step (on
    Windows TerminateProcess, the parent's kill: it runs everywhere). One of the two takes over: it stands on the tool's copy, makes none and runs the step the kill ended; the other waits for that one and
    finds the file at the newest version. The file ends whole, each step in it once, and backup/ holds one copy, of the old version."""
    from tests.test_migration_waits import NEWEST, WAITS, a_station_to_migrate, another_neoaprs, ended, in_the_second_step, open_in_a_thread, said, until, version_of
    caplog.set_level(logging.INFO, MIGRATION_LOG)
    path, held = a_station_to_migrate(tmp_path, monkeypatch)
    tool = another_neoaprs(path, held)
    second: subprocess.Popen[bytes] | None = None
    try:
        until(lambda: tool.pid in in_the_second_step(held), "the tool runs the second step")
        second = another_neoaprs(path, held, busy_ms=300)
        thread, out = open_in_a_thread(path, busy_ms=300)
        child_log = held / f"log-{second.pid}"
        until(lambda: said(caplog, WAITS) == 1 and child_log.is_file() and WAITS in child_log.read_text(encoding="utf-8"), "both say that they wait")
        tool.kill()
        tool.wait(60)
        assert version_of(path) == SCHEMA_VERSION + 1, "killed in its second step: the first is in"
        (held / "go").touch()
        thread.join(60)
        assert second.wait(60) == 0, second.communicate()[0]
    finally:
        (held / "go").touch()
        ended(tool)
        if second is not None:
            ended(second)
    assert out == [("", NEWEST)]
    took_over = in_the_second_step(held) - {tool.pid}
    assert len(took_over) == 1 and took_over <= {second.pid, os.getpid()}, "the step the kill ended ran once more, in one of the two"
    lines = [r.getMessage() for r in caplog.records if r.name == MIGRATION_LOG] + child_log.read_text(encoding="utf-8").splitlines()
    assert sum("taken by a start that did not get through; no other is made" in line for line in lines) == 1 and not any("a copy of it is in" in line for line in lines)
    assert sum(WAITS in line for line in lines) == 2, "each said once that it waits"
    [copy] = taken(tmp_path / "backup")
    assert copy.startswith(f"premigrate-v{SCHEMA_VERSION}-to-v{NEWEST}-") and tables_and_version(tmp_path / "backup" / copy)[0] == SCHEMA_VERSION
    version, tables = tables_and_version(path)
    assert version == NEWEST and {"k2_first", "k2_second"} <= set(tables)
    db = raw(path)
    assert db.execute("SELECT value FROM settings WHERE key = 'station/call'").fetchone() == ("OH2GBA (and the second step)",), "each step ran once whole"
    assert [r[0] for r in db.execute("SELECT version FROM schema_history ORDER BY version")][-2:] == [SCHEMA_VERSION + 1, NEWEST]
    db.close()
    assert not (tmp_path / "neoaprs.migrating").exists()


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

