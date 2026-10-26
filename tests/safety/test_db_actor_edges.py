"""The Db actor (neoaprs/db.py, dbthread.py) at its edges: a start that is cancelled while the file is opened, a Db that was never started, a thread that dies in the middle of its queue, a rollback that
fails, a function that ends its own transaction, an answer for a loop that is gone, the size of a batch and an append that cannot be made again and again. The thread goes on, or ends with
everything that was asked answered."""
import asyncio
import logging
import sqlite3
import threading
from pathlib import Path

import pytest

from neoaprs.db import Db, _post
from neoaprs.dberror import DbClosed, DbError
from neoaprs.dbstats import DbStats
from neoaprs.dbthread import DbThread, Kind, Op, Tuning
from tests.support.dbactor import QUICK, THREAD_PREFIX, committed, fast_connection, started, wait_gone
from tests.support.env import until
from tests.support.riggedsql import fails_at


def rigged_opener(path: Path, *rules: object):  # type: ignore[no-untyped-def]
    """An opener whose connection raises ahead of the statements the rules name (tests/support/riggedsql.py: `fails_at`)."""
    def opener() -> sqlite3.Connection:
        class Rigged(sqlite3.Connection):
            def execute(self, sql: str, *args: object) -> sqlite3.Cursor:
                for rule in rules:
                    rule(self, sql)  # type: ignore[operator]
                return super().execute(sql, *args)  # type: ignore[arg-type]

        conn = sqlite3.connect(str(path), isolation_level=None, timeout=5, factory=Rigged)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        return conn

    return opener


# ---- starting and closing
async def test_a_start_that_is_cancelled_while_the_file_is_opened_leaves_a_db_that_is_closed_and_a_thread_that_ends(tmp_path: Path) -> None:
    inside, release = threading.Event(), threading.Event()

    def opener() -> sqlite3.Connection:
        inside.set()
        release.wait(10)                                                           # a migration that takes its time
        return fast_connection(tmp_path / "x.sqlite")

    db = Db(opener, name=THREAD_PREFIX + "-cancelled")
    starting = asyncio.ensure_future(db.start())
    await until(inside.is_set)
    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting
    assert not db.is_open
    release.set()
    await db.close()                                                               # waits for the thread, which opens the file, finds the queue closed and ends
    assert wait_gone(1.0) == []
    with pytest.raises(DbClosed):
        await db.read(lambda conn: 1)


async def test_a_db_that_was_never_started_closes_and_stays_closed() -> None:
    db = Db(lambda: sqlite3.connect(":memory:", isolation_level=None), name=THREAD_PREFIX + "-never")
    await db.close()
    assert not db.is_open
    with pytest.raises(DbClosed):
        await db.write(lambda conn: None)
    assert db.write_nowait(lambda conn: None) is False and db.stats()["dropped"] == 1
    assert wait_gone(0.05) == []


async def test_a_message_for_a_loop_that_is_gone_or_a_future_that_is_settled_is_dropped_quietly() -> None:
    loop = asyncio.get_running_loop()
    seen: list[dict[str, object]] = []
    loop.set_exception_handler(lambda loop, context: seen.append(context))
    settled: asyncio.Future[None] = loop.create_future()
    settled.set_result(None)
    _post(loop, settled, RuntimeError("late"))                                     # an error for a future that has its answer
    await asyncio.sleep(0)
    gone = asyncio.new_event_loop()
    future = gone.create_future()
    gone.close()
    _post(gone, future, None)                                                      # the loop of the answer is closed
    assert seen == [] and settled.result() is None and not future.done()


# ---- the thread's answers
def test_an_answer_for_a_closed_loop_and_for_an_append_is_dropped_without_a_word() -> None:
    thread = DbThread(lambda: sqlite3.connect(":memory:", isolation_level=None), Tuning(), DbStats(), lambda e: None, lambda: None, THREAD_PREFIX + "-unit")
    gone = asyncio.new_event_loop()
    future = gone.create_future()
    gone.close()
    thread._reply(Op(Kind.READ, None, 0.0, future, gone), 1, None)
    thread._reply(Op(Kind.APPEND, None, 0.0), None, None)
    assert not future.done()
    assert wait_gone(0.05) == []


# ---- a rollback that fails
@pytest.mark.expects_errors
async def test_a_rollback_that_fails_once_is_told_and_the_next_operation_starts_clean(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path, rigged_opener(path, fails_at("ROLLBACK", sqlite3.OperationalError("disk I/O error"), times=1)))

    def writes_and_fails(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO t VALUES (1, 'a')")
        raise KeyError("the function failed")

    with pytest.raises(KeyError):
        await db.write(writes_and_fails)
    assert any("could not be rolled back: disk I/O error" in r.getMessage() for r in caplog.records)
    assert await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (2, 'b')").rowcount) == 1
    assert committed(path) == [2], "what the failed write did was undone by the next operation's own rollback, and the next write is whole"
    await db.close()


@pytest.mark.expects_errors
async def test_a_rollback_that_keeps_failing_is_told_again_when_the_thread_closes_and_close_still_returns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path, rigged_opener(path, fails_at("ROLLBACK", sqlite3.OperationalError("disk I/O error"))))
    with pytest.raises(KeyError):
        await db.write(lambda conn: (conn.execute("INSERT INTO t VALUES (1, 'a')"), (_ for _ in ()).throw(KeyError("no")))[0])
    await db.close()
    messages = [r.getMessage() for r in caplog.records]
    assert any("could not be rolled back" in m for m in messages) and any("could not be closed cleanly: disk I/O error" in m for m in messages)
    assert wait_gone(1.0) == []
    assert committed(path) == []


@pytest.mark.expects_errors
async def test_a_transaction_that_a_rollback_left_open_is_rolled_back_when_the_thread_closes(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    opener = rigged_opener(path, fails_at("ROLLBACK", sqlite3.OperationalError("disk I/O error"), times=1))
    db = await started(path, opener)
    with pytest.raises(KeyError):
        await db.write(lambda conn: (conn.execute("INSERT INTO t VALUES (1, 'a')"), (_ for _ in ()).throw(KeyError("no")))[0])
    await db.close()
    assert wait_gone(1.0) == [] and committed(path) == []


async def test_a_function_that_ends_its_own_transaction_is_told_so_and_what_it_did_is_gone(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path)
    await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'kept')"))

    def ends_it(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO t VALUES (2, 'lost')")
        try:
            conn.execute("INSERT OR ROLLBACK INTO t VALUES (1, 'again')")           # a conflict that rolls the whole transaction back, which the function swallows
        except sqlite3.IntegrityError:
            pass

    with pytest.raises(DbError, match="ended its transaction itself"):
        await db.write(ends_it)
    assert committed(path) == [1]
    assert await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (3, 'after')").rowcount) == 1
    assert committed(path) == [1, 3]
    await db.close()


# ---- appends
async def test_appends_are_committed_in_batches_of_at_most_batch_max_and_none_is_lost(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path, tuning=Tuning(tick=30.0, batch_max=2))                  # a batch ends when it is full or when something else is asked, never by waiting out the tick
    for n in range(5):
        assert db.write_nowait(lambda conn, n=n: conn.execute("INSERT INTO t VALUES (?, 'x')", (n,)))
    await db.barrier()
    assert committed(path) == [0, 1, 2, 3, 4]
    assert db.stats()["batches"] == 3, "2, 2 and 1"
    await db.close()


@pytest.mark.expects_errors
async def test_an_append_that_fails_again_and_again_is_dropped_each_time_and_told_in_the_log_only_the_first_time(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path, tuning=QUICK)
    await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'a')"))
    for _ in range(3):
        db.write_nowait(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'twice')"))
    db.write_nowait(lambda conn: conn.execute("INSERT INTO t VALUES (2, 'b')"))
    await db.barrier()
    assert db.stats()["poisoned"] == 3 and committed(path) == [1, 2]
    told = [r for r in caplog.records if "an append to the database failed" in r.getMessage()]
    assert len(told) == 1 and logging.ERROR == told[0].levelno
    await db.close()

