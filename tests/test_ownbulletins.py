"""Our bulletins, announcements and group bulletins (neoaprs/services/ownbulletins.py) on stub radio
lines, a real log and a held clock: the schedule of each kind and Sent for, the slot a post takes,
delete, the radios they go out on, a restart and a clock set back.
"""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.config import NEW_BULLETIN_HOURS
from neoaprs.ownbulletin import MAX_POSTED, PostError
from neoaprs.ownlog import OwnLog
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.services.ownbulletins import OwnBulletins
from neoaprs.services.sender import Sender
from neoaprs.source import Source
from tests.support.clock import FixedClock
from tests.support.env import remember_stop
from tests.support.rig import OwnRig
from tests.support.seamshapes import LiveShape, RegistryShape
from neoaprs.store import Store
from tests.support.storedb import log_at
from tests.support.stubtnc import StubTnc


class Rig(OwnRig):
    """One run of the daemon's bulletins on the station's radios, radio 1's line `tnc` and radio 2's
    `hf`: made again on the same log and clock after a stop."""

    def __init__(self, log: OwnLog, clock: FixedClock, store: Store | None = None, **changes: object) -> None:
        super().__init__(log, clock, **changes)
        self.store = store
        self.hf = StubTnc()
        lines = {FM_ID: self.tnc, HF_ID: self.hf}
        self.sender = Sender(
            RegistryShape([LiveShape(spec, self.config.radios, lines[spec.id]) for spec in self.config.radios]),
            lambda: self.config,
            clock,
            spacing_sec=10.0,
        )  # type: ignore[arg-type]
        self.posts = OwnBulletins(self.sender, lambda: self.config, log, clock, tick_sec=3600.0, memory=store)
        self.record(self.posts)

    async def start(self) -> "Rig":
        await self.posts.start()
        remember_stop(self.posts.stop)
        return self

    def run(self, seconds: int, step: int = 5) -> None:
        """Looks at the clock every `step` seconds for this long, the first look now; the clock ends
        where the last look was."""
        self.look(self.posts.tick, seconds, step)


async def rig_at(tmp_path: Path, **changes: object) -> Rig:
    log, store, clock = await log_at(tmp_path, OwnLog)
    return await Rig(log, clock, store, **changes).start()


async def again(first: Rig, advance_sec: int = 0) -> Rig:
    """The same station stopped, off for `advance_sec` and started again."""
    await first.settled()
    await first.posts.stop()
    first.clock.advance(advance_sec)
    return await Rig(first.log, first.clock, first.store).start()


def refusal(rig: Rig, *args: object) -> tuple[str, dict[str, object]]:
    with pytest.raises(PostError) as refused:
        rig.posts.post(*args)  # type: ignore[arg-type]
    return refused.value.code, refused.value.params


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    return await rig_at(tmp_path)


async def test_a_bulletin_goes_out_at_once_after_2_and_6_minutes_and_then_every_20_minutes_for_4_hours_and_is_then_over(
    rig: Rig,
) -> None:
    posted = rig.posts.post("bulletin", "Road closed at Kaivopuisto")
    rig.run(5 * 3600)
    assert rig.offsets() == [0, 120, 360, *range(1560, 13561, 1200)] and len(rig.offsets()) == 14
    assert all(info == b":BLN0     :Road closed at Kaivopuisto" for _, info in rig.sent)
    ended = rig.posts.get("BLN0")
    assert ended is not None and ended.sent == 14 and rig.posts.next_at("BLN0") is None, (
        "it stays on the board as ended"
    )
    assert (
        posted.sent == 0
        and posted.hours == 4
        and ended.first_sent_at == rig.begin
        and ended.last_sent_at == rig.begin + timedelta(seconds=13560)
    )


async def test_an_announcement_goes_out_early_and_then_every_hour_for_72_hours(rig: Rig) -> None:
    rig.posts.post("announcement", "Club meeting on Thursday")
    rig.run(80 * 3600, step=60)
    offsets = rig.offsets()
    assert offsets[:6] == [0, 120, 360, 3960, 7560, 11160] and offsets[-1] == 360 + 71 * 3600 and len(offsets) == 3 + 71
    assert rig.posts.next_at("BLNA") is None


@pytest.mark.parametrize(("kind", "hours", "count"), [("bulletin", 8, 26), ("group", 1, 5), ("announcement", 24, 26)])
async def test_a_post_is_sent_for_its_hours_and_no_later(rig: Rig, kind: str, hours: int, count: int) -> None:
    posted = rig.posts.post(kind, "Net tonight", "HAMS", hours)  # type: ignore[arg-type]
    rig.run((hours + 2) * 3600, step=60)
    assert len(rig.sent) == count and rig.sent[-1][0] <= hours * 3600 < rig.sent[-1][0] + 3600
    assert rig.posts.next_at(posted.slot) is None and posted.hours == hours


async def test_a_group_bulletin_goes_to_its_group_by_the_beacons_path_on_the_bulletins_schedule(rig: Rig) -> None:
    rig.posts.post("group", "Net tonight 20:00", "hams")
    rig.run(400)
    assert rig.offsets() == [0, 120, 360]
    frame = rig.tnc.sent[0]
    assert frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1::BLN0HAMS :Net tonight 20:00" and frame.is_ui


@pytest.mark.parametrize(("table", "code", "path"), [("/", "-", "WIDE2-2"), ("/", ">", "WIDE1-1,WIDE2-1")])
async def test_a_bulletin_goes_by_the_recommended_path_of_the_stations_symbol(
    tmp_path: Path, table: str, code: str, path: str
) -> None:
    rig = await rig_at(tmp_path, beacon_path="", station_symbol_table=table, station_symbol_code=code)
    rig.posts.post("bulletin", "Net tonight")
    rig.run(10)
    assert rig.tnc.sent[0].path_text == path


async def test_the_next_time_is_told_and_what_is_overdue_says_so(rig: Rig) -> None:
    rig.posts.post("bulletin", "x")
    assert rig.posts.next_at("BLN0") == rig.begin, "due at once"
    rig.run(0)
    assert rig.posts.next_at("BLN0") == rig.begin + timedelta(seconds=120)
    assert rig.posts.next_at("BLN1") is None and rig.posts.get("BLN1") is None


async def test_each_post_takes_the_next_free_number_or_letter_and_nothing_of_ours_is_replaced(rig: Rig) -> None:
    posts = [
        rig.posts.post(*args)  # type: ignore[arg-type]
        for args in (("bulletin", "one"), ("bulletin", "one"), ("announcement", "a"), ("group", "g", "HAMS"))
    ]
    assert [b.slot for b in posts] == ["BLN0", "BLN1", "BLNA", "BLN0HAMS"]
    rig.run(10)
    assert [(b.slot, b.text) for b in rig.posts.records()] == [
        ("BLN0", "one"),
        ("BLN0HAMS", "g"),
        ("BLN1", "one"),
        ("BLNA", "a"),
    ]
    await rig.settled()
    assert [b.slot for b in await rig.log.bulletins()] == ["BLN0", "BLN0HAMS", "BLN1", "BLNA"]


async def test_an_ended_post_still_holds_its_slot_and_a_deleted_one_frees_it_for_the_next(rig: Rig) -> None:
    rig.posts.post("bulletin", "same", hours=1)
    rig.run(2 * 3600, step=60)
    assert rig.posts.next_at("BLN0") is None
    assert rig.posts.post("bulletin", "same").slot == "BLN1", "the ended one is not replaced"
    assert rig.posts.delete("BLN0")
    assert rig.posts.post("bulletin", "again").slot == "BLN0"


async def test_with_every_number_taken_a_bulletin_is_refused_and_nothing_is_stored_or_sent(rig: Rig) -> None:
    for n in range(10):
        rig.posts.post("bulletin", f"post {n}")
    assert refusal(rig, "bulletin", "one more") == ("bulletin.taken", {"kind": "bulletin", "group": ""})
    rig.run(200)
    assert len(rig.posts.records()) == 10 and not any(b"one more" in info for _, info in rig.sent)
    assert rig.posts.post("announcement", "a letter is free").slot == "BLNA"
    assert rig.posts.post("group", "a group is apart", "HAMS").slot == "BLN0HAMS"
    await rig.settled()
    assert len(await rig.log.bulletins()) == 12


async def test_a_group_takes_its_own_numbers_and_with_all_ten_taken_another_group_still_posts(rig: Rig) -> None:
    for n in range(10):
        assert rig.posts.post("group", f"net {n}", "HAMS").slot == f"BLN{n}HAMS"
    assert refusal(rig, "group", "one more", "hams") == ("bulletin.taken", {"kind": "group", "group": "HAMS"})
    assert rig.posts.post("group", "weather", "WX").slot == "BLN0WX"
    assert rig.posts.post("bulletin", "plain").slot == "BLN0", "BLN0HAMS does not take BLN0"
    assert rig.posts.delete("BLN4HAMS") and rig.posts.post("group", "back", "HAMS").slot == "BLN4HAMS"


async def test_with_every_letter_taken_an_announcement_is_refused(rig: Rig) -> None:
    for n in range(26):
        rig.posts.post("announcement", f"news {n}")
    assert refusal(rig, "announcement", "one more") == ("bulletin.taken", {"kind": "announcement", "group": ""})


async def test_deleting_a_bulletin_stops_it_and_takes_it_off_the_board_and_out_of_the_database(rig: Rig) -> None:
    rig.posts.post("bulletin", "gone")
    rig.posts.post("bulletin", "stays")
    rig.run(0)
    assert rig.posts.delete("BLN0") and not rig.posts.delete("BLN0") and not rig.posts.delete("BLN9")
    assert [b.slot for b in rig.removed] == ["BLN0"]
    rig.run(700)
    assert [info for _, info in rig.sent if b"gone" in info] == [b":BLN0     :gone"], (
        "it was sent once before it was deleted, never after"
    )
    await rig.settled()
    assert [b.slot for b in await rig.log.bulletins()] == ["BLN1"]


async def test_nothing_is_posted_while_the_call_is_not_set(tmp_path: Path) -> None:
    rig = await rig_at(tmp_path, station_call="")
    with pytest.raises(PostError, match="set your call first"):
        rig.posts.post("bulletin", "x")
    assert rig.posts.records() == [] and rig.tnc.sent == []


async def test_nothing_is_sent_while_the_call_is_gone_and_one_packet_goes_out_when_it_is_back(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    rig.posts.post("bulletin", "x")
    rig.config = replace(rig.config, station_call="")
    rig.run(1000)
    assert rig.tnc.sent == [] and "no bulletin sent" in caplog.text
    rig.config = replace(rig.config, station_call="OH2GBA")
    rig.run(0)
    assert rig.offsets() == [1000]


async def test_the_radio_that_is_silent_holds_it_back_and_it_is_not_made_up_when_the_radio_is_back(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    rig.posts.post("bulletin", "x")
    rig.run(0)
    rig.tnc.state = Source.State.SILENT
    rig.run(3000)
    assert rig.offsets() == [0] and caplog.text.count("is due and") == 1
    rig.tnc.state = Source.State.CONNECTED
    rig.run(100)
    assert rig.offsets() == [0, 3000], "one, not the ones that were due on the way"
    rig.run(1000)
    assert rig.offsets() == [0, 3000, 3000 + 240] and rig.posts.get("BLN0").sent == 3  # type: ignore[union-attr]


@pytest.mark.parametrize(("fm", "hf", "on"), [(True, True, "fm"), (True, False, "fm"), (False, True, "hf")])
async def test_a_new_bulletin_goes_on_the_first_radio_that_can_send_the_fm_one_while_it_is_on_else_the_hf_one_by_its_own_path(
    tmp_path: Path, fm: bool, hf: bool, on: str
) -> None:
    rig = await rig_at(tmp_path, fm_enabled=fm, hf_enabled=hf)
    rig.posts.post("bulletin", "Net tonight")
    rig.run(10)
    sent = rig.tnc.sent if on == "fm" else rig.hf.sent
    assert len(sent) == 1 and (rig.hf.sent if on == "fm" else rig.tnc.sent) == []
    assert sent[0].path_text == ("WIDE1-1,WIDE2-1" if on == "fm" else ""), "beacon/path on the FM radio, no path on HF"


async def test_the_post_boxs_ticks_go_with_the_text_and_a_post_without_ticks_starts_as_the_one_posted_last(
    tmp_path: Path,
) -> None:
    """What the Post box sends (BulletinCompose.vue: the radios ticked with every Post while several
    can send), counted per radio."""
    rig = await rig_at(tmp_path, fm_enabled=True, hf_enabled=True)
    rig.posts.post("bulletin", "Net tonight", radios=[FM_ID])
    rig.run(10)
    assert (len(rig.tnc.sent), len(rig.hf.sent)) == (1, 0)
    rig.posts.post("bulletin", "Net moved", radios=[HF_ID])
    rig.run(600)
    assert (len(rig.tnc.sent), len(rig.hf.sent)) == (3, 3), "each on its own radio from its first frame"
    assert rig.posts.get("BLN1").radios == (HF_ID,) and rig.posts.new_radios() == (HF_ID,)  # type: ignore[union-attr]
    assert rig.posts.post("bulletin", "Club news").radios == (HF_ID,), (
        "a new one with no ticks named: as the one posted last"
    )


async def test_a_text_a_group_or_a_sent_for_that_cannot_be_sent_is_refused_with_the_reason(rig: Rig) -> None:
    for args, code in (
        (("bulletin", ""), "message.empty"),
        (("bulletin", "x" * 68), "message.too_long"),
        (("group", "x", ""), "bulletin.group"),
        (("group", "x", "HAMS12"), "bulletin.group"),
        (("bulletin", "x", "", 3), "bulletin.hours"),
        (("bulletin", "x", "", 24), "bulletin.hours"),
        (("announcement", "x", "", 4), "bulletin.hours"),
    ):
        assert refusal(rig, *args)[0] == code, args
    with pytest.raises(PostError, match="forbidden|cannot carry|not allowed"):
        rig.posts.post("bulletin", "a|b")
    assert rig.posts.records() == []


async def test_there_is_a_limit_to_the_bulletins_posted_checked_before_the_slot(rig: Rig) -> None:
    for _ in range(10):
        rig.posts.post("bulletin", "x")
    for _ in range(26):
        rig.posts.post("announcement", "x")
    assert len(rig.posts.records()) == MAX_POSTED
    assert refusal(rig, "group", "x", "HAMS")[0] == "bulletin.full"
    assert refusal(rig, "group", "x", "")[0] == "bulletin.full", "before the group is looked at"


async def test_a_post_without_hours_takes_the_one_posted_last_of_its_kind_and_keeps_it_over_a_restart(
    tmp_path: Path,
) -> None:
    first = await rig_at(tmp_path)
    assert first.posts.new_hours() == {"bulletin": 4, "announcement": 72, "group": 4}
    assert first.posts.post("bulletin", "x", hours=8).hours == 8
    assert first.posts.post("announcement", "y", hours=168).hours == 168
    assert first.posts.post("bulletin", "z").hours == 8 and first.posts.post("group", "g", "HAMS").hours == 4
    assert first.posts.new_hours() == {"bulletin": 8, "announcement": 168, "group": 4}
    await first.posts._remembered.flush()
    second = await again(first)
    assert second.posts.new_hours() == {"bulletin": 8, "announcement": 168, "group": 4}, "both kinds kept"
    assert second.posts.post("announcement", "w").hours == 168


@pytest.mark.parametrize("stored", ["", "nonsense", "[4]", '{"bulletin": 3, "announcement": true, "group": "8"}'])
async def test_a_remembered_sent_for_that_cannot_be_read_is_the_default(tmp_path: Path, stored: str) -> None:
    first = await rig_at(tmp_path)
    assert first.store is not None and await first.store.put_settings({NEW_BULLETIN_HOURS: stored})
    second = await again(first)
    assert second.posts.new_hours() == {"bulletin": 4, "announcement": 72, "group": 4}


async def test_a_restart_goes_on_where_the_schedule_stopped_and_an_ended_one_stays_ended(tmp_path: Path) -> None:
    first = await rig_at(tmp_path)
    first.posts.post("bulletin", "kept")
    first.posts.post("announcement", "also kept")
    first.run(130)
    assert first.offsets() == [0, 10, 120, 130]
    second = await again(first, 100)
    assert [(b.slot, b.sent) for b in second.posts.records()] == [("BLN0", 2), ("BLNA", 2)] and [
        b.slot for b in second.changed
    ] == ["BLN0", "BLNA"]
    second.run(400)
    assert [(t, info[1:5]) for t, info in second.sent] == [(130, b"BLN0"), (140, b"BLNA")], (
        "each is due 240 seconds after its second packet; nothing is sent for the restart"
    )


async def test_a_12_hour_post_stopped_at_5_hours_goes_on_to_its_12_hours_after_a_restart(tmp_path: Path) -> None:
    first = await rig_at(tmp_path)
    first.posts.post("bulletin", "long", hours=12)
    first.run(5 * 3600, step=60)
    assert len(first.sent) == 17
    second = await again(first, 600)
    [kept] = second.posts.records()
    assert (kept.hours, kept.sent) == (12, 17)
    second.run(8 * 3600, step=60)
    assert len(first.sent) + len(second.sent) == 38 and second.posts.next_at("BLN0") is None
    assert (second.begin - first.begin).total_seconds() + second.sent[-1][0] <= 12 * 3600


async def test_a_post_whose_hours_ended_while_the_station_was_off_is_not_sent_at_the_start(tmp_path: Path) -> None:
    first = await rig_at(tmp_path)
    first.posts.post("bulletin", "old news")
    first.run(3 * 3600 + 1800, step=60)
    assert len(first.sent) == 13 and first.posts.next_at("BLN0") is not None, "one more was due at 3 h 46 min"
    second = await again(first, 6 * 3600)
    assert second.posts.next_at("BLN0") is None
    second.run(3600, step=60)
    assert second.sent == []


async def test_one_that_is_over_is_still_there_after_a_restart_and_sends_nothing(tmp_path: Path) -> None:
    first = await rig_at(tmp_path)
    first.posts.post("bulletin", "old news")
    first.run(5 * 3600)
    assert len(first.sent) == 14
    second = await again(first)
    [bulletin] = second.posts.records()
    assert (bulletin.slot, bulletin.sent) == ("BLN0", 14) and second.posts.next_at("BLN0") is None
    second.run(3600)
    assert second.sent == []


async def test_a_clock_set_back_after_the_first_packets_sends_at_once_and_counts_its_hours_from_then(
    rig: Rig,
) -> None:
    rig.posts.post("bulletin", "x")
    rig.run(400)
    assert rig.offsets() == [0, 120, 360]
    rig.clock.advance(-3 * 3600)
    back = round((rig.clock() - rig.begin).total_seconds())
    assert rig.posts.next_at("BLN0") == rig.clock(), "not held off for the three hours"
    rig.run(1300)
    assert rig.offsets()[3:] == [back, back + 1200]
    await rig.settled()
    [kept] = await rig.log.bulletins()
    assert (kept.slot, kept.sent) == ("BLN0", 5) and kept.first_sent_at == rig.begin + timedelta(seconds=back)
    assert kept.last_sent_at == kept.first_sent_at + timedelta(seconds=1200), "the row is stored, in order"
    rig.run(5 * 3600, step=60)
    assert rig.offsets()[-1] - back <= 4 * 3600 and rig.posts.next_at("BLN0") is None
    assert rig.posts.post("bulletin", "y").slot == "BLN1", "the slot stays taken"


async def test_an_ended_post_stays_ended_when_the_clock_is_set_back(rig: Rig) -> None:
    rig.posts.post("bulletin", "x", hours=1)
    rig.run(2 * 3600, step=60)
    rig.clock.advance(-3 * 3600)
    assert rig.posts.next_at("BLN0") is None


async def test_the_bulletins_are_kept_with_their_text_hours_and_the_times_of_what_was_sent(tmp_path: Path) -> None:
    rig = await rig_at(tmp_path)
    rig.posts.post("group", "Net tonight 20:00", "HAMS", 2)
    rig.run(130)
    await rig.settled()
    [kept] = await rig.log.bulletins()
    assert kept == rig.posts.get("BLN0HAMS") and (
        kept.group,
        kept.kind,
        kept.hours,
        kept.sent,
        kept.first_sent_at,
        kept.last_sent_at,
    ) == ("HAMS", "group", 2, 2, rig.begin, rig.begin + timedelta(seconds=120))


async def test_a_clock_set_back_far_and_right_again_leaves_a_fresh_post_live(rig: Rig) -> None:
    rig.posts.post("bulletin", "x")
    rig.run(400)
    before = len(rig.sent)
    rig.clock.advance(-20 * 365 * 86400)
    rig.posts.tick()
    assert len(rig.sent) <= before + 1
    rig.clock.advance(20 * 365 * 86400)
    next_at = rig.posts.next_at("BLN0")
    assert next_at is not None and next_at > rig.clock()
    rig.run(1500, step=60)
    assert len(rig.sent) <= before + 2, "the schedule goes on"
    assert rig.posts.next_at("BLN0") is not None


async def test_a_never_sent_post_goes_out_when_the_clock_is_set_back_before_its_creation(rig: Rig) -> None:
    rig.posts.post("bulletin", "x")
    rig.clock.advance(-3 * 3600)
    assert rig.posts.next_at("BLN0") == rig.clock()


async def test_a_step_back_of_a_second_just_after_a_send_does_not_repeat_the_packet(rig: Rig) -> None:
    rig.posts.post("bulletin", "x")
    rig.run(125)
    sent = len(rig.sent)
    rig.clock.advance(-6)
    next_at = rig.posts.next_at("BLN0")
    assert next_at is not None and next_at > rig.clock()
    rig.posts.tick()
    assert len(rig.sent) == sent
