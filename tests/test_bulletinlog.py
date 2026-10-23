"""The bulletin log (neoaprs/bulletinlog.py, bulletinsql.py) on a real database thread: what goes in comes out equal, one row for a sender and slot, the delete, the care, and a row this program did not write."""
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.bulletin import BulletinRecord
from neoaprs.bulletinlog import BulletinLog, bulletin_of, bulletin_row
from neoaprs.clock import utc
from neoaprs.store import Store
from tests.support.clock import FixedClock
from tests.support.storedb import log_at, sql

T0 = utc(2026, 10, 21, 12, 0, 0)


def bulletin(sender: str = "OH2XYZ", slot: str = "BLN3HAMS", text: str = "Net tonight", **more: object) -> BulletinRecord:
    return BulletinRecord(sender, slot, "HAMS" if slot == "BLN3HAMS" else "", "group" if slot == "BLN3HAMS" else "bulletin", text, T0, T0 + timedelta(minutes=5), 3, **more)  # type: ignore[arg-type]


async def opened(tmp_path: Path) -> BulletinLog:
    log, _ = await opened_with_store(tmp_path)
    return log


async def opened_with_store(tmp_path: Path) -> tuple[BulletinLog, Store]:
    log, store, _ = await log_at(tmp_path, BulletinLog)
    return log, store


def test_a_record_gives_its_row_and_the_row_gives_the_record_back() -> None:
    record = bulletin(text="Åland ä ö")
    assert bulletin_row(record) == ("OH2XYZ", "BLN3HAMS", "HAMS", "Åland ä ö", "2026-10-21T12:00:00.000000Z", "2026-10-21T12:05:00.000000Z", 3)
    assert bulletin_of(bulletin_row(record)) == record


async def test_what_goes_in_comes_out_the_one_heard_last_first_and_a_sender_and_slot_have_one_row(tmp_path: Path) -> None:
    log = await opened(tmp_path)
    older = replace(bulletin("OH2ABC", "BLN1", "old"), last_heard=T0)
    newer = bulletin("OH2XYZ", "BLNA", "an announcement")
    assert log.save(older) and log.save(newer) and log.save(replace(newer, text="changed", times_heard=1))
    assert log.db is not None
    await log.db.barrier()
    assert [(b.key, b.text, b.times_heard) for b in await log.all()] == [("OH2XYZ/BLNA", "changed", 1), ("OH2ABC/BLN1", "old", 3)]


async def test_delete_removes_one_bulletin(tmp_path: Path) -> None:
    log = await opened(tmp_path)
    one, two = bulletin("OH2XYZ", "BLN1"), bulletin("OH2XYZ", "BLN2")
    log.save(one)
    log.save(two)
    assert log.delete(one)
    assert log.db is not None
    await log.db.barrier()
    assert [b.key for b in await log.all()] == ["OH2XYZ/BLN2"]


async def test_a_row_this_program_did_not_write_is_left_out_and_told(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.bulletinlog")
    log, store = await opened_with_store(tmp_path)
    log.save(bulletin())
    assert log.db is not None
    await log.db.barrier()
    await sql(store, "INSERT INTO bulletin (sender, slot, group_name, text, first_heard, last_heard, times_heard) VALUES ('OH2ABC', 'NOT-A-SLOT', '', 'x', '2026-10-21T12:00:00.000000Z', '2026-10-21T12:00:00.000000Z', 1)")
    assert [b.key for b in await log.all()] == ["OH2XYZ/BLN3HAMS"] and any("could not be read" in r.getMessage() for r in caplog.records)


async def test_a_log_with_no_database_says_no_instead_of_raising() -> None:
    log = BulletinLog(None, FixedClock())
    assert not log.save(bulletin()) and not log.delete(bulletin()) and await log.all() == [] and log.dropped == 2
