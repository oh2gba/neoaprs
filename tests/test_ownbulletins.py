"""The bulletins, announcements and group bulletins of ours (neoaprs/services/ownbulletins.py) on a Tnc that is a stub, a real log in a temporary database and a clock the test holds: the schedule of each
kind, a text that replaces the one in its slot, the delete, the interlock, the radio that is away, and a restart."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.ownbulletin import MAX_POSTED, PostError
from neoaprs.ownlog import OwnLog
from neoaprs.services.ownbulletins import OwnBulletins
from neoaprs.services.sender import Sender
from neoaprs.source import Source
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.env import remember_stop
from tests.support.storedb import store_at
from tests.support.rig import ServiceRig


class Rig(ServiceRig):
    """One run of the daemon's bulletins: made again on the same log and clock after a stop."""

    def __init__(self, log: OwnLog, clock: FixedClock, **changes: object) -> None:
        super().__init__(clock, **changes)
        self.log, self.begin = log, clock()
        self.sender = Sender(self.tnc, lambda: self.config, clock, spacing_sec=10.0)
        self.posts = OwnBulletins(self.sender, lambda: self.config, log, clock, tick_sec=3600.0)
        self.sent: list[tuple[int, bytes]] = []                         # (seconds since the rig was made, the information field)
        self.record(self.posts)

    async def start(self) -> "Rig":
        await self.posts.start()
        remember_stop(self.posts.stop)
        return self

    def run(self, seconds: int, step: int = 5) -> None:
        """Looks at the clock every `step` seconds for this long, the first look now; the clock ends where the last look was."""
        for _ in range(0, seconds + 1, step):
            before = len(self.tnc.sent)
            self.posts.tick()
            self.sent += [(round((self.clock() - self.begin).total_seconds()), frame.info) for frame in self.tnc.sent[before:]]
            self.clock.advance(step)
        self.clock.advance(-step)

    def offsets(self) -> list[int]:
        return [t for t, _ in self.sent]

    async def settled(self) -> None:
        assert self.log.db is not None
        await self.log.db.barrier()


async def rig_at(tmp_path: Path, **changes: object) -> Rig:
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    assert store.db is not None
    return await Rig(OwnLog(store.db, clock), clock, **changes).start()


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    return await rig_at(tmp_path)


async def test_a_bulletin_goes_out_at_once_after_2_and_6_minutes_and_then_every_20_minutes_for_4_hours_and_is_then_over(rig: Rig) -> None:
    posted = rig.posts.post("BLN1", "Road closed at Kaivopuisto")
    rig.run(5 * 3600)
    assert rig.offsets() == [0, 120, 360, *range(1560, 13561, 1200)] and len(rig.offsets()) == 14
    assert all(info == b":BLN1     :Road closed at Kaivopuisto" for _, info in rig.sent)
    ended = rig.posts.get("BLN1")
    assert ended is not None and ended.sent == 14 and rig.posts.next_at("BLN1") is None, "it stays on the board as ended"
    assert posted.sent == 0 and ended.first_sent_at == rig.begin and ended.last_sent_at == rig.begin + timedelta(seconds=13560)


async def test_an_announcement_goes_out_early_and_then_every_hour_for_72_hours(rig: Rig) -> None:
    rig.posts.post("BLNA", "Club meeting on Thursday")
    rig.run(80 * 3600, step=60)
    offsets = rig.offsets()
    assert offsets[:6] == [0, 120, 360, 3960, 7560, 11160] and offsets[-1] == 360 + 71 * 3600 and len(offsets) == 3 + 71
    assert rig.posts.next_at("BLNA") is None


async def test_a_group_bulletin_goes_to_its_group_by_the_beacons_path_on_the_bulletins_schedule(rig: Rig) -> None:
    rig.posts.post("bln3hams", "Net tonight 20:00")
    rig.run(400)
    assert rig.offsets() == [0, 120, 360]
    frame = rig.tnc.sent[0]
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::BLN3HAMS :Net tonight 20:00" and frame.is_ui


async def test_the_next_time_is_told_and_what_is_overdue_says_so(rig: Rig) -> None:
    rig.posts.post("BLN1", "x")
    assert rig.posts.next_at("BLN1") == rig.begin, "due at once"
    rig.run(0)
    assert rig.posts.next_at("BLN1") == rig.begin + timedelta(seconds=120)
    assert rig.posts.next_at("BLN2") is None and rig.posts.get("BLN2") is None


async def test_a_new_text_for_a_slot_replaces_the_old_one_and_the_schedule_starts_again_never_within_a_minute(rig: Rig) -> None:
    rig.posts.post("BLN1", "one")
    rig.run(10)
    rig.posts.post("BLN1", "two")
    rig.run(500)
    assert [t for t, _ in rig.sent] == [0, 60, 180, 420] and [info[-3:] for _, info in rig.sent] == [b"one", b"two", b"two", b"two"]
    assert [b.slot for b in rig.posts.records()] == ["BLN1"], "one entry for a slot"
    await rig.settled()
    assert [b.text for b in await rig.log.bulletins()] == ["two"]


async def test_a_bulletin_that_is_over_is_posted_again_with_the_same_text_and_goes_out_again(rig: Rig) -> None:
    rig.posts.post("BLN1", "same")
    rig.run(4 * 3600 + 60)
    assert len(rig.sent) == 14 and rig.posts.next_at("BLN1") is None
    rig.posts.post("BLN1", "same")
    rig.run(300)
    assert len(rig.sent) == 16 and rig.posts.get("BLN1").sent == 2                            # type: ignore[union-attr]


async def test_deleting_a_bulletin_stops_it_and_takes_it_off_the_board_and_out_of_the_database(rig: Rig) -> None:
    rig.posts.post("BLN1", "gone")
    rig.posts.post("BLN2", "stays")
    rig.run(0)
    assert rig.posts.delete("BLN1") and not rig.posts.delete("BLN1") and not rig.posts.delete("BLN9")
    assert [b.slot for b in rig.removed] == ["BLN1"]
    rig.run(700)
    assert [info for _, info in rig.sent if b"gone" in info] == [b":BLN1     :gone"], "it was sent once before it was deleted, never after"
    await rig.settled()
    assert [b.slot for b in await rig.log.bulletins()] == ["BLN2"]


async def test_nothing_is_posted_while_the_call_is_not_set(tmp_path: Path) -> None:
    rig = await rig_at(tmp_path, station_call="")
    with pytest.raises(PostError, match="set your call first"):
        rig.posts.post("BLN1", "x")
    assert rig.posts.records() == [] and rig.tnc.sent == []


async def test_nothing_is_sent_while_the_call_is_gone_and_one_packet_goes_out_when_it_is_back(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    rig.posts.post("BLN1", "x")
    rig.config = replace(rig.config, station_call="")
    rig.run(1000)
    assert rig.tnc.sent == [] and "no bulletin sent" in caplog.text
    rig.config = replace(rig.config, station_call="OH2GBA")
    rig.run(0)
    assert rig.offsets() == [1000]


async def test_the_radio_that_is_silent_holds_it_back_and_it_is_not_made_up_when_the_radio_is_back(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    rig.posts.post("BLN1", "x")
    rig.run(0)
    rig.tnc.state = Source.State.SILENT
    rig.run(3000)
    assert rig.offsets() == [0] and caplog.text.count("is due and") == 1
    rig.tnc.state = Source.State.CONNECTED
    rig.run(100)
    assert rig.offsets() == [0, 3000], "one, not the ones that were due on the way"
    rig.run(1000)
    assert rig.offsets() == [0, 3000, 3000 + 240] and rig.posts.get("BLN1").sent == 3                  # type: ignore[union-attr]


async def test_a_slot_or_a_text_that_cannot_be_sent_is_refused_with_the_reason(rig: Rig) -> None:
    for slot, text, why in (("BLN", "x", "is not BLN0"), ("QST", "x", "is not BLN0"), ("BLN1", "", "empty"), ("BLN1", "x" * 68, "at most 67"), ("BLN1", "a|b", "forbidden|cannot carry|not allowed")):
        with pytest.raises(PostError, match=why):
            rig.posts.post(slot, text)
    assert rig.posts.records() == []


async def test_there_is_a_limit_to_the_bulletins_posted(rig: Rig) -> None:
    slots = [f"BLN{c}" for c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    assert len(slots) == MAX_POSTED
    for slot in slots:
        rig.posts.post(slot, "x")
    with pytest.raises(PostError, match="delete one first"):
        rig.posts.post("BLN1X", "x")
    rig.posts.post("BLN1", "a text for a slot that is there")


async def test_a_restart_goes_on_where_the_schedule_stopped_and_an_ended_one_stays_ended(tmp_path: Path) -> None:
    first = await rig_at(tmp_path)
    first.posts.post("BLN1", "kept")
    first.posts.post("BLNA", "also kept")
    first.run(130)
    assert first.offsets() == [0, 10, 120, 130]
    await first.settled()
    await first.posts.stop()

    first.clock.advance(100)
    second = await Rig(first.log, first.clock).start()
    assert [(b.slot, b.sent) for b in second.posts.records()] == [("BLN1", 2), ("BLNA", 2)] and [b.slot for b in second.changed] == ["BLN1", "BLNA"]
    second.run(400)
    assert [(t, info[1:5]) for t, info in second.sent] == [(130, b"BLN1"), (140, b"BLNA")], "each is due 240 seconds after its second packet; nothing is sent for the restart"


async def test_one_that_is_over_is_still_there_after_a_restart_and_sends_nothing(tmp_path: Path) -> None:
    first = await rig_at(tmp_path)
    first.posts.post("BLN1", "old news")
    first.run(5 * 3600)
    assert len(first.sent) == 14
    await first.settled()
    await first.posts.stop()
    second = await Rig(first.log, first.clock).start()
    [bulletin] = second.posts.records()
    assert (bulletin.slot, bulletin.sent) == ("BLN1", 14) and second.posts.next_at("BLN1") is None
    second.run(3600)
    assert second.sent == []


async def test_the_bulletins_are_kept_with_their_text_and_the_times_of_what_was_sent(tmp_path: Path) -> None:
    rig = await rig_at(tmp_path)
    rig.posts.post("BLN3HAMS", "Net tonight 20:00")
    rig.run(130)
    await rig.settled()
    [kept] = await rig.log.bulletins()
    assert kept == rig.posts.get("BLN3HAMS") and (kept.group, kept.kind, kept.sent, kept.first_sent_at, kept.last_sent_at) == ("HAMS", "group", 2, rig.begin, rig.begin + timedelta(seconds=120))
