"""The Db actor (neoaprs/db.py): life and what it measures. A clean shutdown does everything that was asked (what was acknowledged is on the disk, the last batch of appends too) and does
not wait for a tick; nothing is asked of a closed Db; its thread ends and none is left behind; a backup and a checkpoint are made by the same thread, between the other
operations; the commits are synced to the disk; the queue wait, the run time and the stall of the loop are numbers."""
import asyncio
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from neoaprs.db import Db, DbClosed, StoreError
from neoaprs.dbthread import Tuning
from tests.support.env import until
from tests.support.ptyline import posix_only
from tests.support.dbactor import (THREAD_PREFIX, committed, db_threads, eager, started, wait_gone)
from tests.conftest import ROOT
from tests.support.safety import raw


# ---- shutdown
async def test_a_clean_shutdown_does_everything_that_was_asked_and_does_not_wait_for_the_tick(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path, tuning=Tuning(tick=60.0))
    awaited = [eager(db.write(lambda conn, n=n: conn.execute("INSERT INTO t VALUES (?, 'w')", (n,)))) for n in range(20)]
    for n in range(100, 400):
        assert db.write_nowait(lambda conn, n=n: conn.execute("INSERT INTO t VALUES (?, 'a')", (n,)))
    began = time.monotonic()
    await db.close()
    assert time.monotonic() - began < 30, "the shutdown waited for the tick (60 s); a loaded machine takes a few seconds for the 300 appends and their syncs"
    answers = await asyncio.wait_for(asyncio.gather(*awaited, return_exceptions=True), 30)       # the answers are put on the loop by the thread; the tasks that wait for them wake up a turn after close() returns
    assert not [a for a in answers if isinstance(a, BaseException)], "an operation that was asked before the shutdown has its answer"
    assert committed(path) == list(range(20)) + list(range(100, 400)), "the last batch of appends is in"
    assert db_threads() == []


async def test_what_was_acknowledged_is_on_the_disk_without_a_close(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path)
    await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'acknowledged')"))
    assert committed(path) == [1], "a reader that is not the Db sees it as soon as the write has returned"
    await db.close()


async def test_asking_a_closed_db_is_the_database_not_being_open(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    await db.close()
    assert not db.is_open
    for ask in (db.read, db.write, db.maintain):
        with pytest.raises(DbClosed, match="the database is not open") as caught:
            await ask(lambda conn: 1)
        assert isinstance(caught.value, StoreError), "what catches the StoreError of the Store catches this"
    assert db.write_nowait(lambda conn: None) is False
    assert db.stats()["dropped"] == 1
    await db.close()                                                              # and closing again is harmless


async def test_two_closes_at_once_both_return_when_the_thread_has_ended(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    await asyncio.gather(db.close(), db.close())
    assert db_threads() == []


async def test_asking_while_the_shutdown_is_under_way_is_refused_not_lost(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    inside, release = threading.Event(), threading.Event()
    blocker = asyncio.ensure_future(db.write(lambda conn: (inside.set(), release.wait(10))))
    await until(inside.is_set)
    closing = asyncio.ensure_future(db.close())
    await asyncio.sleep(0.01)
    with pytest.raises(DbClosed):
        await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'too late')"))
    release.set()
    await asyncio.gather(blocker, closing)
    assert committed(tmp_path / "x.sqlite") == []


async def test_a_write_on_the_queue_when_the_db_closes_is_committed_though_its_asker_was_cancelled(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The daemon's stop: the tasks are cancelled first (a message's write among them, queued behind a busy thread), the database closed last; the drain of close() writes it."""
    path = tmp_path / "x.sqlite"
    db = await started(path)
    inside, release = threading.Event(), threading.Event()
    blocker = asyncio.ensure_future(db.write(lambda conn: (inside.set(), release.wait(10))))
    await until(inside.is_set)
    cut = asyncio.ensure_future(db.write(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'a message')")))
    await asyncio.sleep(0.01)
    cut.cancel()
    closing = asyncio.ensure_future(db.close())
    await asyncio.sleep(0.01)
    release.set()
    await asyncio.gather(blocker, closing)
    assert cut.cancelled()
    assert committed(path) == [1], "the write was on the queue when the stop came: it is in the file"
    assert db.stats()["cut"] == 1 and db.stats()["withdrawn"] == 0
    assert any("asker was cancelled" in r.getMessage() and "is committed" in r.getMessage() for r in caplog.records)


async def test_a_stop_while_another_process_holds_the_lock_tries_the_batch_once_and_ends_inside_the_units_timeout(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A tool left in BEGIN IMMEDIATE during `systemctl restart`: three attempts with the busy time of 3 s would take 10.5 s, past TimeoutStopSec=10, and the unit would kill the stop. While the
    queue closes a batch is tried once (the STOP stands behind it; the lock is another process's), so the stop takes one busy wait, plus one for each awaited write still queued.
    Here with a busy time of 100 ms and the retry waits of the daemon (0.5 s, then 1 s): three attempts would take 1.8 s."""
    path = tmp_path / "x.sqlite"
    first = await started(path)
    await first.close()
    held = raw(path)
    held.execute("BEGIN IMMEDIATE")
    try:
        db = Db.at(path, busy_ms=100, name=THREAD_PREFIX + "-locked", tuning=Tuning(tick=0.02, retry_sec=0.5))
        await db.start()
        assert db.write_nowait(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'an event')"))
        awaited = eager(db.write(lambda conn: conn.execute("INSERT INTO t VALUES (2, 'a message')")))
        began = time.monotonic()
        await db.close()
        took = time.monotonic() - began
        assert took < 1.0, f"the stop took {took:.2f} s: the batch was tried again behind a lock the stop cannot hurry"
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            await awaited                                                                 # the awaited write had its own busy wait and its own answer: nothing is silent
        stats: Any = db.stats()
        assert stats["lost"] == 1 and stats["retried"] == 0 and stats["batches"] == 0
        assert [r.getMessage() for r in caplog.records if "could not commit" in r.getMessage()] == ["the database could not commit 1 appends (database is locked): they are lost (the database is closing: no second attempt)"]
    finally:
        held.execute("ROLLBACK")
        held.close()
    assert committed(path) == []


# ---- no thread is left
async def test_the_thread_ends_with_close_and_is_named_after_the_db(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    assert [t.name for t in db_threads()] == [THREAD_PREFIX + "-test"]
    assert db_threads()[0].daemon, "a program that forgot close() still ends"
    await db.close()
    assert wait_gone(1.0) == []


async def test_the_leak_guard_sees_a_thread_that_is_left_running(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    assert len(wait_gone(0.05)) == 1, "the guard would fail a test that ended here"
    await db.close()
    assert wait_gone(1.0) == []


async def test_a_refused_start_leaves_no_thread(tmp_path: Path) -> None:
    db = Db.at(tmp_path / "no-such-folder" / "x.sqlite", name=THREAD_PREFIX + "-nofolder")
    with pytest.raises(sqlite3.OperationalError):
        await db.start()
    assert wait_gone(1.0) == []


# ---- the sync to the disk
async def test_the_connection_is_the_one_of_the_daemon(tmp_path: Path) -> None:
    db = Db.at(tmp_path / "x.sqlite", busy_ms=1234, name=THREAD_PREFIX + "-pragmas")
    await db.start()

    def look(conn: sqlite3.Connection) -> list[Any]:
        return [conn.execute(f"PRAGMA {p}").fetchone()[0] for p in ("journal_mode", "synchronous", "busy_timeout")]

    assert await db.read(look) == ["wal", 2, 1234], "WAL, synchronous=FULL (an acknowledged write is on the disk), the busy time"
    await db.close()


def strace_works() -> bool:
    if not shutil.which("strace"):
        return False
    return subprocess.run(["strace", "-o", "/dev/null", "true"], capture_output=True, timeout=30).returncode == 0


def acknowledged_without_sync(tmp_path: Path, count: int, synchronous: str) -> list[int]:
    """The numbers of the writes that returned with no fsync/fdatasync of the WAL or the database since the one before (the probe: tests/support/db_sync_probe.py)."""
    trace = tmp_path / "trace.txt"
    run = subprocess.run(["strace", "-f", "-y", "-e", "trace=fsync,fdatasync,write", "-e", "write=2", "-o", str(trace), sys.executable, "-c",
                          "from tests.support.db_sync_probe import main; main()", str(tmp_path / "neoaprs.sqlite"), str(count), synchronous], cwd=ROOT, capture_output=True, timeout=120)
    assert run.returncode == 0, run.stderr
    unsynced: list[int] = []
    synced = False
    for line in trace.read_text(encoding="utf-8").splitlines():
        if re.search(r"f(data)?sync\(\d+<[^>]*neoaprs\.sqlite(-wal)?>\)\s+= 0", line):
            synced = True
        elif re.search(r'write\(2<[^>]*>, "READY\\n"', line):
            synced = False
        elif m := re.search(r'write\(2<[^>]*>, "ACK (\d+)\\n"', line):
            if not synced:
                unsynced.append(int(m.group(1)))
            synced = False
    return unsynced


@pytest.mark.skipif(not strace_works(), reason="strace is not available (or not allowed to trace): the pragma is held by test_the_connection_is_the_one_of_the_daemon")
def test_a_write_is_synced_to_the_disk_before_it_returns(tmp_path: Path) -> None:
    assert acknowledged_without_sync(tmp_path, 20, "FULL") == []


@pytest.mark.skipif(not strace_works(), reason="strace is not available (or not allowed to trace)")
def test_the_probe_can_tell_a_synced_commit_from_an_unsynced_one(tmp_path: Path) -> None:
    """The test above would pass for a probe that sees nothing: with NORMAL the same probe sees writes acknowledged with no sync."""
    assert len(acknowledged_without_sync(tmp_path, 20, "NORMAL")) >= 15


async def test_a_backup_sees_every_write_asked_before_it_and_is_whole_and_private(tmp_path: Path) -> None:
    path, dest = tmp_path / "x.sqlite", tmp_path / "backup" / "copy.sqlite"
    db = await started(path)
    for n in range(50):
        await db.write(lambda conn, n=n: conn.execute("INSERT INTO t VALUES (?, 'x')", (n,)))
    db.write_nowait(lambda conn: conn.execute("INSERT INTO t VALUES (100, 'append')"))               # an append before the backup is in the copy: the queue is in order
    await db.backup(dest)
    assert committed(dest) == list(range(50)) + [100]
    if sys.platform != "win32":
        assert (dest.stat().st_mode & 0o777) == 0o600
    assert sorted(p.name for p in dest.parent.iterdir()) == ["copy.sqlite"], "no temporary file, no journal"
    c = raw(dest)
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    c.close()
    await db.close()


@posix_only      # (the descriptors are turned into paths through /proc)
async def test_a_backup_is_synced_before_it_has_its_name_and_its_folder_after(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = await started(tmp_path / "x.sqlite")
    dest = tmp_path / "backup" / "copy.sqlite"
    synced: list[str] = []
    before_rename: list[list[str]] = []
    real_fsync, real_replace = os.fsync, Path.replace

    def fsync(fd: int) -> None:
        try:
            synced.append(os.readlink(f"/proc/self/fd/{fd}"))
        except OSError:
            pass
        real_fsync(fd)

    def replace(self: Path, target: Any) -> Path:
        before_rename.append(list(synced))
        return real_replace(self, target)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(Path, "replace", replace)
    await db.backup(dest)
    monkeypatch.undo()
    assert any(p.endswith(".tmp") for p in before_rename[0]), f"the copy was renamed before it was synced ({before_rename})"
    assert str(dest.parent) in synced, "the folder was not synced after the rename"
    await db.close()


async def test_a_backup_that_fails_raises_and_leaves_nothing_and_the_db_goes_on(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    blocked = tmp_path / "backup"
    blocked.write_text("a file where the folder should be")
    with pytest.raises(OSError):
        await db.backup(blocked / "copy.sqlite")
    await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'x')"))
    assert committed(tmp_path / "x.sqlite") == [1]
    await db.close()


async def test_copies_taken_while_writes_go_on_are_whole_and_each_holds_what_was_acknowledged_before_it(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path)
    acked: list[int] = []

    async def writer() -> None:
        n = 0
        while True:
            await db.write(lambda conn, n=n: conn.execute("INSERT INTO t VALUES (?, 'x')", (n,)))
            acked.append(n)
            n += 1

    task = asyncio.ensure_future(writer())
    copies = []
    for i in range(8):
        await asyncio.sleep(0.02)
        low = len(acked)
        dest = tmp_path / f"copy-{i}.sqlite"
        await db.backup(dest)
        copies.append((dest, low, len(acked)))
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await db.close()
    for dest, low, high in copies:
        numbers = committed(dest)
        assert numbers == list(range(len(numbers))), "a copy holds a prefix of the writes"
        assert low <= len(numbers) <= high + 1, (low, len(numbers), high)


async def test_a_checkpoint_moves_the_log_into_the_file(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path)
    for n in range(30):
        await db.write(lambda conn, n=n: conn.execute("INSERT INTO t VALUES (?, ?)", (n, "x" * 500)))
    wal = Path(str(path) + "-wal")
    assert wal.stat().st_size > 0
    busy, _, _ = await db.checkpoint("TRUNCATE")
    assert busy == 0 and wal.stat().st_size == 0
    assert len(committed(path)) == 30
    with pytest.raises(ValueError):
        await db.checkpoint("DROP TABLE t")
    await db.close()


# ---- what it measures
async def test_the_wait_in_the_queue_and_the_run_time_are_measured(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    inside = threading.Event()
    slow = asyncio.ensure_future(db.write(lambda conn: (inside.set(), time.sleep(0.12))))
    await until(inside.is_set)
    await db.read(lambda conn: 1)                                                  # asked while the slow one runs: it waits for the rest of it
    await slow
    stats: Any = db.stats()
    assert stats["run"]["max_ms"] >= 100, stats["run"]
    assert stats["queue_wait"]["max_ms"] >= 80, stats["queue_wait"]
    assert stats["queue_wait"]["p50_ms"] < 50 and stats["reads"] == 1 and stats["writes"] >= 2
    assert stats["max_depth"] >= 1
    await db.close()


async def test_the_stall_of_the_event_loop_is_measured_as_the_time_an_answer_waited_for_it(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    pending = eager(db.read(lambda conn: 1))
    time.sleep(0.15)                                                              # the loop is held: the answer is ready in a millisecond and waits for it
    await pending
    stats: Any = db.stats()
    assert stats["loop_delivery"]["max_ms"] >= 100, stats["loop_delivery"]
    await db.close()


async def test_an_operation_that_runs_long_is_told_in_the_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    db = await started(tmp_path / "x.sqlite", tuning=Tuning(tick=0.01, slow_sec=0.15))
    try:
        await db.read(lambda conn: time.sleep(0.3))
        await db.read(lambda conn: 1)                                              # (quick, but a busy machine may hold it past slow_sec too: the count is at least one)
        told = [float(m.group(1)) for r in caplog.records if (m := re.search(r"ran for ([\d.]+) s", r.getMessage()))]
        assert told and max(told) >= 0.15 and db.stats()["slow"] >= 1, (told, db.stats()["slow"])   # (told while it still runs: past slow_sec, not necessarily its whole 0.3 s)
    finally:
        await db.close()
