"""The objects and items of ours (neoaprs/services/ownobjects.py) on a Tnc that is a stub, a real log in a temporary database and a clock the test holds: the decay schedule second by second, a change that
starts it again, a kill that is sent three times and forgotten, the interlock, the radio that is away, the pause between two frames, a restart that goes on where the schedule stopped, and another station
that takes an object over."""
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from neoaprs.config import Config
from neoaprs.ownlog import OwnLog
from neoaprs.ownobject import OwnError, OwnObject
from neoaprs.packet import ObjectReport, Packet, Position
from neoaprs.services.ownobjects import MAX_OBJECTS, OwnObjects
from neoaprs.services.sender import Sender
from neoaprs.source import Source
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, remember_stop
from tests.support.storedb import store_at
from tests.support.stubtnc import StubTnc

STEP = 5                                                    # seconds the clock moves between two looks at it
LAT, LON = 60.17, 24.94


class Rig:
    """One run of the daemon's objects: made again on the same log and clock after a stop."""

    def __init__(self, log: OwnLog, clock: FixedClock, **changes: object) -> None:
        self.log, self.clock, self.begin = log, clock, clock()
        self.config: Config = replace(ON_AIR, **changes)               # type: ignore[arg-type]
        self.tnc = StubTnc()
        self.sender = Sender(self.tnc, lambda: self.config, clock, spacing_sec=10.0)
        self.objects = OwnObjects(self.sender, lambda: self.config, log, lambda name: name == "OH2RDG", clock, tick_sec=3600.0)
        self.sent: list[tuple[int, bytes]] = []                         # (seconds since the rig was made, the information field), in the order they went out
        self.changed: list[OwnObject] = []
        self.removed: list[OwnObject] = []
        self.objects.changed.connect(self.changed.append)
        self.objects.removed.connect(self.removed.append)

    async def start(self) -> "Rig":
        await self.objects.start()
        remember_stop(self.objects.stop)
        return self

    def make(self, name: str = "LEADER", kind: str = "object", **values: object) -> OwnObject:
        fields: dict[str, object] = {"lat": LAT, "lon": LON, "symbol_table": "/", "symbol_code": ">", **values}
        return self.objects.set(name, kind, **fields)                  # type: ignore[arg-type]

    def run(self, seconds: int) -> None:
        """Looks at the clock every STEP seconds for this long, the first look now."""
        for _ in range(0, seconds + 1, STEP):
            before = len(self.tnc.sent)
            self.objects.tick()
            self.sent += [(round((self.clock() - self.begin).total_seconds()), frame.info) for frame in self.tnc.sent[before:]]
            self.clock.advance(STEP)
        self.clock.advance(-STEP)

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


def reported(name: str, at: datetime, sender: str = "OH2XYZ", alive: bool = True) -> Packet:
    report = ObjectReport(name, alive, Position(LAT, LON, "/", ">"))
    return Packet(at, "in", b"", sender, "APRS", (), b"", report)


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    return await rig_at(tmp_path)


# ---- the schedule ---------------------------------------------------------------------------------------------------------------------------------

async def test_a_new_object_goes_out_at_once_then_after_1_2_4_minutes_and_on_to_the_net_cycle_time_of_its_path(rig: Rig) -> None:
    rig.make(comment="Rescue 1")
    rig.run(5000)
    assert rig.offsets() == [0, 60, 180, 420, 900, 1860, 3060, 4260], "the beacon's path has two digipeaters: a net cycle of 20 minutes"
    first = rig.tnc.sent[0]
    assert (str(first.destination), str(first.source), first.path_text, first.is_ui) == ("APZNEO", "OH2GBA", "WIDE1-1,WIDE2-1", True)
    assert rig.sent[0][1] == b";LEADER   *211200z6010.20N/02456.40E>Rescue 1" and rig.sent[1][1] == b";LEADER   *211201z6010.20N/02456.40E>Rescue 1", "each copy carries the time it is sent"


@pytest.mark.parametrize("path, expected", [("WIDE2-1", [0, 60, 180, 420, 900, 1500, 2100]), ("WIDE3-3", [0, 60, 180, 420, 900, 1860, 3660])])
async def test_the_net_cycle_time_follows_the_path_of_the_object(rig: Rig, path: str, expected: list[int]) -> None:
    rig.make(path=path)
    rig.run(3700 if path == "WIDE3-3" else 2100)
    assert rig.offsets() == expected
    assert rig.tnc.sent[0].path_text == path


async def test_an_object_goes_by_its_own_path_else_by_the_beacons(tmp_path: Path) -> None:
    rig = await rig_at(tmp_path, beacon_path="WIDE2-2")
    rig.make("ONE")
    rig.make("TWO", path="OH2RCH-2")
    rig.run(20)
    assert [f.path_text for f in rig.tnc.sent] == ["WIDE2-2", "OH2RCH-2"]


async def test_an_item_is_sent_as_an_item_without_a_time_stamp(rig: Rig) -> None:
    rig.make("AID", "item", symbol_table="\\", symbol_code="+", comment="First aid")
    rig.run(0)
    assert rig.sent == [(0, b")AID!6010.20N\\02456.40E+First aid")]


async def test_a_change_starts_the_decay_again_but_not_sooner_than_a_minute_after_the_last_packet(rig: Rig) -> None:
    rig.make(comment="one")
    rig.run(3)
    rig.make(comment="two")
    rig.run(500)
    assert rig.offsets() == [0, 60, 120, 240, 480]
    assert [info[-3:] for _, info in rig.sent] == [b"one", b"two", b"two", b"two", b"two"]


async def test_a_change_after_a_long_quiet_spell_goes_out_at_once_and_decays_from_the_start(rig: Rig) -> None:
    rig.make()
    rig.run(1000)
    assert rig.offsets() == [0, 60, 180, 420, 900]
    rig.make(lat=61.0)
    rig.run(300)
    assert rig.offsets() == [0, 60, 180, 420, 900, 1000, 1060, 1180], "the change goes out at once (the last packet is more than a minute old), and its decay starts from a minute"


async def test_the_same_values_again_change_nothing_and_send_nothing(rig: Rig) -> None:
    first = rig.make(comment="same", course_deg=90, speed_kmh=20.0)
    rig.run(0)
    assert rig.make(comment="same", course_deg=90, speed_kmh=20.0) == replace(first, sent=1, last_sent_at=rig.clock())
    rig.run(50)
    assert len(rig.sent) == 1


async def test_one_that_was_killed_and_made_again_is_alive_and_decays_from_the_start(rig: Rig) -> None:
    rig.make()
    rig.run(0)
    rig.objects.kill("LEADER")
    rig.make()
    rig.run(130)
    assert rig.offsets() == [0, 60, 120] and all(info.startswith(b";LEADER   *") for _, info in rig.sent)


# ---- the kill -------------------------------------------------------------------------------------------------------------------------------------

async def test_a_kill_is_sent_three_times_and_then_the_object_is_forgotten(rig: Rig) -> None:
    rig.make(comment="gone soon")
    rig.run(0)
    killed = rig.objects.kill("LEADER")
    assert killed is not None and not killed.alive and rig.objects.get("LEADER") == killed
    rig.run(1000)
    assert rig.offsets() == [0, 60, 120, 240]
    assert [info[:11] for _, info in rig.sent] == [b";LEADER   *", b";LEADER   _", b";LEADER   _", b";LEADER   _"]
    assert rig.sent[1][1] == b";LEADER   _211201z6010.20N/02456.40E>gone soon"
    assert rig.objects.get("LEADER") is None and rig.objects.records() == [] and [o.name for o in rig.removed] == ["LEADER"]
    await rig.settled()
    assert await rig.log.objects() == []


async def test_an_object_that_was_never_sent_is_removed_at_once_and_nothing_is_said_of_it(rig: Rig) -> None:
    rig.tnc.state = Source.State.SILENT
    rig.make()
    rig.run(120)
    assert rig.tnc.sent == [] and rig.objects.kill("LEADER") is None
    assert rig.objects.get("LEADER") is None and [o.name for o in rig.removed] == ["LEADER"]
    rig.tnc.state = Source.State.CONNECTED
    rig.run(300)
    assert rig.tnc.sent == []
    await rig.settled()
    assert await rig.log.objects() == []


async def test_a_kill_that_is_asked_again_changes_nothing_and_an_object_that_is_not_ours_is_an_error(rig: Rig) -> None:
    rig.make()
    rig.run(0)
    first = rig.objects.kill("LEADER")
    assert rig.objects.kill("LEADER") == first
    with pytest.raises(OwnError, match="no object or item"):
        rig.objects.kill("OH2RDG")


async def test_a_kill_waits_for_the_radio_and_is_still_sent_three_times_when_it_is_back(rig: Rig) -> None:
    rig.make()
    rig.run(0)
    rig.tnc.state = Source.State.SILENT
    rig.objects.kill("LEADER")
    rig.run(3600)
    assert rig.offsets() == [0] and rig.objects.get("LEADER") is not None
    rig.tnc.state = Source.State.CONNECTED
    rig.run(300)
    assert [info[:11] for _, info in rig.sent] == [b";LEADER   *"] + [b";LEADER   _"] * 3 and rig.objects.get("LEADER") is None


# ---- the interlock, the radio and the pace ----------------------------------------------------------------------------------------------------------

async def test_nothing_is_made_while_the_call_is_not_set(tmp_path: Path) -> None:
    rig = await rig_at(tmp_path, station_call="")
    with pytest.raises(OwnError, match="set your call first"):
        rig.make()
    assert rig.objects.records() == [] and rig.tnc.sent == []


async def test_nothing_is_sent_while_the_call_is_gone_and_what_was_due_goes_out_when_it_is_back(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    rig.make()
    rig.config = replace(rig.config, station_call="")
    rig.run(300)
    assert rig.tnc.sent == [] and "no object sent" in caplog.text
    rig.config = replace(rig.config, station_call="OH2GBA")
    rig.run(0)
    assert rig.offsets() == [300] and rig.tnc.sent[0].source.call == "OH2GBA"


async def test_the_radio_that_is_silent_holds_everything_back_and_one_packet_goes_out_when_it_is_back_however_many_were_missed(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    rig.make()
    rig.run(0)
    rig.tnc.state = Source.State.SILENT
    rig.run(7200)
    assert rig.offsets() == [0] and caplog.text.count("is due and") == 1 and "goes out when the radio is back" in caplog.text
    rig.tnc.state = Source.State.CONNECTED
    rig.run(60)
    assert rig.offsets() == [0, 7200], "one packet, not one for each interval that went by"
    rig.run(200)
    assert rig.offsets() == [0, 7200, 7320], "and the schedule goes on from it: its count was 2, the next wait is two minutes"


@pytest.mark.parametrize("state", [Source.State.WAITING, Source.State.STOPPED])
async def test_a_tnc_that_is_not_connected_sends_nothing_either(rig: Rig, state: Source.State) -> None:
    rig.tnc.state = state
    rig.make()
    rig.run(600)
    assert rig.tnc.sent == []


async def test_a_tnc_that_would_not_take_the_frame_is_tried_again_at_the_next_look(rig: Rig) -> None:
    rig.tnc.takes = False
    rig.make()
    rig.run(30)
    waiting = rig.objects.get("LEADER")
    assert rig.tnc.sent == [] and waiting is not None and waiting.sent == 0
    rig.tnc.takes = True
    rig.run(0)
    assert rig.offsets() == [30]


async def test_several_objects_that_are_due_together_go_out_one_after_the_other_ten_seconds_apart_the_oldest_due_first(rig: Rig) -> None:
    for name in ("ONE", "TWO", "THREE"):
        rig.make(name)
        rig.clock.advance(1)
    rig.run(40)
    assert [(t, info[1:6].strip()) for t, info in rig.sent] == [(3, b"ONE"), (13, b"TWO"), (23, b"THREE")]


async def test_a_frame_that_cannot_be_made_is_told_once_and_does_not_hold_the_others_up(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    rig.make("BAD")
    rig.make("GOOD", path="WIDE2-1")
    rig.config = replace(rig.config, beacon_path=",".join(["WIDE1-1"] * 9))
    rig.run(30)
    assert [f.path_text for f in rig.tnc.sent] == ["WIDE2-1"], "the object with a path of its own goes out, the one with the beacon's path of nine digipeaters cannot"
    assert caplog.text.count("cannot be sent") == 1, "told once, not at every look"


# ---- the names and the number ---------------------------------------------------------------------------------------------------------------------

async def test_an_object_cannot_have_our_call_or_the_name_of_a_station(rig: Rig) -> None:
    for name, why in (("OH2GBA", "our own call"), ("oh2gba", "our own call"), ("OH2RDG", "a station")):
        with pytest.raises(OwnError, match=why):
            rig.make(name)
    assert rig.make("OH2GBA-7").name == "OH2GBA-7", "another SSID is another call, and an object of any name may be made"


async def test_there_is_a_limit_to_the_objects_on_the_air(rig: Rig) -> None:
    for number in range(MAX_OBJECTS):
        rig.make(f"OBJ{number}")
    with pytest.raises(OwnError, match="kill one first"):
        rig.make("ONE MORE")
    assert rig.make("OBJ3", comment="a change of one that is there").comment == "a change of one that is there"


# ---- a restart ------------------------------------------------------------------------------------------------------------------------------------

async def test_a_restart_goes_on_where_the_schedule_stopped(tmp_path: Path) -> None:
    first = await rig_at(tmp_path)
    first.make(comment="kept", course_deg=88, speed_kmh=36 * 1.852)
    first.run(60)
    assert first.offsets() == [0, 60]
    await first.settled()
    await first.objects.stop()

    first.clock.advance(30)
    second = await Rig(first.log, first.clock).start()
    [obj] = second.objects.records()
    assert (obj.name, obj.comment, obj.course_deg, obj.sent, obj.alive, obj.last_sent_at) == ("LEADER", "kept", 88, 2, True, first.begin + timedelta(seconds=60))
    assert [o.name for o in second.changed] == ["LEADER"], "the objects are told at the start: the station book gets them from that"
    second.run(200)
    assert second.sent == [(90, b";LEADER   *211203z6010.20N/02456.40E>088/036kept")], "the next is due 120 seconds after the one at 60: 90 seconds after the restart"


async def test_a_kill_that_was_not_sent_yet_is_still_sent_after_a_restart(tmp_path: Path) -> None:
    first = await rig_at(tmp_path)
    first.make()
    first.run(0)
    first.tnc.state = Source.State.SILENT
    first.objects.kill("LEADER")
    await first.settled()
    await first.objects.stop()

    second = await Rig(first.log, first.clock).start()
    [obj] = second.objects.records()
    assert not obj.alive and obj.sent == 0
    second.run(300)
    assert [info[:11] for _, info in second.sent] == [b";LEADER   _"] * 3 and second.objects.records() == []
    await second.settled()
    assert await second.log.objects() == []


async def test_the_objects_are_kept_with_their_values_and_what_is_sent(tmp_path: Path) -> None:
    rig = await rig_at(tmp_path)
    rig.make("AID", "item", symbol_table="\\", symbol_code="+", comment="First aid", path="WIDE2-1")
    rig.make("LEADER", comment="Rescue 1", course_deg=0, speed_kmh=12.5)
    rig.run(20)
    await rig.settled()
    kept = {o.name: o for o in await rig.log.objects()}
    assert kept["AID"] == rig.objects.get("AID") and kept["LEADER"] == rig.objects.get("LEADER")
    assert (kept["AID"].kind, kept["AID"].path, kept["AID"].sent) == ("item", "WIDE2-1", 1) and (kept["LEADER"].course_deg, kept["LEADER"].speed_kmh) == (0, 12.5)


# ---- another station ------------------------------------------------------------------------------------------------------------------------------

async def test_another_station_that_reports_an_object_of_ours_takes_it_over_and_we_stop_without_a_kill(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    rig.make()
    rig.run(0)
    rig.objects.on_packet(reported("LEADER", rig.clock()))
    assert rig.objects.get("LEADER") is None and [o.name for o in rig.removed] == ["LEADER"] and "OH2XYZ took over our object LEADER" in caplog.text
    rig.run(600)
    assert rig.offsets() == [0]
    await rig.settled()
    assert await rig.log.objects() == []


async def test_a_copy_of_our_own_object_that_comes_back_is_no_takeover_and_neither_is_a_kill_or_another_name(rig: Rig) -> None:
    rig.make()
    rig.objects.on_packet(reported("LEADER", rig.clock(), sender="OH2GBA"))
    rig.objects.on_packet(reported("LEADER", rig.clock(), alive=False))
    rig.objects.on_packet(reported("OTHER", rig.clock()))
    rig.objects.on_packet(replace(reported("LEADER", rig.clock()), direction="out"))
    assert rig.objects.get("LEADER") is not None and rig.removed == []
