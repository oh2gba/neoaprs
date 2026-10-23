"""The Db actor (neoaprs/db.py): order. One connection, one thread, one FIFO queue: what was asked first is done first, whatever kind it is and however many tasks ask,
and a read sees every write asked before it, with nothing to flush. Also: what a function run by the thread may and may not do."""
import asyncio
import random
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from neoaprs.db import Db, DbClosed, DbError, NestedUse, StoreError
from neoaprs.dbthread import Tuning
from tests.support.env import until
from tests.support.dbactor import QUICK, THREAD_PREFIX, committed, eager, fast_connection, started


async def test_a_read_sees_every_write_asked_before_it(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    for n in range(100):
        await db.write(lambda conn, n=n: conn.execute("INSERT INTO t VALUES (?, 'x')", (n,)))
        assert await db.read(lambda conn: conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]) == n + 1
    await db.close()


async def test_operations_of_many_tasks_are_done_in_the_order_they_were_asked(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    done: list[int] = []

    def mark(i: int) -> None:
        done.append(i)

    async def one(i: int) -> None:
        kind = i % 3
        if kind == 0:
            await db.write(lambda conn: mark(i))
        elif kind == 1:
            await db.read(lambda conn: mark(i))
        else:
            await db.maintain(lambda conn: mark(i))

    tasks = [eager(one(i)) for i in range(300)]
    await asyncio.gather(*tasks)
    assert done == list(range(300))
    await db.close()


async def test_appends_are_in_the_order_they_were_made_and_before_what_is_asked_after_them(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite", tuning=Tuning(tick=30.0))        # a tick as long as the test: nothing may wait for it
    began = time.monotonic()
    for n in range(100):
        assert db.write_nowait(lambda conn, n=n: conn.execute("INSERT INTO t VALUES (?, 'a')", (n,)))
    assert await db.read(lambda conn: conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]) == 100            # the read ends the collecting: it sees all of them
    await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (100, 'w')"))
    db.write_nowait(lambda conn: conn.execute("UPDATE t SET v = 'late' WHERE n = 100"))
    assert await db.read(lambda conn: conn.execute("SELECT v FROM t WHERE n = 100").fetchone()[0]) == "late"      # an append after a write is after it
    assert time.monotonic() - began < 5.0
    await db.close()
    assert committed(tmp_path / "x.sqlite") == list(range(101))


async def test_ten_thousand_mixed_operations_agree_with_a_model(tmp_path: Path) -> None:
    """Random inserts, replacements, updates, deletes (awaited and appended) and reads, asked in bursts of tasks, against a dictionary that is changed in the order of asking."""
    path = tmp_path / "x.sqlite"
    db = Db(lambda: fast_connection(path), tuning=QUICK, name=THREAD_PREFIX + "-model")
    await db.start()
    await db.write(lambda conn: conn.execute("CREATE TABLE t (n INTEGER PRIMARY KEY, v TEXT NOT NULL)"))
    rng = random.Random(20261011)
    model: dict[int, str] = {}
    answers: list[tuple[object, object]] = []
    pending: list[asyncio.Future[object]] = []

    def expect(got: asyncio.Future[object], want: object) -> None:
        got.add_done_callback(lambda f: answers.append((f.result(), want)))

    for i in range(10_000):
        n, v = rng.randrange(300), f"v{i}"
        pick = rng.random()
        if pick < 0.25:
            model[n] = v
            pending.append(eager(db.write(lambda conn, n=n, v=v: conn.execute("INSERT OR REPLACE INTO t VALUES (?, ?)", (n, v)))))
        elif pick < 0.45:
            model[n] = v
            assert db.write_nowait(lambda conn, n=n, v=v: conn.execute("INSERT OR REPLACE INTO t VALUES (?, ?)", (n, v)))
        elif pick < 0.55:
            model = {k: x for k, x in model.items() if k != n}
            pending.append(eager(db.write(lambda conn, n=n: conn.execute("DELETE FROM t WHERE n = ?", (n,)))))
        elif pick < 0.65:
            model = {k: (v if k == n else x) for k, x in model.items()}
            db.write_nowait(lambda conn, n=n, v=v: conn.execute("UPDATE t SET v = ? WHERE n = ?", (v, n)))
        elif pick < 0.85:
            want = model.get(n)
            fut = eager(db.read(lambda conn, n=n: (r := conn.execute("SELECT v FROM t WHERE n = ?", (n,)).fetchone()) and r[0]))
            expect(fut, want)
            pending.append(fut)
        else:
            want = dict(model)
            fut = eager(db.read(lambda conn: dict(conn.execute("SELECT n, v FROM t").fetchall())))
            expect(fut, want)
            pending.append(fut)
        if i % 250 == 249:
            await asyncio.gather(*pending)
            pending.clear()
    await asyncio.gather(*pending)
    await db.close()
    assert len(answers) > 3000
    wrong = [(got, want) for got, want in answers if (got or None) != (want or None)]
    assert not wrong, wrong[:3]
    assert dict(committed(path, "SELECT n, v FROM t")) == model


async def test_an_await_cancelled_before_the_thread_began_it_withdraws_a_read(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    inside, release = threading.Event(), threading.Event()
    ran: list[int] = []

    def hold(conn: sqlite3.Connection) -> None:
        inside.set()
        release.wait(5)

    blocker = asyncio.ensure_future(db.write(hold))
    await until(inside.is_set)
    withdrawn = asyncio.ensure_future(db.read(lambda conn: ran.append(1)))
    await asyncio.sleep(0.01)
    withdrawn.cancel()
    release.set()
    await blocker
    with pytest.raises(asyncio.CancelledError):
        await withdrawn
    await db.barrier()
    assert ran == [] and db.stats()["withdrawn"] == 1
    await db.close()


async def test_a_write_whose_await_is_cancelled_before_the_thread_began_it_is_still_committed(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A write is never withdrawn: the daemon's stop cancels the task that carries a message of the radio or of the page, and the message must not go with it.
    The asker is cancelled all the same, and the outcome it never saw is in the log."""
    db = await started(tmp_path / "x.sqlite")
    inside, release = threading.Event(), threading.Event()

    def hold(conn: sqlite3.Connection) -> None:
        inside.set()
        release.wait(5)

    blocker = asyncio.ensure_future(db.write(hold))
    await until(inside.is_set)
    cut = asyncio.ensure_future(db.write(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'kept')")))
    await asyncio.sleep(0.01)
    cut.cancel()
    release.set()
    await blocker
    with pytest.raises(asyncio.CancelledError):
        await cut
    await db.barrier()
    assert committed(tmp_path / "x.sqlite") == [1]
    assert db.stats()["withdrawn"] == 0 and db.stats()["cut"] == 1
    assert [r.levelname for r in caplog.records if "asker was cancelled" in r.getMessage() and "is committed" in r.getMessage()] == ["WARNING"]
    await db.close()


async def test_a_cut_off_write_that_fails_says_so_in_the_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    db = await started(tmp_path / "x.sqlite")
    inside, release = threading.Event(), threading.Event()
    blocker = asyncio.ensure_future(db.write(lambda conn: (inside.set(), release.wait(5))))
    await until(inside.is_set)
    cut = asyncio.ensure_future(db.write(lambda conn: conn.execute("INSERT INTO no_such_table VALUES (1)")))
    await asyncio.sleep(0.01)
    cut.cancel()
    release.set()
    await blocker
    with pytest.raises(asyncio.CancelledError):
        await cut
    await db.barrier()
    assert [r.levelname for r in caplog.records if "asker was cancelled" in r.getMessage() and "no such table" in r.getMessage()] == ["ERROR"]
    assert db.stats()["cut"] == 1
    await db.close()


async def test_an_await_cancelled_after_the_thread_began_it_does_not_undo_it(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    inside, release = threading.Event(), threading.Event()

    def slow_insert(conn: sqlite3.Connection) -> None:
        inside.set()
        release.wait(5)
        conn.execute("INSERT INTO t VALUES (1, 'kept')")

    task = asyncio.ensure_future(db.write(slow_insert))
    await until(inside.is_set)
    task.cancel()
    release.set()
    await db.barrier()
    assert committed(tmp_path / "x.sqlite") == [1], "the thread had begun: the write is committed, the answer is dropped"
    await db.close()


async def test_every_function_runs_in_the_one_thread_which_is_not_the_loops(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    seen: set[int] = set()

    def note(conn: sqlite3.Connection) -> None:
        seen.add(threading.get_ident())

    await db.write(note)
    await db.read(note)
    await db.maintain(note)
    db.write_nowait(note)
    await db.barrier()
    assert len(seen) == 1 and threading.get_ident() not in seen
    await db.close()


async def test_nothing_is_left_open_between_two_operations(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    states: list[bool] = []
    await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'a')"))
    await db.maintain(lambda conn: states.append(conn.in_transaction))
    await db.read(lambda conn: conn.execute("SELECT 1").fetchone())
    await db.maintain(lambda conn: states.append(conn.in_transaction))
    assert states == [False, False]
    await db.close()


# ---- what a function that is run may not do
async def test_a_function_may_not_ask_the_database_thread_for_anything(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")

    def nested(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO t VALUES (1, 'half')")
        db.write_nowait(lambda c: None)

    with pytest.raises(NestedUse) as caught:
        await db.write(nested)
    assert isinstance(caught.value, DbError) and isinstance(caught.value, StoreError)
    assert committed(tmp_path / "x.sqlite") == [], "the write that went wrong is rolled back"
    await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (2, 'fine')"))
    assert committed(tmp_path / "x.sqlite") == [2], "and the thread goes on"
    await db.close()


@pytest.mark.parametrize("statement", ["BEGIN", "BEGIN IMMEDIATE", "COMMIT", "END", "END TRANSACTION", "ROLLBACK", "COMMIT TRANSACTION", "begin deferred"])
async def test_a_function_may_not_begin_commit_or_roll_back_a_transaction(tmp_path: Path, statement: str) -> None:
    db = await started(tmp_path / "x.sqlite")

    def own_transaction(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO t VALUES (1, 'half')")
        conn.execute(statement)
        conn.execute("INSERT INTO t VALUES (2, 'half')")

    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        await db.write(own_transaction)
    assert committed(tmp_path / "x.sqlite") == [], "nothing of a function that tried to take the transaction into its own hands is kept"
    await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (3, 'fine')"))
    assert await db.read(lambda conn: [r[0] for r in conn.execute("SELECT n FROM t")]) == [3]
    await db.close()


async def test_a_savepoint_inside_a_write_is_the_functions_own_business(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")

    def with_savepoint(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO t VALUES (1, 'a')")
        conn.execute("SAVEPOINT s")
        conn.execute("INSERT INTO t VALUES (2, 'b')")
        conn.execute("ROLLBACK TO s")
        conn.execute("RELEASE s")

    await db.write(with_savepoint)
    assert committed(tmp_path / "x.sqlite") == [1]
    await db.close()


async def test_a_read_cannot_write(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite")
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        await db.read(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'sneaked')"))
    assert committed(tmp_path / "x.sqlite") == []
    await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (2, 'allowed')"))          # and a write after a read can
    assert committed(tmp_path / "x.sqlite") == [2]
    await db.close()


async def test_the_statements_of_one_read_see_one_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    db = await started(path)
    await db.write(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'a')"))

    def two_looks(conn: sqlite3.Connection) -> tuple[int, int]:
        first = conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        other = sqlite3.connect(path, isolation_level=None, timeout=5)           # somebody else (another process) writes between the two statements
        other.execute("INSERT INTO t VALUES (2, 'b')")
        other.close()
        return first, conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]

    assert await db.read(two_looks) == (1, 1)
    assert await db.read(lambda conn: conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]) == 2
    await db.close()


# ---- starting
async def test_a_connection_that_is_not_in_autocommit_mode_is_refused(tmp_path: Path) -> None:
    db = Db(lambda: sqlite3.connect(tmp_path / "x.sqlite"), name=THREAD_PREFIX + "-bad")
    with pytest.raises(DbError, match="isolation_level"):
        await db.start()
    with pytest.raises(DbClosed):
        await db.read(lambda conn: 1)


async def test_what_the_opener_raises_is_raised_by_start_and_the_db_stays_closed(tmp_path: Path) -> None:
    def opener() -> sqlite3.Connection:
        raise StoreError("is of version 99, made by a newer NeoAPRS")

    db = Db(opener, name=THREAD_PREFIX + "-refused")
    with pytest.raises(StoreError, match="newer NeoAPRS"):
        await db.start()
    assert not db.is_open
    with pytest.raises(DbClosed, match="not open"):
        await db.write(lambda conn: None)
    await db.close()                                                              # closing what never opened is harmless


async def test_what_was_asked_while_the_file_was_opened_is_answered_when_the_opening_fails(tmp_path: Path) -> None:
    def opener() -> sqlite3.Connection:
        time.sleep(0.1)                                                           # a migration that takes a while, and then refuses the file
        raise StoreError("not ours")

    db = Db(opener, name=THREAD_PREFIX + "-slow")
    starting = asyncio.ensure_future(db.start())
    await asyncio.sleep(0.02)
    asked = eager(db.read(lambda conn: 1))
    with pytest.raises(StoreError, match="not ours"):
        await starting
    with pytest.raises(DbClosed):
        await asked


async def test_what_was_asked_while_the_file_was_opened_waits_for_it_and_is_done_in_order(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"

    def opener() -> sqlite3.Connection:
        time.sleep(0.1)
        conn = fast_connection(path)
        conn.execute("CREATE TABLE t (n INTEGER PRIMARY KEY, v TEXT NOT NULL)")
        return conn

    db = Db(opener, name=THREAD_PREFIX + "-slow")
    starting = asyncio.ensure_future(db.start())
    await asyncio.sleep(0.02)
    wrote = eager(db.write(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'a')")))
    counted = eager(db.read(lambda conn: conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]))
    await starting
    await wrote
    assert await counted == 1
    await db.close()


async def test_a_db_is_started_once(tmp_path: Path) -> None:
    db = await started(tmp_path / "x.sqlite", tables=False)
    with pytest.raises(DbError, match="started already"):
        await db.start()
    await db.close()
    with pytest.raises(DbError, match="started already"):
        await db.start()


async def test_asking_before_start_is_the_database_not_being_open(tmp_path: Path) -> None:
    db = Db.at(tmp_path / "x.sqlite")
    with pytest.raises(DbClosed, match="not open"):
        await db.read(lambda conn: 1)
    assert db.write_nowait(lambda conn: None) is False
