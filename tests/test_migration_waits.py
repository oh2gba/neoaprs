"""What waits for the daemon while it brings its database up to date (a migration: minutes for a large file on a slow card): the note `neoaprs.migrating` (neoaprs/stopfile.py) that the migration keeps fresh
while it runs (neoaprs/migrations.py), the wait for the page of `neoaprs open` and of the desktop app, which does not run out while the note is fresh (neoaprs/cli/opencmd.py), and what `neoaprs doctor`
says of the daemon meanwhile (neoaprs/cli/daemonstate.py). The migration is made slow by a made-up step that waits for the test, never by a large file."""
import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from neoaprs import migrations as migrations_module
from neoaprs import stopfile
from neoaprs.cli import daemonstate, doctor, opencmd
from neoaprs.migrations import MIGRATIONS, open_database
from neoaprs.stopfile import MIGRATING_FRESH_SEC, MIGRATING_NAME, MigratingNote, migrating
from neoaprs.store import DB_NAME
from tests.support.migrated import opened

URL = "http://127.0.0.1:7303/"


class SlowStep:
    """A made-up migration step that waits until the test lets it go (or fails, when told to)."""

    def __init__(self) -> None:
        self.running = threading.Event()
        self.go = threading.Event()
        self.fail = False
        self.__name__ = "slow_step"

    def __call__(self, db: sqlite3.Connection) -> None:
        self.running.set()
        assert self.go.wait(30), "the test never let the step go"
        db.execute("CREATE TABLE slow (x INTEGER)")
        if self.fail:
            raise sqlite3.OperationalError("database or disk is full")


def a_file_to_migrate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, step: SlowStep) -> Path:
    path = tmp_path / DB_NAME
    s = opened(path)
    s.db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    s.close()
    steps = [*MIGRATIONS, step]
    monkeypatch.setattr(migrations_module, "MIGRATIONS", steps)
    monkeypatch.setattr(migrations_module, "SCHEMA_VERSION", len(steps))
    return path


def migrate_in_a_thread(path: Path) -> tuple[threading.Thread, list[str]]:
    why: list[str] = []

    def run() -> None:
        db, reason = open_database(path)
        why.append(reason)
        if db is not None:
            db.close()
    thread = threading.Thread(target=run, name="test-migration")
    thread.start()
    return thread, why


@pytest.mark.parametrize("fails", [pytest.param(False, id="gets through"), pytest.param(True, id="fails", marks=pytest.mark.expects_errors)])
def test_a_migration_that_takes_its_time_keeps_its_note_fresh_and_takes_it_away_at_its_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fails: bool) -> None:
    step = SlowStep()
    step.fail = fails
    path = a_file_to_migrate(tmp_path, monkeypatch, step)
    assert not migrating(tmp_path)
    thread, why = migrate_in_a_thread(path)
    try:
        assert step.running.wait(30)
        assert migrating(tmp_path), "while a step runs the note is there and fresh"
        monkeypatch.setattr(daemonstate, "is_running", lambda _: True)
        running, line = daemonstate.describe(tmp_path)
        assert running and line == "a daemon is running and is bringing its database up to date; its page comes when that is done"
        assert doctor.check_daemon(tmp_path).status == "ok", "doctor tells no fault of a daemon that is busy migrating"
    finally:
        step.go.set()
        thread.join(30)
    assert why == (["database or disk is full"] if fails else [""])
    assert not (tmp_path / MIGRATING_NAME).exists() and not migrating(tmp_path), "the note goes with the end of the migration, whole or not"


def test_a_file_at_its_version_or_new_gets_no_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[Path] = []
    monkeypatch.setattr(MigratingNote, "start", lambda self: written.append(self.path))
    opened(tmp_path / DB_NAME).close()               # (a new file: nothing in it to bring up to date)
    opened(tmp_path / DB_NAME).close()               # (at its version)
    assert written == []


def test_the_note_is_written_again_while_it_is_held_and_one_a_kill_left_goes_stale(tmp_path: Path) -> None:
    note = MigratingNote(tmp_path, beat_sec=0.02)
    note.stop()                                      # (not started: nothing)
    note.start()
    note.start()                                     # (once is enough)
    old = time.time() - MIGRATING_FRESH_SEC - 5
    os.utime(note.path, (old, old))
    assert not migrating(tmp_path)
    deadline = time.monotonic() + 10
    while not migrating(tmp_path) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert migrating(tmp_path), "the thread of the note writes it again"
    note.stop()
    note.stop()
    assert not note.path.exists()
    left = tmp_path / MIGRATING_NAME
    left.write_text("migrating\n", encoding="ascii")
    assert migrating(tmp_path) and not migrating(tmp_path, now=left.stat().st_mtime + MIGRATING_FRESH_SEC + 1), "the note of a migration that a kill ended is stale after a while"
    unwritable = MigratingNote(tmp_path / "a file" / "below")
    unwritable.start()
    unwritable.stop()


def test_the_wait_for_the_page_does_not_run_out_while_the_database_is_brought_up_to_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The page's 60 seconds (here 5 of virtual time) would end long before the migration does (here 100): the wait goes on while the note is fresh, starts its seconds again at its end, and the page is there
    when the rest of the start has come; `told` is said once."""
    step = SlowStep()
    path = a_file_to_migrate(tmp_path, monkeypatch, step)
    now = [0.0]
    page = threading.Event()
    told: list[str] = []
    monkeypatch.setattr(opencmd, "page_url", lambda _: URL if page.is_set() else None)
    monkeypatch.setattr(opencmd, "page_answers", lambda _: True)
    monkeypatch.setattr(opencmd, "is_running", lambda _: True)
    thread, why = migrate_in_a_thread(path)
    assert step.running.wait(30)

    def sleep(seconds: float) -> None:
        now[0] += 1.0
        if now[0] == 100.0:
            step.go.set()
            thread.join(30)                          # (the migration has ended and taken its note away)
        if now[0] == 103.0:
            page.set()                               # (the rest of the start: the page listens)
        time.sleep(0.001)

    try:
        url = opencmd.wait_for_page(tmp_path, None, 5.0, clock=lambda: now[0], sleep=sleep, told=lambda: told.append("migrating"))
    finally:
        step.go.set()
        thread.join(30)
    assert url == URL and now[0] == 103.0 and told == ["migrating"] and why == [""]


def test_the_wait_runs_out_as_before_when_no_migration_runs_or_its_note_is_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opencmd, "page_url", lambda _: None)
    left = tmp_path / MIGRATING_NAME
    left.write_text("migrating\n", encoding="ascii")
    old = time.time() - MIGRATING_FRESH_SEC - 5
    os.utime(left, (old, old))
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += 1.0

    told: list[str] = []
    assert opencmd.wait_for_page(tmp_path, None, 5.0, clock=lambda: now[0], sleep=sleep, told=lambda: told.append("x")) is None
    assert now[0] == 5.0 and told == []
    assert stopfile.migrating(tmp_path) is False


def test_a_note_ahead_of_the_clock_is_not_fresh_and_a_start_with_nothing_to_migrate_removes_a_stale_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A migration killed (a power cut) on a machine whose clock goes back at the next boot (a Raspberry Pi without a clock of its own) leaves a note dated ahead of the clock: it is not fresh, so the wait
    for the page runs out as before and doctor does not say a migration runs; and the next start that has nothing to migrate (the kill came after the last step) removes it. A fresh note, which another
    process keeps writing, stays."""
    monkeypatch.setattr(opencmd, "page_url", lambda _: None)
    left = tmp_path / MIGRATING_NAME
    left.write_text("migrating\n", encoding="ascii")
    ahead = time.time() + 3600
    os.utime(left, (ahead, ahead))
    assert not migrating(tmp_path), "a note an hour ahead was written before the clock went back"
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += 1.0
        assert now[0] < 600, "the wait never ran out"

    assert opencmd.wait_for_page(tmp_path, None, 5.0, clock=lambda: now[0], sleep=sleep) is None and now[0] == 5.0
    monkeypatch.setattr(daemonstate, "is_running", lambda _: True)
    monkeypatch.setattr(daemonstate, "page_url", lambda _: None)
    assert "bringing its database up to date" not in daemonstate.describe(tmp_path)[1]
    opened(tmp_path / DB_NAME).close()
    assert not left.exists(), "the note a kill left goes with the next start"
    left.write_text("migrating\n", encoding="ascii")
    opened(tmp_path / DB_NAME).close()
    assert left.exists(), "a fresh note is somebody else's"
