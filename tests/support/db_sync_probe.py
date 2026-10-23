"""Writes through the Db actor and says "ACK n" on file descriptor 2 after each write that has returned: run under strace by tests/safety/test_db_actor_lifecycle.py, which reads from the
trace whether the commit had been synced to the disk by the time the write returned.

    python -c "from tests.support.db_sync_probe import main; main()" DB COUNT [SYNCHRONOUS]"""
import asyncio
import os
import sqlite3
import sys
from collections.abc import Callable

from neoaprs.db import Db
from neoaprs.dbfile import connect


def insert(n: int) -> Callable[[sqlite3.Connection], object]:
    return lambda conn: conn.execute("INSERT INTO t VALUES (?, 'x')", (n,))


async def run(path: str, count: int, synchronous: str) -> None:
    def opener() -> sqlite3.Connection:
        conn = connect(path)
        conn.execute(f"PRAGMA synchronous={synchronous}")                  # FULL is what it is already; NORMAL is what the probe must see as unsynced
        return conn

    db = Db(opener)
    await db.start()
    await db.write(lambda conn: conn.execute("CREATE TABLE t (n INTEGER PRIMARY KEY, v TEXT)"))
    os.write(2, b"READY\n")                                                 # the first WAL and the schema are behind
    for n in range(count):
        await db.write(insert(n))
        os.write(2, f"ACK {n}\n".encode())
    await db.close()


def main() -> None:
    asyncio.run(run(sys.argv[1], int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "FULL"))


if __name__ == "__main__":
    main()
