"""The database thread dies (neoaprs/dbthread.py): an error that is not SQLite's, in the middle of committing a batch of appends, ends the thread; everything that was asked and not done is answered with
DbClosed (nobody waits for ever), the one who asks next is refused, and nothing of the batch is kept."""
import asyncio
import sqlite3
import threading
from pathlib import Path

import pytest

from neoaprs.dberror import DbClosed
from neoaprs.dbthread import Tuning
from tests.support.dbactor import committed, eager, started, wait_gone
from tests.support.env import until
from tests.support.riggedsql import plain


class Broken(sqlite3.Connection):
    """A connection whose library breaks (what is not an sqlite3.Error) at the next BEGIN IMMEDIATE once `broken` is set."""
    broken = threading.Event()

    def execute(self, sql: str, *args: object) -> sqlite3.Cursor:
        if self.broken.is_set() and sql.startswith("BEGIN IMMEDIATE"):
            raise RuntimeError("the library broke")
        return plain(self, sql, *args)


@pytest.mark.expects_errors
async def test_a_thread_that_dies_while_committing_a_batch_answers_what_ended_the_batch_and_what_was_queued_behind_it(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "x.sqlite"
    broken = threading.Event()
    connection_class = type("Mine", (Broken,), {"broken": broken})

    def opener() -> sqlite3.Connection:
        conn = sqlite3.connect(str(path), isolation_level=None, timeout=5, factory=connection_class)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    db = await started(path, opener, tuning=Tuning(tick=30.0))
    inside, release = threading.Event(), threading.Event()
    held = eager(db.maintain(lambda conn: (inside.set(), release.wait(10))))
    await until(inside.is_set)
    broken.set()
    assert db.write_nowait(lambda conn: conn.execute("INSERT INTO t VALUES (1, 'a')"))
    read = eager(db.read(lambda conn: 1))                                                      # it ends the batch: the thread has taken it off the queue when the commit breaks
    write = eager(db.write(lambda conn: conn.execute("INSERT INTO t VALUES (2, 'b')")))        # and these are still on the queue
    assert db.write_nowait(lambda conn: conn.execute("INSERT INTO t VALUES (3, 'c')"))
    release.set()
    await held
    for asked in (read, write):
        with pytest.raises(DbClosed, match="has stopped"):
            await asyncio.wait_for(asked, 5)               # (an answer that never comes is a failure, not a test that never ends)
    assert wait_gone(2.0) == []
    assert any("the database thread failed" in r.getMessage() for r in caplog.records)
    assert db.is_open, "the Db has not been told: the next ask finds the queue closed"
    with pytest.raises(DbClosed):
        await db.write(lambda conn: None)
    with pytest.raises(DbClosed):
        await db.read(lambda conn: 1)
    assert db.write_nowait(lambda conn: None) is False and db.stats()["dropped"] == 1
    assert committed(path) == []
    await db.close()
