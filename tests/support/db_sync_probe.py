"""Write through the Db actor and print "ACK n" on file descriptor 2 after each returned write.

Run under strace by tests/safety/test_db_actor_lifecycle.py to see whether the commit was synced.
"""
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
        # FULL is the default; NORMAL is what the probe must see as unsynced.
        conn.execute(f"PRAGMA synchronous={synchronous}")
        return conn

    db = Db(opener)
    await db.start()
    await db.write(lambda conn: conn.execute("CREATE TABLE t (n INTEGER PRIMARY KEY, v TEXT)"))
    # The first WAL and the schema are behind.
    os.write(2, b"READY\n")
    for n in range(count):
        await db.write(insert(n))
        os.write(2, f"ACK {n}\n".encode())
    await db.close()


def main() -> None:
    asyncio.run(run(sys.argv[1], int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "FULL"))


if __name__ == "__main__":
    main()
