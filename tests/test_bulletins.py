"""The message board (neoaprs/services/bulletins.py) on a real bulletin log and a clock the test holds: what is kept for a sender and a slot, a text that is replaced, the hearings counted, that
nothing ages out or is trimmed, the delete, and a restart."""
import asyncio
from pathlib import Path

import pytest

from neoaprs.bulletin import BulletinRecord
from neoaprs.bulletinlog import BulletinLog
from neoaprs.packet import Message, Packet, ThirdParty
from neoaprs.services.bulletins import COPY_SEC, Bulletins
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.storedb import store_at

TICK = 0.01


class Rig:
    def __init__(self, log: BulletinLog, clock: FixedClock) -> None:
        self.log, self.clock = log, clock
        self.board = Bulletins(log, clock)
        self.changed: list[BulletinRecord] = []
        self.removed: list[BulletinRecord] = []
        self.board.changed.connect(self.changed.append)
        self.board.removed.connect(self.removed.append)

    def hear(self, sender: str, addressee: str, text: str, via: str = "") -> None:
        third = ThirdParty(sender, "APRS", ("TCPIP",)) if via else None
        message = Message(addressee, text)
        self.board.heard(Packet(self.clock(), "in", b"", via or sender, "APRS", (), b"", message, third), message)

    async def tick(self, seconds: float = 0.0) -> None:
        self.clock.advance(seconds)
        await asyncio.sleep(TICK * 6)

    async def settled(self) -> None:
        assert self.log.db is not None
        await self.log.db.barrier()


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    assert store.db is not None
    r = Rig(BulletinLog(store.db, clock), clock)
    await r.board.start()
    return r


def keys(rig: Rig) -> list[str]:
    return [b.key for b in rig.board.records()]


async def test_a_bulletin_is_kept_for_its_sender_and_slot_and_told(rig: Rig) -> None:
    rig.hear("OH2XYZ", "BLN1", "Road closed at Kaivopuisto")
    [one] = rig.board.records()
    assert (one.sender, one.slot, one.group, one.kind, one.text, one.times_heard) == ("OH2XYZ", "BLN1", "", "bulletin", "Road closed at Kaivopuisto", 1)
    assert one.first_heard == one.last_heard == rig.clock() and rig.changed == [one] and rig.board.get("OH2XYZ/BLN1") == one
    await rig.settled()
    assert await rig.log.all() == [one]


async def test_each_kind_is_told_by_its_slot_and_a_group_bulletin_has_its_group(rig: Rig) -> None:
    for slot in ("BLN1", "BLNA", "BLN3HAMS", "QST", "CQ", "ALL"):
        rig.hear("OH2XYZ", slot, "text")
    found = {b.slot: (b.kind, b.group) for b in rig.board.records()}
    assert found == {"BLN1": ("bulletin", ""), "BLNA": ("announcement", ""), "BLN3HAMS": ("group", "HAMS"), "QST": ("group", ""), "CQ": ("group", ""), "ALL": ("group", "")}


async def test_a_sender_sending_the_slot_again_replaces_the_text_and_starts_the_count(rig: Rig) -> None:
    rig.hear("OH2XYZ", "BLN1", "first")
    await rig.tick(3600)
    rig.hear("OH2XYZ", "BLN1", "second")
    [one] = rig.board.records()
    assert (one.text, one.times_heard, one.first_heard, one.last_heard) == ("second", 1, rig.clock(), rig.clock())
    await rig.settled()
    assert [b.text for b in await rig.log.all()] == ["second"], "one row for the sender and the slot"


async def test_the_same_text_heard_again_counts_and_moves_the_last_hearing_but_not_the_first(rig: Rig) -> None:
    rig.hear("OH2XYZ", "BLN1", "same")
    first = rig.clock()
    await rig.tick(1800)
    rig.hear("OH2XYZ", "BLN1", "same")
    await rig.tick(1800)
    rig.hear("OH2XYZ", "BLN1", "same")
    [one] = rig.board.records()
    assert (one.times_heard, one.first_heard, one.last_heard) == (3, first, rig.clock())


async def test_the_copies_of_one_transmission_within_ten_seconds_are_one_hearing(rig: Rig) -> None:
    rig.hear("OH2XYZ", "BLN1", "same")
    for _ in range(3):
        await rig.tick(COPY_SEC / 2 - 1)
        rig.hear("OH2XYZ", "BLN1", "same")
    [one] = rig.board.records()
    assert one.times_heard == 1 and one.last_heard == rig.clock(), "the last hearing moves with the copy"
    await rig.tick(COPY_SEC + 1)
    rig.hear("OH2XYZ", "BLN1", "same")
    assert rig.board.records()[0].times_heard == 2


async def test_two_senders_and_two_slots_are_three_rows_and_the_newest_is_first(rig: Rig) -> None:
    rig.hear("OH2XYZ", "BLN1", "a")
    await rig.tick(10)
    rig.hear("OH2ABC", "BLN1", "b")
    await rig.tick(10)
    rig.hear("OH2XYZ", "BLN2", "c")
    assert keys(rig) == ["OH2XYZ/BLN2", "OH2ABC/BLN1", "OH2XYZ/BLN1"]
    await rig.tick(10)
    rig.hear("OH2XYZ", "BLN1", "a")
    assert keys(rig)[0] == "OH2XYZ/BLN1", "heard again, it is the newest"


async def test_a_third_party_bulletin_is_from_the_sender_inside(rig: Rig) -> None:
    rig.hear("OH2DPN", "BLN4", "from the net", via="OH7JHF-1")
    assert keys(rig) == ["OH2DPN/BLN4"]


async def test_a_bulletin_with_no_text_is_not_kept(rig: Rig) -> None:
    rig.hear("OH2XYZ", "BLN1", "   ")
    rig.board.heard(Packet(rig.clock(), "in", b"", "OH2XYZ", "APRS", (), b"", Message("OH2GBA", "x"), None), Message("OH2GBA", "x"))
    assert rig.board.records() == [] and rig.changed == []


async def test_nothing_ages_out_not_after_a_day_nor_a_year_and_the_rows_keep_their_times(rig: Rig) -> None:
    for slot in ("BLN1", "BLN3HAMS", "QST", "BLNA"):
        rig.hear("OH2XYZ", slot, "text")
    rig.hear("OH2XYZ", "BLN1", "text")
    first = rig.clock()
    await rig.tick(365 * 86400)
    assert sorted(keys(rig)) == ["OH2XYZ/BLN1", "OH2XYZ/BLN3HAMS", "OH2XYZ/BLNA", "OH2XYZ/QST"] and rig.removed == []
    one = rig.board.get("OH2XYZ/BLN1")
    assert one is not None and (one.times_heard, one.first_heard, one.last_heard) == (1, first, first), "the times heard and the last hearing stay"
    await rig.settled()
    assert len(await rig.log.all()) == 4, "and the database keeps them"


async def test_a_restart_finds_the_whole_board(rig: Rig) -> None:
    rig.hear("OH2XYZ", "BLN1", "old")
    rig.hear("OH2XYZ", "BLNA", "an announcement")
    rig.clock.advance(30 * 86400)
    rig.hear("OH2ABC", "BLN2", "new")
    await rig.settled()
    again = Rig(rig.log, rig.clock)
    await again.board.start()
    assert sorted(b.key for b in again.board.records()) == ["OH2ABC/BLN2", "OH2XYZ/BLN1", "OH2XYZ/BLNA"]
    assert len(again.board.records()) == 3


async def test_the_board_has_no_limit_of_size(rig: Rig) -> None:
    for n in range(520):
        rig.hear(f"OH2{n:03d}", "BLN1", "x")
        rig.clock.advance(1)
    assert len(rig.board.records()) == 520 and rig.removed == []


async def test_delete_removes_the_entry_from_the_board_and_the_database_and_tells(rig: Rig) -> None:
    rig.hear("OH2XYZ", "BLN1", "a")
    rig.hear("OH2XYZ", "BLN2", "b")
    [gone] = [b for b in rig.board.records() if b.slot == "BLN1"]
    assert rig.board.delete("OH2XYZ", "BLN1") is True
    assert keys(rig) == ["OH2XYZ/BLN2"] and rig.removed == [gone] and rig.board.get("OH2XYZ/BLN1") is None
    await rig.settled()
    assert [b.key for b in await rig.log.all()] == ["OH2XYZ/BLN2"]
    assert rig.board.delete("OH2XYZ", "BLN1") is False and rig.board.delete("OH2NONE", "BLN9") is False and len(rig.removed) == 1


async def test_a_bulletin_sent_again_after_a_delete_is_new(rig: Rig) -> None:
    rig.hear("OH2XYZ", "BLN1", "same")
    await rig.tick(100)
    rig.hear("OH2XYZ", "BLN1", "same")
    assert rig.board.records()[0].times_heard == 2
    first = rig.board.records()[0].first_heard
    rig.board.delete("OH2XYZ", "BLN1")
    await rig.tick(100)
    rig.hear("OH2XYZ", "BLN1", "same")
    [again] = rig.board.records()
    assert (again.times_heard, again.first_heard) == (1, rig.clock()) and again.first_heard != first
    assert rig.changed[-1] == again


async def test_a_board_that_is_not_in_a_database_still_works() -> None:
    clock = FixedClock()
    r = Rig(BulletinLog(None, clock), clock)
    await r.board.start()
    r.hear("OH2XYZ", "BLN1", "x")
    assert keys(r) == ["OH2XYZ/BLN1"]
    assert r.log.dropped == 1, "the write that could not be queued is counted"


async def test_a_weather_service_bulletin_is_kept_on_the_board_as_the_kind_nws_and_a_restart_finds_it(rig: Rig, tmp_path: Path) -> None:
    rig.hear("OH2XYZ", "NWS-WARNV", "092010z,THUNDER_STORM,AR_ASHLEY,")
    [one] = rig.board.records()
    assert (one.slot, one.kind, one.group, one.key) == ("NWS-WARNV", "nws", "", "OH2XYZ/NWS-WARNV")
    await rig.settled()
    again = Rig(rig.log, rig.clock)
    await again.board.start()
    assert again.board.records() == [one]
