"""The random pause before every send by the clock (neoaprs/pause.py): its size by radio type, one draw
for each send, the slots that do not stretch, the start, and the beacon, the status and our objects.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from neoaprs import pause
from neoaprs.decay import Plan
from neoaprs.ownlog import OwnLog
from neoaprs.ownobject import OwnObject
from neoaprs.radiospec import FM_ID, HF_ID
from neoaprs.radiotypes.common import FM_LIMITS, HF_LIMITS, LORA_LIMITS
from neoaprs.rigctld import Reading, RigError
from neoaprs.services.beacon import Beacon
from neoaprs.services.beaconframe import BeaconFrames
from neoaprs.services.ownbulletins import END_MARGIN_SEC, OwnBulletins
from neoaprs.services.ownobjects import OwnObjects
from neoaprs.services.rigstatus import RigStatus
from neoaprs.services.sender import Sender
from tests.support.clock import FixedClock
from tests.support.env import idle_for, remember_stop, until
from tests.support.radioconfig import with_radio
from tests.support.rig import OwnRig, ServiceRig
from tests.support.seamshapes import LiveShape, RegistryShape
from tests.support.storedb import log_at
from tests.support.stubtnc import StubTnc
from tests.test_beaconframe import radio_of


class Draws:
    """A jitter that gives these shares of the most in turn (the last one again after them) and
    counts its calls."""

    def __init__(self, *shares: float) -> None:
        self.shares = shares
        self.calls: list[float] = []

    def __call__(self, most: float) -> float:
        self.calls.append(most)
        return self.shares[min(len(self.calls), len(self.shares)) - 1] * most


def seconds(times: list[datetime], start: datetime) -> list[float]:
    return [(t - start).total_seconds() for t in times]


# ---- the pause itself ----------------------------------------------------------------------------


def test_the_share_is_the_draw_over_the_most_and_zero_without_a_pause() -> None:
    draws = Draws(0.5)
    assert pause.share(draws, 0) == 0.0 and draws.calls == [], "no pause: the jitter is not asked"
    assert pause.share(draws, 30) == 0.5 and draws.calls == [30]
    assert pause.share(lambda most: -5.0, 30) == 0.0 and pause.share(lambda most: 999.0, 30) == 1.0, "clamped"


def test_the_pause_is_capped_by_the_smallest_room_and_spread_evenly() -> None:
    assert pause.capped(0.5, 300, 60) == timedelta(seconds=30), "an early repeat of 60 s waits half of 60 s"
    assert pause.capped(0.5, 300) == timedelta(seconds=150)
    assert pause.capped(1.0, 300, 1200, 100) == timedelta(seconds=100), "the end of a bulletin is a room too"
    assert pause.capped(1.0, 300, -5) == timedelta(0), "no room: no pause"
    start = FixedClock()()
    assert pause.latest(start, start + timedelta(seconds=40)) == 40 and pause.latest(start, None) == float("inf")


def test_a_send_in_its_slot_keeps_the_slot_and_one_later_counts_from_when_it_went() -> None:
    slot = datetime(2026, 11, 22, 12, 0, tzinfo=FixedClock()().tzinfo)
    assert pause.anchor((slot, 30), slot + timedelta(seconds=30)) == slot, "within the pause: the slot"
    assert pause.anchor((slot, 30), slot + timedelta(seconds=31)) == slot + timedelta(seconds=31), "late: the send"
    assert pause.anchor((slot, 30), slot - timedelta(hours=1)) == slot - timedelta(hours=1), "a clock set back"
    assert pause.anchor(None, slot) == slot


def test_fm_pauses_up_to_30_s_and_hf_and_lora_up_to_300_s() -> None:
    assert (FM_LIMITS.beacon_jitter_sec, HF_LIMITS.beacon_jitter_sec, LORA_LIMITS.beacon_jitter_sec) == (30, 300, 300)


def test_the_tests_draw_no_pause_unless_they_ask_for_the_real_one() -> None:
    assert pause.draw(30) == 0.0 and pause.draw is not pause.uniform


def test_the_shipped_draw_is_random_and_within_the_most(real_pauses: None) -> None:
    assert pause.draw is pause.uniform
    for most in (30, 300):
        values = [pause.draw(most) for _ in range(500)]
        assert all(0 <= v <= most for v in values) and len(set(values)) >= 400
        assert abs(sum(values) / len(values) - most / 2) <= most / 10


# ---- the beacon ----------------------------------------------------------------------------------


class BeaconRig(ServiceRig):
    """One radio's beacon whose timer is looked at by the test (`tick`), never by itself."""

    def __init__(self, radio: int = FM_ID, **changes: object) -> None:
        super().__init__(**{"beacon_interval_min": 20, "hf_enabled": radio == HF_ID, **changes})
        self.tnc = StubTnc(max_frame=123) if radio == HF_ID else self.tnc
        frames = BeaconFrames(lambda: self.config, None, self.clock)
        self.beacon = Beacon(radio_of(self.config, radio, self.tnc), lambda: self.config, self.clock, frames=frames)
        self.beacon.tick_sec = 3600.0
        self.start = self.clock()
        self.sends: list[datetime] = []
        self.beacon.sent.connect(lambda frame: self.sends.append(self.clock()))

    async def started(self, jitter: pause.Draw | None = None) -> "BeaconRig":
        if jitter is not None:
            self.beacon.jitter = jitter
        await self.beacon.start()
        remember_stop(self.beacon.stop)
        return self

    def run(self, seconds: int) -> list[float]:
        """Looks once a second for this long; the seconds from the start at which a beacon went."""
        for _ in range(seconds):
            self.beacon._tick()
            self.clock.advance(1)
        return seconds_of(self)


def seconds_of(rig: BeaconRig) -> list[float]:
    return seconds(rig.sends, rig.start)


async def test_an_fm_beacon_waits_its_pause_in_each_slot_and_the_slots_do_not_stretch() -> None:
    draws = Draws(1.0, 0.5, 0.0, 0.25)
    rig = await BeaconRig().started(draws)
    assert rig.run(3 * 1200 + 60) == [60, 30 + 1200 + 15, 30 + 2400, 30 + 3600 + 8], (
        "the first 30 s and its pause, then each 20 minutes from the slot before, not from the send"
    )
    assert draws.calls == [30] * 5, "one draw for each beacon planned, none at the ticks between"


async def test_the_first_beacon_after_a_start_waits_30_s_and_the_radios_pause() -> None:
    fm = await BeaconRig(FM_ID).started(Draws(1.0))
    hf = await BeaconRig(HF_ID, beacon_interval_min=30).started(Draws(1.0))
    assert (fm.beacon.next_due, hf.beacon.next_due) == (
        fm.start + timedelta(seconds=30 + 30),
        hf.start + timedelta(seconds=30 + 300),
    )


async def test_a_clock_set_back_keeps_the_planned_beacon_and_draws_no_new_pause() -> None:
    draws = Draws(0.5)
    rig = await BeaconRig().started(draws)
    due = rig.beacon.next_due
    rig.clock.advance(-3600)
    rig.run(10)
    assert rig.beacon.next_due == due and len(draws.calls) == 1 and rig.sends == []


async def test_beacon_now_is_not_paused_and_the_next_counts_from_it() -> None:
    rig = await BeaconRig().started(Draws(1.0))
    rig.clock.advance(10)
    assert rig.beacon.send_now() and seconds_of(rig) == [10]
    assert rig.beacon.next_due == rig.clock() + timedelta(minutes=20, seconds=30)


async def test_a_beacon_late_past_its_pause_counts_from_when_it_went() -> None:
    rig = await BeaconRig().started(Draws(0.0))
    rig.tnc.state = rig.tnc.state.WAITING
    rig.run(200)
    rig.tnc.state = rig.tnc.state.CONNECTED
    rig.run(1)
    assert seconds_of(rig) == [200] and rig.beacon.next_due == rig.start + timedelta(seconds=200 + 1200)


async def test_a_restart_draws_a_new_pause_from_the_stored_last_send() -> None:
    draws = Draws(0.5)
    rig = BeaconRig()
    rig.beacon.jitter = draws
    rig.beacon._earlier, rig.beacon._started = rig.start - timedelta(minutes=10), rig.start
    rig.beacon._plan(20)
    assert rig.beacon.next_due == rig.start + timedelta(minutes=10, seconds=15) and draws.calls == [30]


async def test_beacons_of_two_stations_with_the_same_clock_and_last_send_go_at_different_times(
    real_pauses: None,
) -> None:
    one, two = BeaconRig(), BeaconRig()
    planned = []
    for rig in (one, two, *[BeaconRig() for _ in range(18)]):
        rig.beacon.last_sent, rig.beacon._started = rig.start, rig.start
        rig.beacon._plan(20)
        assert rig.beacon.next_due is not None
        planned.append((rig.beacon.next_due - rig.start - timedelta(minutes=20)).total_seconds())
    assert planned[0] != planned[1] and all(0 <= p <= 30 for p in planned) and len(set(planned)) >= 15


# ---- the status ----------------------------------------------------------------------------------


class StatusRig(ServiceRig):
    """The status on radio 1 (FM, `tnc`) and radio 2 (HF, `hf`), by the station's text unless a
    reader is given; its timer is looked at by the test (`tick`), its poll too."""

    def __init__(self, both: bool = False, read: object = None, **changes: object) -> None:
        super().__init__(**{"beacon_interval_min": 30, "station_status": "QRV", "hf_enabled": both, **changes})
        if both:
            self.config = with_radio(with_radio(self.config, FM_ID, status=True), HF_ID, status=True)
        self.hf = StubTnc(max_frame=123)
        radios = RegistryShape([radio_of(self.config, FM_ID, self.tnc), radio_of(self.config, HF_ID, self.hf)])
        options = {} if read is None else {"read": read}
        frames = BeaconFrames(lambda: self.config, None, self.clock)
        self.status = RigStatus(radios, lambda: self.config, frames, self.clock, poll_sec=30, **options)  # type: ignore[arg-type]
        self.status.tick_sec = 3600.0
        self.start = self.clock()
        remember_stop(self.status.stop)

    async def started(self, jitter: pause.Draw) -> "StatusRig":
        self.status.jitter = jitter
        # (its own polls an hour apart, the first at the start: it reads, and offers what is due)
        self.status.poll_sec = 3600.0
        await self.status.start()
        self.status.poll_sec = 30.0
        await until(lambda: self.status._text_at is not None)
        return self

    def run(self, seconds: int) -> None:
        for _ in range(seconds):
            self.clock.advance(1)
            self.status._tick()
            self.note()

    async def poll(self) -> None:
        await self.status.poll()
        self.note()

    def note(self) -> None:
        """Gives each frame the lines took since the last note the clock's time."""
        for line in (self.tnc, self.hf):
            times = self.times.setdefault(id(line), [])
            times += [self.clock()] * (len(line.sent) - len(times))

    def at(self, line: StubTnc) -> list[float]:
        """The seconds from the start at which a report went on the line."""
        self.note()
        return [(t - self.start).total_seconds() for t in self.times[id(line)]]

    def watch(self) -> "StatusRig":
        self.times: dict[int, list[datetime]] = {}
        self.note()
        return self


async def test_the_status_waits_each_radios_own_pause() -> None:
    draws = Draws(1.0)
    rig = await StatusRig(both=True).watch().started(draws)
    rig.run(400)
    assert (rig.at(rig.tnc), rig.at(rig.hf)) == ([30], [300]), "FM 30 s, HF 300 s after the start"
    assert draws.calls == [30, 300, 30, 300], "one draw for each radio's report, then for its next"


async def test_the_first_status_after_a_start_waits_the_pause_also_when_the_last_was_long_ago() -> None:
    rig = StatusRig(both=True).watch()
    rig.status.sent_on[FM_ID] = rig.start - timedelta(hours=2)
    rig.status.sent_on[HF_ID] = rig.start - timedelta(hours=2)
    await rig.started(Draws(1.0))
    assert rig.status.on_radio(HF_ID)[1] == rig.start + timedelta(seconds=300), "the page is told the same time"
    rig.run(400)
    assert (rig.at(rig.tnc), rig.at(rig.hf)) == ([30], [300])


async def test_each_status_draws_anew_and_the_slots_do_not_stretch() -> None:
    draws = Draws(1.0, 0.0, 0.5)
    rig = await StatusRig().watch().started(draws)
    rig.run(3 * 1800 + 60)
    assert rig.at(rig.tnc) == [30, 1800, 3600 + 15, 5400 + 15], "each 30 minutes from its slot, each its own pause"
    assert len(draws.calls) == 5


async def test_status_now_is_not_paused_and_the_next_after_it_is() -> None:
    rig = await StatusRig().watch().started(Draws(1.0))
    rig.run(5)
    assert await rig.status.send_now() == "" and rig.at(rig.tnc) == [5]
    assert rig.status.on_radio(FM_ID)[1] == rig.start + timedelta(seconds=5 + 1800 + 30)
    rig.run(1800 + 40)
    assert rig.at(rig.tnc) == [5, 5 + 1800 + 30]


async def test_the_status_is_checked_every_second_so_the_fm_pause_counts() -> None:
    rig = StatusRig().watch()
    rig.status.jitter = Draws(17 / 30)
    rig.status.poll_sec, rig.status.tick_sec = 3600.0, 0.01
    await rig.status.start()
    rig.clock.advance(16)
    await idle_for(0.1)
    assert rig.at(rig.tnc) == []
    rig.clock.advance(1)
    await until(lambda: rig.at(rig.tnc) == [17])


async def test_a_status_turned_off_or_a_radio_gone_away_is_not_sent_from_the_last_poll() -> None:
    answers: list[Reading | None] = [Reading(14074000, "USB")]

    async def read(host: str, port: int) -> Reading:
        if (reading := answers[-1]) is None:
            raise RigError("no answer")
        return reading

    rig = StatusRig(read=read, status_source="rig", status_rigctld="localhost:4532").watch()
    await rig.started(Draws(1.0))
    rig.run(40)
    assert rig.at(rig.tnc) == [30], "the timer sends the reading of the poll before"
    rig.run(1700 - 40)
    await rig.poll()
    rig.run(140)
    assert rig.at(rig.tnc) == [30], "due at 1830: a reading older than two polls is not sent"
    answers.append(None)
    await rig.poll()
    rig.run(40)
    assert rig.at(rig.tnc) == [30], "the radio went away: nothing from the reading before"
    answers.append(Reading(14074000, "USB"))
    await rig.poll()
    assert rig.at(rig.tnc) == [30, 1880], "the poll that finds it again sends"
    rig.run(3700 - 1880)
    await rig.poll()
    rig.set(status_rigctld="")
    rig.run(20)
    assert rig.at(rig.tnc) == [30, 1880], "due at 3710: the rig's address cleared"
    text = await StatusRig().watch().started(Draws(1.0))
    text.set(station_status="")
    text.run(40)
    assert text.at(text.tnc) == [], "the station's text cleared"


async def test_a_refused_status_is_tried_again_at_the_polls_rhythm_not_at_every_tick() -> None:
    rig = StatusRig().watch()
    rig.tnc.takes = False
    await rig.started(Draws(0.0))
    rig.run(29)
    assert rig.tnc.asked == 1, "at the start, then not at the ticks before the next poll"
    rig.run(2)
    assert rig.tnc.asked == 2
    rig.tnc.takes = True
    await rig.poll()
    assert rig.at(rig.tnc) == [31]


def test_the_status_of_two_stations_with_the_same_clock_goes_at_different_times(real_pauses: None) -> None:
    times = []
    for _ in range(2):
        rig = StatusRig()
        rig.status._started = rig.start
        radio = rig.status._targets(rig.config)[0][1]
        times.append(rig.status._due_at(FM_ID, radio, 30))
    assert times[0] != times[1] and all(rig.start <= t <= rig.start + timedelta(seconds=30) for t in times)


# ---- our objects ---------------------------------------------------------------------------------


class ObjectRig(OwnRig):
    """Our objects on radio 1 (FM, `tnc`) and radio 2 (HF, `hf`), looked at once a second."""

    def __init__(self, log: OwnLog, clock: FixedClock, **changes: object) -> None:
        super().__init__(log, clock, **{"fm_enabled": True, "hf_enabled": True, **changes})
        self.hf = StubTnc()
        lines = {FM_ID: self.tnc, HF_ID: self.hf}
        self.shapes = [LiveShape(spec, self.config.radios, lines[spec.id]) for spec in self.config.radios]  # type: ignore[arg-type]
        self.sender = Sender(RegistryShape(self.shapes), lambda: self.config, clock, spacing_sec=0.0)
        self.objects = OwnObjects(self.sender, lambda: self.config, log, clock=clock, tick_sec=3600.0)

    async def started(self, jitter: pause.Draw) -> "ObjectRig":
        self.objects.jitter = jitter
        await self.objects.start()
        remember_stop(self.objects.stop)
        return self

    def make(self, name: str, radios: tuple[int, ...], **values: object) -> OwnObject:
        return self.objects.set(name, "object", 60.2, 24.9, "/", ">", radios=radios, **values)  # type: ignore[arg-type]

    def timed(self, seconds: int) -> dict[str, list[int]]:
        """Looks once a second for this long, the first now: when something went on `fm` and `hf`."""
        out: dict[str, list[int]] = {"fm": [], "hf": []}
        begin = self.clock()
        for t in range(seconds + 1):
            before = {"fm": len(self.tnc.sent), "hf": len(self.hf.sent)}
            self.objects.tick()
            for word, line in (("fm", self.tnc), ("hf", self.hf)):
                out[word] += [t] * (len(line.sent) - before[word])
            self.clock.advance(1)
        self.clock.advance(-1)
        assert self.clock() == begin + timedelta(seconds=seconds)
        return out


async def objects_at(tmp_path: Path, jitter: pause.Draw, **changes: object) -> ObjectRig:
    log, _, clock = await log_at(tmp_path, OwnLog)
    return await ObjectRig(log, clock, **changes).started(jitter)


async def again(first: ObjectRig, jitter: pause.Draw, off_sec: int, **changes: object) -> ObjectRig:
    """The same station stopped, off for `off_sec` and started again."""
    await first.settled()
    await first.objects.stop()
    first.clock.advance(off_sec)
    return await ObjectRig(first.log, first.clock, **changes).started(jitter)


async def test_a_repeat_waits_the_pause_of_its_radio_type_never_longer_than_its_wait(tmp_path: Path) -> None:
    rig = await objects_at(tmp_path, Draws(1.0))
    rig.make("FMONLY", (FM_ID,))
    rig.make("HFONLY", (HF_ID,))
    out = rig.timed(4000)
    assert out["fm"] == [0, 90, 210, 450, 930, 1890, 3090], (
        "slots at 1, 3, 7, 15, 31 minutes, then the net cycle of 20; each 30 s into its slot"
    )
    assert out["hf"] == [1, 121, 301, 661, 1201, 2161, 3961], (
        "a second after FM's (one thing a tick): slots at 1, 3, 7, 15, 31, 61 minutes (HF's floor of 30), a pause as long as the wait, five minutes at most"
    )


async def test_each_repeat_of_an_object_draws_anew_and_a_look_draws_nothing(tmp_path: Path) -> None:
    draws = Draws(0.1, 0.5, 0.9)
    rig = await objects_at(tmp_path, draws)
    rig.make("HFONLY", (HF_ID,))
    for _ in range(5):
        rig.objects.next_at("HFONLY")
    out = rig.timed(700)
    for _ in range(5):
        rig.objects.next_at("HFONLY")
    assert out["hf"] == [0, 66, 240, 636] and draws.calls == [300] * 4, (
        "one draw for each repeat (and the next one planned), none for the first packet, a look or a tick"
    )


async def test_a_new_changed_or_killed_object_goes_at_once_and_its_repeats_are_paused(tmp_path: Path) -> None:
    rig = await objects_at(tmp_path, Draws(1.0))
    rig.make("HFONLY", (HF_ID,))
    assert rig.timed(10)["hf"] == [0]
    rig.make("HFONLY", (HF_ID,), comment="moved")
    assert rig.timed(60)["hf"] == [50], "changed: a minute after its last packet, with no pause"
    rig.objects.kill("HFONLY")
    out = rig.timed(400)
    assert out["hf"] == [50, 170, 350] and rig.objects.get("HFONLY") is None, (
        "killed: a minute after its last packet with no pause, then 60 and 120 s on, each with a pause as long as its wait"
    )


async def test_an_object_on_fm_and_hf_waits_one_pause_the_larger_and_goes_in_one_round(tmp_path: Path) -> None:
    draws = Draws(0.5)
    rig = await objects_at(tmp_path, draws)
    rig.make("BOTH", (FM_ID, HF_ID))
    out = rig.timed(400)
    assert out["fm"] == out["hf"] == [0, 90, 240], "HF's five minutes cap: half the wait, on both in the same tick"
    assert set(draws.calls) == {300}


async def test_an_object_due_at_a_start_waits_the_pause_after_the_start(tmp_path: Path) -> None:
    first = await objects_at(tmp_path, Draws(0.0))
    first.make("HFONLY", (HF_ID,))
    first.timed(4000)
    draws = Draws(0.5)
    rig = await again(first, draws, 2 * 3600)
    assert rig.objects.next_at("HFONLY") == rig.clock() + timedelta(seconds=150)
    assert rig.timed(200)["hf"] == [150] and draws.calls == [300, 300]


async def test_the_page_is_told_the_paused_time_of_an_object_at_the_start(tmp_path: Path) -> None:
    first = await objects_at(tmp_path, Draws(0.0))
    first.make("HFONLY", (HF_ID,))
    first.timed(4000)
    await first.settled()
    await first.objects.stop()
    first.clock.advance(2 * 3600)
    rig = ObjectRig(first.log, first.clock)
    told: list[datetime | None] = []
    rig.objects.changed.connect(lambda obj: told.append(rig.objects.next_at(obj.name)))
    await rig.started(Draws(0.5))
    assert told == [rig.clock() + timedelta(seconds=150)]


async def test_an_object_not_yet_due_at_a_start_keeps_its_paused_time(tmp_path: Path) -> None:
    first = await objects_at(tmp_path, Draws(0.0))
    first.make("HFONLY", (HF_ID,))
    first.timed(3000)
    last = first.objects.get("HFONLY").last_sent_at  # type: ignore[union-attr]
    assert last is not None
    rig = await again(first, Draws(0.5), 60)
    assert rig.objects.next_at("HFONLY") == last + timedelta(seconds=1800 + 150)


async def test_an_object_with_no_radio_up_at_the_start_still_waits_from_the_start(tmp_path: Path) -> None:
    first = await objects_at(tmp_path, Draws(0.0))
    first.make("HFONLY", (HF_ID,))
    first.timed(4000)
    draws = Draws(0.5)
    rig = await again(first, draws, 2 * 3600, fm_enabled=False, hf_enabled=False)
    start = rig.clock()
    rig.timed(10)
    assert draws.calls == [300], "the pause of the radio it is set for, drawn while no radio is up"
    rig.set(hf_enabled=True)
    for shape in rig.shapes:
        shape.spec, shape.specs = rig.config.radio(shape.id) or shape.spec, rig.config.radios
    assert rig.objects.next_at("HFONLY") == start + timedelta(seconds=150) and draws.calls == [300]


async def test_a_new_object_after_the_clock_is_set_back_goes_at_once(tmp_path: Path) -> None:
    first = await objects_at(tmp_path, Draws(0.0))
    first.make("OLD", (HF_ID,))
    first.timed(4000)
    rig = await again(first, Draws(0.5), 2 * 3600)
    rig.objects.next_at("OLD")
    rig.clock.advance(-3600)
    rig.make("NEW", (HF_ID,))
    out = rig.timed(160)
    assert out["hf"] == [0, 90, 150], (
        "the new one at once and its repeat paused; the old one waits its pause from the clock as it is now"
    )


async def test_objects_of_two_stations_loaded_at_the_same_start_go_at_different_times(
    tmp_path: Path, real_pauses: None
) -> None:
    times = []
    for name in ("one", "two"):
        (tmp_path / name).mkdir()
        first = await objects_at(tmp_path / name, pause.draw)
        first.make("HFONLY", (HF_ID,))
        first.timed(100)
        rig = await again(first, pause.draw, 3600)
        times.append(rig.objects.next_at("HFONLY"))
    assert times[0] != times[1]


# ---- our bulletins -------------------------------------------------------------------------------


class BulletinRig(OwnRig):
    """Our bulletins on radio 1 (FM, `tnc`) and radio 2 (HF, `hf`), looked at once a second."""

    def __init__(self, log: OwnLog, clock: FixedClock, **changes: object) -> None:
        super().__init__(log, clock, **{"fm_enabled": True, "hf_enabled": True, **changes})
        self.hf = StubTnc()
        lines = {FM_ID: self.tnc, HF_ID: self.hf}
        self.shapes = [LiveShape(spec, self.config.radios, lines[spec.id]) for spec in self.config.radios]  # type: ignore[arg-type]
        self.sender = Sender(RegistryShape(self.shapes), lambda: self.config, clock, spacing_sec=0.0)
        self.posts = OwnBulletins(self.sender, lambda: self.config, log, clock, tick_sec=3600.0)

    def timed(self, seconds: int) -> list[int]:
        """Looks once a second for this long, the first now: when something went, on either line."""
        out: list[int] = []
        for t in range(seconds + 1):
            before = len(self.tnc.sent) + len(self.hf.sent)
            self.posts.tick()
            out += [t] * (len(self.tnc.sent) + len(self.hf.sent) - before)
            self.clock.advance(1)
        self.clock.advance(-1)
        return out


async def bulletins_at(tmp_path: Path, jitter: pause.Draw) -> BulletinRig:
    log, _, clock = await log_at(tmp_path, OwnLog)
    rig = BulletinRig(log, clock)
    rig.posts.jitter = jitter
    await rig.posts.start()
    remember_stop(rig.posts.stop)
    return rig


@pytest.mark.parametrize(
    ("radio", "hours", "count"),
    [(FM_ID, 4, 3 + 11), (HF_ID, 4, 3 + 7), (FM_ID, 1, 3 + 2), (HF_ID, 1, 3 + 1)],
    ids=["fm-4h", "hf-4h", "fm-1h", "hf-1h"],
)
async def test_the_largest_pause_loses_no_packet_of_the_plan_and_none_goes_after_the_end(
    tmp_path: Path, radio: int, hours: int, count: int
) -> None:
    rig = await bulletins_at(tmp_path, Draws(1.0))
    rig.posts.post("bulletin", "NET TONIGHT", hours=hours, radios=(radio,))
    out = rig.timed(hours * 3600 + 900)
    assert len(out) == count and out[-1] <= hours * 3600, (
        f"once, after 2 and 6 minutes, then every {20 if radio == FM_ID else 30} minutes of its slots: {out}"
    )


async def test_a_new_post_goes_at_once_and_its_repeats_are_paused(tmp_path: Path) -> None:
    rig = await bulletins_at(tmp_path, Draws(1.0))
    rig.posts.post("bulletin", "NET TONIGHT", hours=1, radios=(FM_ID,))
    assert rig.timed(1600) == [0, 150, 390, 1590], "slots at 0, 2, 6 and 26 minutes, each 30 s into it"


async def test_a_post_deleted_and_made_anew_draws_a_new_pause(tmp_path: Path) -> None:
    draws = Draws(0.2, 0.8)
    rig = await bulletins_at(tmp_path, draws)
    posted = rig.posts.post("bulletin", "NET TONIGHT", hours=1, radios=(FM_ID,))
    out = rig.timed(130)
    assert rig.posts.delete(posted.slot)
    rig.posts.post("bulletin", "NET TOMORROW", hours=1, radios=(FM_ID,))
    out += [130 + t for t in rig.timed(200)]
    assert out == [0, 126, 130, 274], "the new post at once, its repeat with a pause of its own"


async def test_the_pause_ends_before_the_end_of_the_bulletin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.ownbulletin.bulletin_plan", lambda announcement, hours: Plan((120, 240), 1200, 400))
    rig = await bulletins_at(tmp_path, Draws(1.0))
    rig.posts.post("bulletin", "NET TONIGHT", hours=1, radios=(HF_ID,))
    assert rig.timed(800) == [0, 240, 400 - END_MARGIN_SEC], (
        "the last slot at 6 minutes, 40 s before the end: its pause is the room left, less the margin"
    )


# ---- a clock stepped forward, a radio that comes up late, the page's time -------------------------


async def test_a_clock_stepped_forward_keeps_the_first_beacons_pause() -> None:
    rig = await BeaconRig(HF_ID, beacon_interval_min=30).started(Draws(0.5))
    rig.run(10)
    rig.clock.step(3600)
    assert rig.run(400) == [3600 + 30 + 150], "the start's 30 s and the drawn 150 s, counted on from the step"


async def test_a_clock_stepped_forward_keeps_the_first_status_pause() -> None:
    rig = await StatusRig(both=True).watch().started(Draws(0.5))
    rig.run(5)
    rig.clock.step(7200)
    rig.run(400)
    assert (rig.at(rig.tnc), rig.at(rig.hf)) == ([7200 + 15], [7200 + 150])


async def test_a_clock_stepped_forward_keeps_the_pause_of_an_object_loaded_at_the_start(tmp_path: Path) -> None:
    first = await objects_at(tmp_path, Draws(0.0))
    first.make("HFONLY", (HF_ID,))
    first.timed(4000)
    rig = await again(first, Draws(0.5), 2 * 3600)
    rig.timed(5)
    rig.clock.step(3 * 3600)
    assert rig.timed(200)["hf"] == [145], "150 s from the start, the start moved on by the step"


async def test_a_beacon_whose_radio_comes_up_after_its_pause_waits_the_pause_from_then() -> None:
    rig = await BeaconRig(HF_ID, beacon_interval_min=30).started(Draws(0.5))
    rig.tnc.state = rig.tnc.state.WAITING
    rig.run(400)
    rig.tnc.state = rig.tnc.state.CONNECTED
    assert rig.run(200) == [400 + 150]


async def test_a_status_whose_radio_comes_up_after_its_pause_waits_the_pause_from_then() -> None:
    rig = StatusRig(both=True).watch()
    rig.hf.state = rig.hf.state.WAITING
    await rig.started(Draws(0.5))
    rig.run(400)
    rig.hf.state = rig.hf.state.CONNECTED
    rig.run(200)
    assert (rig.at(rig.tnc), rig.at(rig.hf)) == ([15], [401 + 150])


async def test_an_object_whose_radio_comes_up_after_its_pause_waits_the_pause_from_then(tmp_path: Path) -> None:
    first = await objects_at(tmp_path, Draws(0.0))
    first.make("HFONLY", (HF_ID,))
    first.timed(4000)
    rig = await again(first, Draws(0.5), 2 * 3600, fm_enabled=False, hf_enabled=False)
    rig.timed(400)
    rig.set(hf_enabled=True)
    for shape in rig.shapes:
        shape.spec, shape.specs = rig.config.radio(shape.id) or shape.spec, rig.config.radios
    assert rig.objects.next_at("HFONLY") == rig.clock() + timedelta(seconds=150)
    assert rig.timed(200)["hf"] == [150]


async def test_the_next_time_of_an_object_does_not_move_when_one_of_its_radios_drops(tmp_path: Path) -> None:
    rig = await objects_at(tmp_path, Draws(1.0))
    rig.make("BOTH", (FM_ID, HF_ID))
    rig.timed(5)
    shown = rig.objects.next_at("BOTH")
    for hf in (False, True):
        rig.set(hf_enabled=hf)
        for shape in rig.shapes:
            shape.spec, shape.specs = rig.config.radio(shape.id) or shape.spec, rig.config.radios
        assert rig.objects.next_at("BOTH") == shown, "HF's pause holds while HF is away"


async def test_the_next_time_of_a_bulletin_does_not_move_when_one_of_its_radios_drops(tmp_path: Path) -> None:
    rig = await bulletins_at(tmp_path, Draws(1.0))
    posted = rig.posts.post("bulletin", "NET TONIGHT", hours=4, radios=(FM_ID, HF_ID))
    rig.timed(5)
    shown = rig.posts.next_at(posted.slot)
    rig.set(hf_enabled=False)
    for shape in rig.shapes:
        shape.spec, shape.specs = rig.config.radio(shape.id) or shape.spec, rig.config.radios
    assert rig.posts.next_at(posted.slot) == shown
