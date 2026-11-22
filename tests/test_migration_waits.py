"""What waits for the daemon while its database is migrated: the `neoaprs.migrating` note
(neoaprs/stopfile.py) kept fresh by the migration, the wait of `neoaprs open` and the desktop app
that lasts while it is fresh, and the limits of that wait.
"""

import itertools
import logging
import os
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from neoaprs import migrations as migrations_module
from neoaprs import stopfile
from neoaprs.cli import daemonstate, doctor, opencmd
from neoaprs.instancelock import InstanceLock
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.migrations import MIGRATIONS, SCHEMA_VERSION, open_database
from neoaprs.stopfile import MIGRATE_LOCK_NAME, MIGRATING_FRESH_SEC, MIGRATING_NAME, MigratingNote, migrating
from neoaprs.store import DB_NAME
from tests.support.migrated import opened

URL = "http://127.0.0.1:7303/"
WAITS = "is being brought up to date by another NeoAPRS"


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


@pytest.mark.parametrize(
    "fails", [pytest.param(False, id="gets through"), pytest.param(True, id="fails", marks=pytest.mark.expects_errors)]
)
def test_a_migration_that_takes_its_time_keeps_its_note_fresh_and_takes_it_away_at_its_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
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
        assert (
            running
            and line == "a daemon is running and is bringing its database up to date; its page comes when that is done"
        )
        assert doctor.check_daemon(tmp_path).status == "ok", "doctor tells no fault of a daemon that is busy migrating"
    finally:
        step.go.set()
        thread.join(30)
    assert why == (["database or disk is full"] if fails else [""])
    assert not (tmp_path / MIGRATING_NAME).exists() and not migrating(tmp_path), (
        "the note goes with the end of the migration, whole or not"
    )


def test_a_file_at_its_version_or_new_gets_no_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[Path] = []
    monkeypatch.setattr(MigratingNote, "start", lambda self: written.append(self.path))
    opened(tmp_path / DB_NAME).close()  # (a new file: nothing in it to bring up to date)
    opened(tmp_path / DB_NAME).close()  # (at its version)
    assert written == []


def test_the_note_is_written_again_while_it_is_held_and_one_a_kill_left_goes_stale(tmp_path: Path) -> None:
    note = MigratingNote(tmp_path, beat_sec=0.02)
    note.stop()  # (not started: nothing)
    note.start()
    note.start()  # (once is enough)
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
    assert migrating(tmp_path) and not migrating(tmp_path, now=left.stat().st_mtime + MIGRATING_FRESH_SEC + 1), (
        "the note of a migration that a kill ended is stale after a while"
    )
    unwritable = MigratingNote(tmp_path / "a file" / "below")
    unwritable.start()
    unwritable.stop()


def test_the_wait_for_the_page_does_not_run_out_while_the_database_is_brought_up_to_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page's 60 seconds (here 5 of virtual time) would end long before the migration does (here
    100): the wait goes on while the note is fresh, starts its seconds again at its end, and the
    page is there when the rest of the start has come; `told` is said once."""
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
            thread.join(30)  # (the migration has ended and taken its note away)
        if now[0] == 103.0:
            page.set()  # (the rest of the start: the page listens)
        time.sleep(0.001)

    try:
        url = opencmd.wait_for_page(
            tmp_path, None, 5.0, clock=lambda: now[0], sleep=sleep, told=lambda: told.append("migrating")
        )
    finally:
        step.go.set()
        thread.join(30)
    assert url == URL and now[0] == 103.0 and told == ["migrating"] and why == [""]


def test_the_wait_runs_out_as_before_when_no_migration_runs_or_its_note_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(opencmd, "page_url", lambda _: None)
    left = tmp_path / MIGRATING_NAME
    left.write_text("migrating\n", encoding="ascii")
    old = time.time() - MIGRATING_FRESH_SEC - 5
    os.utime(left, (old, old))
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += 1.0

    told: list[str] = []
    assert (
        opencmd.wait_for_page(tmp_path, None, 5.0, clock=lambda: now[0], sleep=sleep, told=lambda: told.append("x"))
        is None
    )
    assert now[0] == 5.0 and told == []
    assert stopfile.migrating(tmp_path) is False


def test_a_note_ahead_of_the_clock_is_not_fresh_and_a_start_with_nothing_to_migrate_removes_a_stale_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A migration killed (a power cut) on a machine whose clock goes back at the next boot (a
    Raspberry Pi without a clock of its own) leaves a note dated ahead of the clock: it is not
    fresh, so the wait for the page runs out as before and doctor does not say a migration runs; and
    the next start that has nothing to migrate (the kill came after the last step) removes it. A
    fresh note, which another process keeps writing, stays."""
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


# ---- a NeoAPRS that is to migrate the file while another one does

# Two made-up steps after the program's own, the same in every process (exec'd: no source to hash,
# so the history does not hold one process's code against another's): the second tells the test that
# it runs, by a file named after its process, and waits until the test lets it go (the file `go`). A
# child is named by the number the test gave it (its last argument), not by its process id: on
# Windows the python of a virtual environment is a launcher that starts the interpreter as a process
# of its own, so the id the test has of its child is not the one the child reads of itself.
STEPS = r"""
import os, time
from pathlib import Path
WHO = globals().get("WHO") or str(os.getpid())

def k2_first(db):
    db.execute("CREATE TABLE k2_first (x INTEGER)")

def k2_second(db):
    held = Path(HELD)
    (held / f"in-the-second-step-{WHO}").write_text("")
    deadline = time.monotonic() + 60
    while not (held / "go").exists():
        if time.monotonic() > deadline:
            raise RuntimeError("the test never let the step go")
        time.sleep(0.02)
    db.execute("CREATE TABLE k2_second (x INTEGER)")
    db.execute("UPDATE settings SET value = value || ' (and the second step)' WHERE key = 'station/call'")
"""

OTHER = (
    r"""
import logging, os, sys
from pathlib import Path
from neoaprs import migrations
path, HELD, busy, WHO = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
"""
    + STEPS
    + r"""
logging.basicConfig(filename=str(Path(HELD) / f"log-{WHO}"), level=logging.INFO, format="%(message)s")
migrations.MIGRATIONS = [*migrations.MIGRATIONS, k2_first, k2_second]
migrations.SCHEMA_VERSION = len(migrations.MIGRATIONS)
db, why = migrations.open_database(path, busy)
if db is None:
    print(why)
    raise SystemExit(3)
db.close()
"""
)
NEWEST = SCHEMA_VERSION + 2


def a_station_to_migrate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A file at the program's version with a setting, the two made-up steps in this process too,
    and the folder the steps and the test tell each other through."""
    path = tmp_path / DB_NAME
    s = opened(path)
    s.db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    s.close()
    held = tmp_path / "held"
    held.mkdir()
    steps: dict[str, object] = {"HELD": str(held)}
    exec(STEPS, steps)
    monkeypatch.setattr(migrations_module, "MIGRATIONS", [*MIGRATIONS, steps["k2_first"], steps["k2_second"]])
    monkeypatch.setattr(migrations_module, "SCHEMA_VERSION", NEWEST)
    return path, held


def another_neoaprs(path: Path, held: Path, busy_ms: int = 30000) -> "subprocess.Popen[bytes]":
    """`open_database` of `path` in a child process with the same made-up steps (a tool, `neoaprs db
    set`, has the tools' busy time); it ends with 0 when it opened the file, 3 when refused."""
    root = Path(__file__).resolve().parents[1]
    name = next(_names)
    proc = subprocess.Popen(
        [sys.executable, "-c", OTHER, str(path), str(held), str(busy_ms), str(name)],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    _who[proc.pid] = name
    _watched.append((held, proc))
    return proc


# Above every process id, so that a child's name is never taken for this process's own id, which
# names the steps it runs itself
_names = itertools.count(1_000_000_000)
_who: dict[int, int] = {}


def who(proc: "subprocess.Popen[bytes]") -> int:
    """The name the test gave this child, which its steps' files and its log carry."""
    return _who[proc.pid]


def in_the_second_step(held: Path) -> set[int]:
    """The processes that ran (or run) the second made-up step."""
    return {int(p.name.rsplit("-", 1)[1]) for p in held.glob("in-the-second-step-*")}


def until(done: Callable[[], bool], what: str, seconds: float = 60.0) -> None:
    deadline = time.monotonic() + seconds
    while not done():
        assert time.monotonic() < deadline, f"never: {what}{_said_by_the_others()}"
        time.sleep(0.02)


_watched: list[tuple[Path, "subprocess.Popen[bytes]"]] = []


def _said_by_the_others() -> str:
    """What the child processes of this test logged and how each stands, for the message of a wait
    that ran out: without it a child that failed at its first line looks like one that never got
    there."""
    lines = []
    for held, proc in _watched:
        lines.append(f"\nchild {proc.pid}: {'running' if proc.poll() is None else f'ended with {proc.returncode}'}")
        log = held / f"log-{who(proc)}"
        if log.exists():
            lines.append(log.read_text(encoding="utf-8", errors="replace")[-3000:])
        if proc.poll() is not None and proc.stdout is not None:
            lines.append(proc.stdout.read().decode("utf-8", "replace")[-3000:])
    return "".join(lines)


def open_in_a_thread(path: Path, busy_ms: int) -> tuple[threading.Thread, list[tuple[str, int]]]:
    """`open_database(path, busy_ms)` as the daemon makes it (its busy time is 3 s; the tests give
    less, which the wait does not depend on): the reason and the version it found, once it has
    returned."""
    out: list[tuple[str, int]] = []

    def run() -> None:
        db, why = open_database(path, busy_ms)
        out.append((why, -1 if db is None else int(db.execute("PRAGMA user_version").fetchone()[0])))
        if db is not None:
            db.close()

    thread = threading.Thread(target=run, name="test-open")
    thread.start()
    return thread, out


def said(caplog: pytest.LogCaptureFixture, text: str) -> int:
    return sum(1 for r in caplog.records if r.name == MIGRATION_LOG and text in r.getMessage())


def version_of(path: Path) -> int:
    db = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        return int(db.execute("PRAGMA user_version").fetchone()[0])
    finally:
        db.close()


def taken(tmp_path: Path) -> list[str]:
    return sorted(p.name for p in (tmp_path / "backup").glob("premigrate-*"))


def ended(child: "subprocess.Popen[bytes]") -> None:
    if child.poll() is None:
        child.kill()
    child.communicate(timeout=60)


def test_a_start_while_another_neoaprs_migrates_the_file_waits_for_it_says_so_once_and_comes_up_at_the_newest_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The daemon starts while a tool migrates the file (the tool is in a step that takes longer
    than the daemon's busy time): the daemon waits for it, says so once, and opens the file at the
    newest version with nothing of its own to do: no copy of its own, no step run twice; before this
    it was refused ("database is locked") after its busy time and the unit did not start it again.
    """
    caplog.set_level(logging.INFO, MIGRATION_LOG)
    path, held = a_station_to_migrate(tmp_path, monkeypatch)
    tool = another_neoaprs(path, held)
    try:
        until(lambda: who(tool) in in_the_second_step(held), "the tool runs the second step")
        assert migrating(tmp_path) and version_of(path) == SCHEMA_VERSION + 1
        thread, out = open_in_a_thread(path, busy_ms=300)
        until(lambda: said(caplog, WAITS) == 1, "the start says that it waits")
        time.sleep(1.0)  # (three times the busy time)
        assert thread.is_alive() and out == [], "it waits past its busy time"
        (held / "go").touch()
        thread.join(60)
        assert tool.wait(60) == 0, tool.communicate()[0]
    finally:
        (held / "go").touch()
        ended(tool)
    assert out == [("", NEWEST)]
    assert said(caplog, WAITS) == 1, "said once"
    assert (
        said(caplog, "is now version") == 0
        and said(caplog, "a copy of it is in") == 0
        and in_the_second_step(held) == {who(tool)}
    ), "the start ran no step and made no copy"
    [copy] = taken(tmp_path)
    assert copy.startswith(f"premigrate-v{SCHEMA_VERSION}-to-v{NEWEST}-") and copy.endswith(".sqlite"), (
        "one copy, the tool's, of the old version"
    )
    assert not (tmp_path / MIGRATING_NAME).exists()


@pytest.mark.parametrize("note", ["stale", "ahead of the clock"])
@pytest.mark.parametrize("holder", ["a writer of the file", "the migration's lock"])
def test_a_note_that_is_not_fresh_is_never_waited_on_and_a_file_held_meanwhile_is_refused_within_the_busy_time(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, note: str, holder: str
) -> None:
    """A note a kill left (stale, or dated ahead of a clock that went back) is not a migration that
    runs: a file another writer holds is refused as before ("database is locked") after the busy
    time, and a migration's lock that is held with no fresh note (its process stuck) is refused
    after the busy time too, saying why; neither waits, and the file is as it was."""
    caplog.set_level(logging.INFO, MIGRATION_LOG)
    path = tmp_path / DB_NAME
    s = opened(path)
    s.db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    s.close()
    left = tmp_path / MIGRATING_NAME
    left.write_text("migrating\n", encoding="ascii")
    when = time.time() + (3600 if note == "ahead of the clock" else -MIGRATING_FRESH_SEC - 5)
    os.utime(left, (when, when))
    holds: sqlite3.Connection | InstanceLock
    if holder == "a writer of the file":
        holds = sqlite3.connect(path, isolation_level=None)
        holds.execute("BEGIN IMMEDIATE")
    else:
        holds = InstanceLock(tmp_path, MIGRATE_LOCK_NAME)
        holds.acquire()
    steps = [*MIGRATIONS, lambda db: db.execute("CREATE TABLE k2_never (x INTEGER)")]
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(migrations_module, "MIGRATIONS", steps)
            patch.setattr(migrations_module, "SCHEMA_VERSION", len(steps))
            began = time.monotonic()
            db, why = open_database(path, busy_ms=300)
            took = time.monotonic() - began
    finally:
        holds.close() if isinstance(holds, sqlite3.Connection) else holds.release()
    assert db is None and (
        "locked" in why
        if holder == "a writer of the file"
        else "shows no sign that it is still at it (stopped, or stuck)" in why
    ), why
    # The wrong behaviour, a wait on the note, would last MIGRATION_WAIT_SEC: an hour; the ceiling
    # leaves a busy machine its time
    assert 0.3 <= took < 30.0, took
    assert said(caplog, WAITS) == 0, "no wait on a note that is not fresh"
    assert version_of(path) == SCHEMA_VERSION


@pytest.mark.expects_errors
def test_the_wait_has_a_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A migration whose process lives but never ends is waited for MIGRATION_WAIT_SEC and no
    longer: refused, saying why, with nothing changed."""
    caplog.set_level(logging.INFO, MIGRATION_LOG)
    path = tmp_path / DB_NAME
    opened(path).close()
    steps = [*MIGRATIONS, lambda db: db.execute("CREATE TABLE k2_never (x INTEGER)")]
    monkeypatch.setattr(migrations_module, "MIGRATIONS", steps)
    monkeypatch.setattr(migrations_module, "SCHEMA_VERSION", len(steps))
    assert migrations_module.MIGRATION_WAIT_SEC == 3600.0, "an hour"
    monkeypatch.setattr(migrations_module, "MIGRATION_WAIT_SEC", 0.8)
    lock = InstanceLock(tmp_path, MIGRATE_LOCK_NAME)
    lock.acquire()
    note = MigratingNote(tmp_path, beat_sec=0.05)
    note.start()
    try:
        began = time.monotonic()
        db, why = open_database(path, busy_ms=300)
        took = time.monotonic() - began
    finally:
        note.stop()
        lock.release()
    assert (
        db is None
        and "another NeoAPRS has been bringing it up to date for 0.8 seconds, longer than a migration takes: this one waited no longer"
        in why
    ), why
    assert 0.8 <= took < 30.0 and said(caplog, WAITS) == 1  # (a wait without its bound would last for ever)
    assert version_of(path) == SCHEMA_VERSION and not (tmp_path / "backup").exists()


@pytest.mark.expects_errors
def test_a_migration_that_stops_showing_it_is_at_it_while_waited_for_is_refused_after_the_busy_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The other's note was fresh, so this one waited; then it stops being written while the lock
    stays held (a tool stopped with Ctrl-Z in its step, or stuck): the wait ends the busy time after
    the note went stale, refused with a reason that names no seconds it did not wait (it waited
    longer), and the file is as it was."""
    caplog.set_level(logging.INFO, MIGRATION_LOG)
    path = tmp_path / DB_NAME
    opened(path).close()
    steps = [*MIGRATIONS, lambda db: db.execute("CREATE TABLE k2_never (x INTEGER)")]
    monkeypatch.setattr(migrations_module, "MIGRATIONS", steps)
    monkeypatch.setattr(migrations_module, "SCHEMA_VERSION", len(steps))
    lock = InstanceLock(tmp_path, MIGRATE_LOCK_NAME)
    lock.acquire()
    note = MigratingNote(tmp_path, beat_sec=0.05)
    note.start()
    try:
        began = time.monotonic()
        thread, out = open_in_a_thread(path, busy_ms=300)
        until(lambda: said(caplog, WAITS) == 1, "the start says that it waits")
        time.sleep(0.6)
        assert thread.is_alive(), "it waits while the note is fresh"
        # The note is no longer written: gone, as stale as it gets.
        note.stop()
        stale_at = time.monotonic()
        thread.join(60)
        took, waited = time.monotonic() - stale_at, time.monotonic() - began
    finally:
        note.stop()
        lock.release()
    [(why, version)] = out
    assert (
        version == -1 and "shows no sign that it is still at it (stopped, or stuck)" in why and "seconds" not in why
    ), why
    # A wait on past the stale note would last MIGRATION_WAIT_SEC: an hour
    assert 0.3 <= took < 30.0 and waited >= 0.9, (took, waited)
    assert said(caplog, WAITS) == 1 and version_of(path) == SCHEMA_VERSION and not (tmp_path / "backup").exists()


def test_a_start_with_nothing_to_migrate_does_not_wait_or_take_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A new file and a file at the newest version open as before, at once: the migration's lock is
    not looked at (here another holds it, with a fresh note), nothing sleeps, and no lock file is
    made."""
    caplog.set_level(logging.INFO, MIGRATION_LOG)
    slept: list[float] = []
    monkeypatch.setattr(migrations_module, "_sleep", slept.append)
    path = tmp_path / DB_NAME
    began = time.monotonic()
    opened(path).close()  # (new)
    opened(path).close()  # (at its version)
    alone = time.monotonic() - began
    assert not (tmp_path / MIGRATE_LOCK_NAME).exists(), "no lock file for a start with nothing to migrate"
    lock = InstanceLock(tmp_path, MIGRATE_LOCK_NAME)
    lock.acquire()
    note = MigratingNote(tmp_path, beat_sec=0.05)
    note.start()
    try:
        began = time.monotonic()
        for _ in range(2):
            opened(path).close()
        beside = time.monotonic() - began
    finally:
        note.stop()
        lock.release()
    assert slept == [] and said(caplog, WAITS) == 0
    # (no bound on the first two: making a new file is the machine's time, 3.6 s on a Windows
    # machine busy with the whole suite. The two beside a held lock are bounded by what a wait would
    # cost: one that waited would stand until the lock is let go, which this test does only after
    # them)
    assert beside < 30.0, (alone, beside)
