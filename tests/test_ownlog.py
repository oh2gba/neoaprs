"""The log of our own objects and bulletins (neoaprs/ownlog.py, ownsql.py) on a real database thread: what goes in comes out equal, one row for a name and for a slot, the delete, a row this program did not write,
and a log with no database."""
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.clock import utc
from neoaprs.ownbulletin import OwnBulletin
from neoaprs.ownlog import OwnLog, bulletin_of, bulletin_row, object_of, object_row
from neoaprs.ownobject import OwnObject
from neoaprs.store import DB_NAME, Store
from tests.support.clock import FixedClock
from tests.support.storedb import sql, store_at

T0 = utc(2026, 10, 21, 12, 0, 0)


def obj(name: str = "LEADER", **more: object) -> OwnObject:
    fields: dict[str, object] = {"kind": "object", "lat": 60.17, "lon": 24.94, "symbol_table": "/", "symbol_code": ">", "created_at": T0, "updated_at": T0 + timedelta(minutes=1), **more}
    return OwnObject(name, **fields)                                                       # type: ignore[arg-type]


def post(slot: str = "BLN3HAMS", **more: object) -> OwnBulletin:
    fields: dict[str, object] = {"group": "HAMS" if slot == "BLN3HAMS" else "", "kind": "group" if slot == "BLN3HAMS" else "announcement" if slot[3].isalpha() else "bulletin", "text": "Net tonight", "created_at": T0, **more}
    return OwnBulletin(slot, **fields)                                                     # type: ignore[arg-type]


async def opened_with_store(tmp_path: Path) -> tuple[OwnLog, Store]:
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    assert store.db is not None
    return OwnLog(store.db, clock), store


def test_an_object_gives_its_row_and_the_row_gives_the_object_back() -> None:
    full = obj(comment="Rescue 1 åäö"[:12], course_deg=0, speed_kmh=12.5, path="WIDE2-1", alive=False, sent=3, last_sent_at=T0 + timedelta(minutes=2))
    assert object_row(full) == ("LEADER", "object", 60.17, 24.94, "/", ">", "Rescue 1 åäö", 0, 12.5, "WIDE2-1", 0, "2026-10-21T12:00:00.000000Z", "2026-10-21T12:01:00.000000Z", 3, "2026-10-21T12:02:00.000000Z")
    assert object_of(object_row(full)) == full
    plain = obj("AID", kind="item")
    assert object_of(object_row(plain)) == plain and object_row(plain)[7:10] == (None, None, None) and object_row(plain)[14] is None


def test_a_bulletin_gives_its_row_and_the_row_gives_the_bulletin_back() -> None:
    sent = post(sent=2, first_sent_at=T0, last_sent_at=T0 + timedelta(minutes=2))
    assert bulletin_row(sent) == ("BLN3HAMS", "HAMS", "Net tonight", "2026-10-21T12:00:00.000000Z", 2, "2026-10-21T12:00:00.000000Z", "2026-10-21T12:02:00.000000Z")
    assert bulletin_of(bulletin_row(sent)) == sent
    assert bulletin_of(bulletin_row(post("BLNA"))) == post("BLNA") and bulletin_of(bulletin_row(post("BLNA"))).kind == "announcement"


async def test_what_goes_in_comes_out_the_oldest_first_and_a_name_and_a_slot_have_one_row(tmp_path: Path) -> None:
    log, _ = await opened_with_store(tmp_path)
    later = obj("ZULU", created_at=T0 + timedelta(minutes=9))
    assert log.save_object(later) and log.save_object(obj("ALPHA")) and log.save_object(replace(obj("ALPHA"), comment="changed", sent=1, last_sent_at=T0))
    assert log.save_bulletin(post("BLN3HAMS")) and log.save_bulletin(post("BLN1", created_at=T0 - timedelta(hours=1))) and log.save_bulletin(replace(post("BLN3HAMS"), text="changed"))
    assert log.db is not None
    await log.db.barrier()
    assert [(o.name, o.comment, o.sent) for o in await log.objects()] == [("ALPHA", "changed", 1), ("ZULU", "", 0)]
    assert [(b.slot, b.text) for b in await log.bulletins()] == [("BLN1", "Net tonight"), ("BLN3HAMS", "changed")]


async def test_delete_removes_one_object_and_one_bulletin(tmp_path: Path) -> None:
    log, _ = await opened_with_store(tmp_path)
    log.save_object(obj("ONE"))
    log.save_object(obj("TWO"))
    log.save_bulletin(post("BLN1"))
    log.save_bulletin(post("BLN2"))
    assert log.delete_object("ONE") and log.delete_bulletin("BLN2") and log.delete_object("NOBODY")
    assert log.db is not None
    await log.db.barrier()
    assert [o.name for o in await log.objects()] == ["TWO"] and [b.slot for b in await log.bulletins()] == ["BLN1"]


async def test_a_row_this_program_did_not_write_is_left_out_and_told(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.ownlog")
    log, store = await opened_with_store(tmp_path)
    log.save_object(obj())
    log.save_bulletin(post("BLN1"))
    assert log.db is not None
    await log.db.barrier()
    await sql(store, "INSERT INTO own_bulletin (slot, group_name, text, created_at, sent) VALUES ('BLN3HAMS', 'WRONG', 'x', '2026-10-21T12:00:00.000000Z', 0)")      # (the group is not the one of the slot)
    assert [o.name for o in await log.objects()] == ["LEADER"] and [b.slot for b in await log.bulletins()] == ["BLN1"]
    assert any("could not be read" in r.getMessage() and "own_bulletin" in r.getMessage() for r in caplog.records)


async def test_a_log_with_no_database_says_no_instead_of_raising() -> None:
    log = OwnLog(None, FixedClock())
    assert not log.save_object(obj()) and not log.delete_object("X") and not log.save_bulletin(post()) and not log.delete_bulletin("X")
    assert await log.objects() == [] and await log.bulletins() == [] and log.dropped == 4
