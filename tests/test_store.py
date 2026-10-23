"""The Store (neoaprs/store.py): the settings on the database thread, a store whose database is not open says no, a copy of the file and the checkpoint."""
import sqlite3
from pathlib import Path

import pytest

from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME, Store
from tests.support.clock import FixedClock
from tests.support.ptyline import posix_only
from tests.support.safety import FaultyConnection, raw
from tests.support.storedb import sql, store_at


async def setting_rev(store: Store, key: str) -> int:
    """How many times the setting has been written, 0 when it is not there."""
    rows = await sql(store, "SELECT rev FROM settings WHERE key = ?", key)
    return int(rows[0][0]) if rows else 0


async def test_a_new_file_has_the_current_version_and_no_settings(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    assert store.is_open() and await sql(store, "PRAGMA user_version") == [(SCHEMA_VERSION,)]
    assert await store.settings() == {} and await store.setting("station/call") is None and await setting_rev(store, "station/call") == 0


async def test_a_setting_is_kept_replaced_and_deleted(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    assert await store.put_setting("station/call", "OH2GBA")
    assert await store.setting("station/call") == "OH2GBA" and await setting_rev(store, "station/call") == 1
    assert await store.put_setting("station/call", "OH2GBA-9")
    assert await store.settings() == {"station/call": "OH2GBA-9"} and await setting_rev(store, "station/call") == 2
    await store.delete_setting("station/call")
    assert await store.settings() == {} and await setting_rev(store, "station/call") == 0


async def test_the_settings_round_trip_exactly(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    data = {"station/call": "OH2GBA-9", "station/lat": "60.1699", "station/comment": "ä ö \U0001F4E1 | \" ' ; --", "web/allowed_hosts": "", "multi/line": "a\nb\r\n"}
    assert await store.put_settings(data)
    assert await store.settings() == data
    assert await store.put_settings({"station/call": "OH2GBA", "web/port": "7303"})            # the other keys stay
    assert await store.settings() == {**data, "station/call": "OH2GBA", "web/port": "7303"}


async def test_settings_stored_during_an_error_are_not_half_stored(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = await store_at(tmp_path / DB_NAME)
    await store.put_settings({"a": "1"})
    assert not await store.put_settings({"b": "2", "": "an empty key is refused by the table"})
    assert await store.settings() == {"a": "1"}, "all of it or none"
    assert any("could not be stored" in r.getMessage() for r in caplog.records)


async def test_a_store_that_is_not_open_says_no_and_does_not_crash(tmp_path: Path) -> None:
    store = Store(FixedClock())
    assert not store.is_open()
    assert await store.settings() == {} and await store.setting("x") is None
    assert not await store.put_setting("x", "1") and not await store.put_settings({"x": "1"}) and not await store.backup(tmp_path / "copy.sqlite")
    await store.delete_setting("x")
    await store.checkpoint()
    opened = await store_at(tmp_path / DB_NAME)
    assert opened.db is not None
    await opened.db.close()
    assert not opened.is_open()
    assert await opened.settings() == {} and not await opened.put_setting("x", "1")             # a closed database is no error either


@pytest.mark.expects_errors
async def test_a_database_that_fails_is_told_and_does_not_raise(tmp_path: Path) -> None:
    path = tmp_path / DB_NAME
    store = await store_at(path)
    await store.put_setting("a", "1")
    assert store.db is not None
    await store.db.write(lambda conn: conn.execute("ALTER TABLE settings RENAME TO gone"))      # what a tool or another version could do to the file
    assert await store.settings() == {} and await store.setting("a") is None
    assert not await store.put_setting("a", "2")


async def test_a_backup_is_a_whole_second_database(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    await store.put_settings({"station/call": "OH2GBA", "station/lat": "60.17"})
    dest = tmp_path / "backup" / "copy.sqlite"
    assert await store.backup(dest)
    copy = raw(dest)
    assert copy.execute("SELECT key, value FROM settings ORDER BY key").fetchall() == [("station/call", "OH2GBA"), ("station/lat", "60.17")]
    assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    copy.close()
    assert not any(p.name.endswith((".tmp", "-wal", "-shm", "-journal")) for p in dest.parent.iterdir())


@pytest.mark.expects_errors
async def test_a_backup_to_an_impossible_place_fails_cleanly(tmp_path: Path) -> None:
    store = await store_at(tmp_path / DB_NAME)
    (tmp_path / "backup").write_text("a file where the folder should be")
    assert not await store.backup(tmp_path / "backup" / "copy.sqlite")
    assert await store.put_setting("a", "1"), "and the store goes on"


async def test_a_database_in_memory_cannot_be_copied() -> None:
    store = await store_at(":memory:")
    assert await store.put_setting("a", "1") and not await store.backup(Path("never.sqlite"))


async def test_the_checkpoint_moves_the_log_into_the_file_on_the_thread(tmp_path: Path) -> None:
    path = tmp_path / DB_NAME
    store = await store_at(path)
    for n in range(20):
        await store.put_setting(f"k/{n}", "x" * 400)
    wal = Path(str(path) + "-wal")
    assert wal.stat().st_size > 0
    await store.checkpoint()
    assert wal.stat().st_size == 0 and len(await store.settings()) == 20


@posix_only
async def test_the_file_and_its_log_are_private_to_this_user(tmp_path: Path) -> None:
    path = tmp_path / DB_NAME
    store = await store_at(path)
    await store.put_setting("a", "1")
    for name in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if name.exists():
            assert (name.stat().st_mode & 0o077) == 0, name


@pytest.mark.expects_errors
async def test_the_store_runs_on_a_connection_that_fails_on_demand(tmp_path: Path) -> None:
    from neoaprs.migrations import open_database
    path = tmp_path / DB_NAME
    migrated, error = open_database(path)
    assert migrated is not None, error
    migrated.close()
    made: list[FaultyConnection] = []

    def opener() -> sqlite3.Connection:
        conn = sqlite3.connect(str(path), isolation_level=None, timeout=5, factory=FaultyConnection)
        made.append(conn)
        return conn

    store = await store_at(path, opener=opener)
    made[0].statements, made[0].fail_at = 0, 2            # BEGIN, the statement, ...: the second statement of the next operation fails
    assert not await store.put_setting("a", "1")
    made[0].fail_at = None
    assert await store.settings() == {} and await store.put_setting("a", "1") and await store.setting("a") == "1"
