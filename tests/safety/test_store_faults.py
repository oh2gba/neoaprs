"""The Store (neoaprs/store.py) when the database fails under it: a setting that cannot be deleted is left as it was and the store goes on, a checkpoint that fails is a warning and not an exception, and
a store whose Db is closed says no to everything."""
import logging
import sqlite3
from pathlib import Path

import pytest

from neoaprs.migrations import open_database
from neoaprs.store import DB_NAME, Store
from tests.support.safety import FaultyConnection
from tests.support.storedb import store_at


async def faulty_store(tmp_path: Path) -> tuple[Store, list[FaultyConnection]]:
    path = tmp_path / DB_NAME
    migrated, error = open_database(path)
    assert migrated is not None, error
    migrated.close()
    made: list[FaultyConnection] = []

    def opener() -> sqlite3.Connection:
        conn = sqlite3.connect(str(path), isolation_level=None, timeout=5, factory=FaultyConnection)
        made.append(conn)
        return conn

    return await store_at(path, opener=opener), made


async def test_a_setting_that_cannot_be_deleted_is_left_as_it_was_and_the_store_goes_on(tmp_path: Path) -> None:
    store, made = await faulty_store(tmp_path)
    assert await store.put_setting("station/call", "OH2GBA")
    made[0].statements, made[0].fail_at = 0, 2                         # BEGIN, then the DELETE fails
    await store.delete_setting("station/call")
    made[0].fail_at = None
    assert await store.setting("station/call") == "OH2GBA", "nothing was deleted"
    await store.delete_setting("station/call")
    assert await store.setting("station/call") is None


async def test_a_checkpoint_that_fails_is_told_as_a_warning_and_not_raised(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store, made = await faulty_store(tmp_path)
    made[0].statements, made[0].fail_at = 0, 1                         # the first statement of the checkpoint
    with caplog.at_level(logging.WARNING, "neoaprs.store"):
        await store.checkpoint()
    assert [r.getMessage() for r in caplog.records if r.name == "neoaprs.store"] == ["the checkpoint failed: database or disk is full"]
    made[0].fail_at = None
    await store.checkpoint()
    assert len([r for r in caplog.records if r.name == "neoaprs.store"]) == 1


async def test_a_store_whose_db_was_closed_says_no_to_everything_and_raises_nothing(tmp_path: Path) -> None:
    store, _ = await faulty_store(tmp_path)
    assert await store.put_setting("a", "1")
    assert store.db is not None
    await store.db.close()
    assert not store.is_open()
    assert await store.settings() == {} and await store.setting("a") is None
    assert not await store.put_setting("a", "2") and not await store.put_settings({"a": "2"})
    await store.delete_setting("a")
    await store.checkpoint()
    assert not await store.backup(tmp_path / "copy.sqlite")
