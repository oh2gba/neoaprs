"""The Db actor (neoaprs/db.py): faults. A write is all of it or none, with a statement failing at every place it can (the first BEGIN, each statement, the COMMIT); the error reaches
the one who waits as it was raised; an append that cannot be made is undone alone, a batch that cannot be committed is rolled back whole and tried again; the queue of appends
is bounded and says no instead of growing; the thread goes on after all of it."""
import asyncio
import sqlite3
import threading
from pathlib import Path

import pytest

from neoaprs.dbthread import Tuning
from tests.support.dbactor import (QUICK, Injected, arm, committed, faulty_connection,
                                   started)


def three_statements(n: int):  # type: ignore[no-untyped-def]
    def write(conn: sqlite3.Connection) -> int:
        conn.execute("INSERT INTO t VALUES (?, 'a')", (n,))
        conn.execute("INSERT INTO pair VALUES (?, 0)", (n,))
        conn.execute("UPDATE t SET v = 'b' WHERE n = ?", (n,))
        return n
    return write


# BEGIN, three statements, COMMIT: five that the thread issues; the sixth is one that does not exist
@pytest.mark.parametrize("fail_at", [1, 2, 3, 4, 5, 6])
async def test_a_write_with_a_statement_failing_at_every_place_is_all_of_it_or_none(tmp_path: Path, fail_at: int) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path, lambda: faulty_connection(path))
    await db.maintain(lambda conn: arm(conn, fail_at))
    if fail_at <= 5:
        with pytest.raises(Injected):
            await db.write(three_statements(1))
        assert committed(path) == [] and committed(path, "SELECT n FROM pair") == [], "a write that failed left half of itself"
    else:
        assert await db.write(three_statements(1)) == 1
        assert committed(path) == [1] and committed(path, "SELECT n FROM pair") == [1]
        assert committed(path, "SELECT v FROM t") == ["b"]
    await db.maintain(lambda conn: arm(conn, None))
    assert await db.write(three_statements(2)) == 2, "the thread goes on after a failed write"
    assert committed(path, "SELECT n FROM pair ORDER BY n")[-1] == 2
    await db.close()


async def test_a_disk_that_stays_full_fails_every_write_and_none_leaves_anything(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path, lambda: faulty_connection(path))
    await db.maintain(lambda conn: arm(conn, 2, sticky=True))
    for n in range(5):
        with pytest.raises(Injected):
            await db.write(three_statements(n))
    assert committed(path) == []
    await db.maintain(lambda conn: arm(conn, None))
    await db.write(three_statements(9))
    assert committed(path) == [9]
    await db.close()


async def test_the_error_of_a_statement_reaches_the_caller_as_it_was_raised(tmp_path: Path) -> None:
    """IntegrityError stays an IntegrityError: the code that handles a constraint error from a direct execute handles it the same."""
    db = await started(tmp_path / "x.sqlite")
    await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'a')"))

    def duplicate(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO t VALUES (2, 'b')")
        conn.execute("INSERT INTO t VALUES (1, 'again')")

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed: t.n"):
        await db.write(duplicate)
    assert committed(tmp_path / "x.sqlite") == [1], "the first statement of the failed write is not kept"

    class Mine(Exception):
        pass

    def raises(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO t VALUES (3, 'c')")
        raise Mine("not a database error")

    with pytest.raises(Mine, match="not a database error"):
        await db.write(raises)
    assert committed(tmp_path / "x.sqlite") == [1]
    assert db.stats()["errors"] == 2
    await db.close()


# ---- appends
# BEGIN, then SAVEPOINT / INSERT / RELEASE for each of the three appends, COMMIT: eleven statements; the twelfth does not exist
@pytest.mark.parametrize("fail_at", range(1, 13))
async def test_a_batch_of_appends_with_a_statement_failing_at_every_place_is_in_exactly_once(tmp_path: Path, fail_at: int) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path, lambda: faulty_connection(path), QUICK)
    await db.maintain(lambda conn: arm(conn, fail_at))
    for n in (1, 2, 3):
        assert db.write_nowait(lambda conn, n=n: conn.execute("INSERT INTO t VALUES (?, 'x')", (n,)))
    await db.barrier()
    assert committed(path) == [1, 2, 3], "a batch that failed once is rolled back whole and made again: all of it, once"
    assert db.stats()["retried"] == (1 if fail_at <= 11 else 0)
    await db.close()


@pytest.mark.expects_errors
async def test_a_batch_that_cannot_be_committed_is_dropped_whole_after_its_attempts_and_the_thread_goes_on(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path, lambda: faulty_connection(path), Tuning(tick=0.01, retry_sec=0.001, attempts=3))
    await db.maintain(lambda conn: arm(conn, 3, sticky=True))                  # the disk is full from the second append on
    for n in (1, 2, 3):
        db.write_nowait(lambda conn, n=n: conn.execute("INSERT INTO t VALUES (?, 'x')", (n,)))
    await db.barrier()
    assert committed(path) == [], "not the first append alone: the batch is all of it or none"
    stats = db.stats()
    assert stats["lost"] == 3 and stats["retried"] == 2, "three attempts: two of them were retries"
    await db.maintain(lambda conn: arm(conn, None))
    assert db.write_nowait(lambda conn: conn.execute("INSERT INTO t VALUES (4, 'x')"))
    await db.barrier()
    assert committed(path) == [4]
    await db.close()


@pytest.mark.expects_errors
async def test_an_append_that_fails_for_its_own_reasons_is_undone_alone(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path)

    def two_statements(n: int, twice: bool):  # type: ignore[no-untyped-def]
        def append(conn: sqlite3.Connection) -> None:
            conn.execute("INSERT INTO pair VALUES (?, 0)", (n,))
            conn.execute("INSERT INTO t VALUES (?, 'x')", (n,))
            if twice:
                conn.execute("INSERT INTO t VALUES (?, 'again')", (n,))               # the constraint: this append cannot be made
        return append

    db.write_nowait(two_statements(1, False))
    db.write_nowait(two_statements(2, True))
    db.write_nowait(two_statements(3, False))
    await db.barrier()
    assert committed(path) == [1, 3] and committed(path, "SELECT n FROM pair ORDER BY n") == [1, 3], "the failed append left nothing, its neighbours are in"
    assert db.stats()["poisoned"] == 1 and db.stats()["retried"] == 0
    await db.close()


# ---- the queue of appends is bounded
@pytest.mark.expects_errors
async def test_a_full_queue_of_appends_says_no_and_keeps_what_it_has(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path, tuning=Tuning(tick=0.01, max_appends=50))
    inside, release = threading.Event(), threading.Event()

    def hold(conn: sqlite3.Connection) -> None:
        inside.set()
        release.wait(10)

    blocker = asyncio.ensure_future(db.write(hold))
    while not inside.is_set():
        await asyncio.sleep(0.002)
    answers = [db.write_nowait(lambda conn, n=n: conn.execute("INSERT INTO t VALUES (?, 'x')", (n,))) for n in range(80)]
    assert answers == [True] * 50 + [False] * 30, "the first 50 are queued, the rest are refused at once (the producer is never made to wait)"
    waiting = asyncio.ensure_future(db.write(lambda conn: conn.execute("INSERT INTO t VALUES (1000, 'awaited')")))            # an awaited operation is never refused
    assert db.stats()["dropped"] == 30
    release.set()
    await asyncio.gather(blocker, waiting)
    await db.barrier()
    assert committed(path) == list(range(50)) + [1000], "the oldest are kept: the order is the order of asking, with no hole"
    assert db.write_nowait(lambda conn: conn.execute("INSERT INTO t VALUES (2000, 'x')")), "and it takes appends again once it has caught up"
    await db.close()
    assert committed(path)[-1] == 2000


@pytest.mark.expects_errors
async def test_the_refusals_are_told_in_the_log_not_every_time(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    db = await started(tmp_path / "x.sqlite", tuning=Tuning(tick=0.01, max_appends=1))
    inside, release = threading.Event(), threading.Event()
    blocker = asyncio.ensure_future(db.write(lambda conn: (inside.set(), release.wait(10))))
    while not inside.is_set():
        await asyncio.sleep(0.002)
    for _ in range(121):
        db.write_nowait(lambda conn: None)
    release.set()
    await blocker
    told = [r for r in caplog.records if "is full" in r.getMessage()]
    assert len(told) == 3, "the first, the tenth and the hundredth refusal (of 120)"
    await db.close()
