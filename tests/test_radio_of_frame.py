"""The radio of the frame: every gate asks the radio the frame goes on and every frame is built for it, never for "the radio" of a station that has two. The retry ticker (services/retries.py), on the
station's radios as the registry gives them (services/radioset.py RadioPick: tests/test_messaging.py `StubPick` over stub lines) and on the old set of two (tests/support/stubtnc.py `StubRadios`, read as a
RadioPick: the shape of before the round, kept until its last test goes), attempts a message on HF while the FM radio is away and moves on only the waits of the radio that was away, two radios of one kind
each by its own id. The sender and our objects (services/sender.py, services/ownobjects.py), on the station's radios by id (tests/support/seamshapes.py over stub lines), send on the radio that takes a frame
and give a held radio its copy later without another sending again, keep the round by the radio's id (two radios of one kind are two radios), and repeat by the net cycle of the path each radio carries; a
query asked over HF (services/queries.py) is answered with the beacon's and the status's frames built for HF, no path and within the frame, while the same asked on FM has the path, and the general and the
heard query asked over HF are answered on HF alone (each on the registry's radios and on the old set); the status report (services/rigstatus.py) is built for the radio it goes on."""
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.config import Config
from neoaprs.interlock import Interlock
from neoaprs.message import MessageRecord, retry_pause
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import FM_ID, HF_ID, RadioId
from neoaprs.radiotypes.common import HF_LIMITS
from neoaprs.ownlog import OwnLog
from neoaprs.packet import Message, Other, Packet
from neoaprs.services.answers import as_pick
from neoaprs.services.beacon import Beacon
from neoaprs.services.beaconframe import BeaconFrames
from neoaprs.services.ownobjects import OwnObjects
from neoaprs.services.queries import Queries
from neoaprs.services.radioset import AirRadio, RadioPick
from neoaprs.services.retries import Retries
from neoaprs.services.rigstatus import RigStatus
from neoaprs.services.sender import Sender
from neoaprs.source import Source
from neoaprs.stationbook import StationBook
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, idle_for, remember_stop, until
from tests.support.rig import ServiceRig
from tests.support.seamshapes import LiveShape, RegistryShape
from tests.support.storedb import log_at
from tests.support.stubtnc import StubRadios, StubTnc
from tests.test_messaging import LineAir, StubPick
from tests.test_queries_heard import Log


BOTH: Config = replace(ON_AIR, hf_enabled=True, station_comment="a comment cut on a radio with a short frame")       # (43 characters, the most a comment may be)


class Host:
    """What the ticker asks of messaging, here by hand: the records by id, the radio of each by the station (the RadioPick's `for_station`), and the attempts made."""

    def __init__(self, radios: RadioPick, records: list[MessageRecord]) -> None:
        self.radios = radios
        self.records = {r.id: r for r in records}
        self.attempted: list[int] = []

    def get(self, number: int) -> MessageRecord | None:
        return self.records.get(number)

    def attempt(self, record: MessageRecord) -> MessageRecord:
        self.attempted.append(record.id)
        self.records[record.id] = record = replace(record, attempts=record.attempts + 1)
        return record

    def put(self, record: MessageRecord) -> None:
        self.records[record.id] = record

    def radio_of(self, record: MessageRecord) -> AirRadio | None:
        return self.radios.for_station(record.to_call)


def record(number: int, to: str, at: datetime, attempts: int = 1) -> MessageRecord:
    return MessageRecord(number, at, "out", "OH2GBA", to, "hello", f"0{number}", "sending", attempts=attempts, last_attempt_at=at if attempts else None)


def two(config: Config, old: bool) -> tuple[RadioPick | StubRadios, RadioPick, dict[int, StubTnc]]:
    """The two radios of the settings with OH2C on the HF one: what the ticker is given (the registry's RadioPick, or the old set of two of before the round), the same as a RadioPick, and the lines by id."""
    if old:
        radios = StubRadios(hf_stations=("OH2C",))
        return radios, as_pick(radios, lambda: config), {FM_ID: radios.fm, HF_ID: radios.hf}
    pick = StubPick([LineAir(StubTnc(), lambda: config), LineAir(StubTnc(max_frame=123), lambda: config)], hf_stations=("OH2C",))
    return pick, pick, pick.lines


# ---- the retry ticker

@pytest.mark.parametrize("old", [False, True], ids=["by id", "the old set"])
def test_the_ticker_attempts_a_message_on_hf_while_the_fm_radio_is_away_and_flushes_the_acks_that_wait(old: bool) -> None:
    given, radios, lines = two(BOTH, old)
    clock = FixedClock()
    at = clock() - timedelta(seconds=60)                                    # (both messages had their first attempt 60 s ago: the retry at 32 s is due, on HF after its pause of at most 20 s too)
    host = Host(radios, [record(1, "OH2B", at), record(2, "OH2C", at)])
    flushed: list[int] = []
    retries = Retries(host, given, lambda: BOTH, Interlock(lambda: BOTH), clock, lambda: 1.0, lambda: flushed.append(1))
    for r in host.records.values():
        retries.plan(r)
    lines[FM_ID].state = Source.State.SILENT
    retries.tick()
    assert host.attempted == [2] and flushed == [1], "the message to the station on HF went, the acks were flushed; the message to the station on FM waits"
    assert retries.away(radios.get(FM_ID)) and not retries.away(radios.get(HF_ID))       # type: ignore[arg-type]
    assert set(retries._down) == {FM_ID}, "the time away is kept by the radio's id"
    if old:
        assert retries.away(lines[FM_ID]) and not retries.away(lines[HF_ID]), "(a test of today names the radio by its line)"


@pytest.mark.parametrize("old", [False, True], ids=["by id", "the old set"])
def test_the_time_a_radio_was_away_moves_on_the_waits_of_that_radio_alone_and_not_a_clock_jump_after_its_return(old: bool) -> None:
    given, radios, lines = two(BOTH, old)
    clock = FixedClock()
    at = clock()
    host = Host(radios, [record(1, "OH2B", at), record(2, "OH2C", at)])
    retries = Retries(host, given, lambda: BOTH, Interlock(lambda: BOTH), clock, lambda: 1.0)
    for r in host.records.values():
        retries.plan(r)
    lines[FM_ID].state = Source.State.SILENT
    retries.tick()                                                          # (the FM radio is away from now)
    clock.advance(10)
    retries.tick()                                                          # (... and still at +10)
    clock.advance(52)                                                       # (it came back somewhere in these 52 s, which nobody saw: the jump is not its time away)
    lines[FM_ID].state = Source.State.CONNECTED
    retries.tick()
    hf_pause = retry_pause(record(2, "OH2C", at), HF_LIMITS.retry_jitter_sec)        # (of the message as it was planned, with its one attempt: the pause of the HF radio's limits)
    assert retries._due[1] == at + timedelta(seconds=32 + 10) and retries._due[2] == at + timedelta(seconds=32) + hf_pause, "FM's wait moved on by the 10 s seen away, HF's not at all (it has its pause)"
    assert host.attempted == [1, 2], "both retries were due by +62 and went: the jump moved neither on"


def test_two_radios_of_one_kind_are_watched_each_by_its_id_and_the_time_one_was_away_moves_on_its_own_waits_alone(caplog: pytest.LogCaptureFixture) -> None:
    config = replace(BOTH, hf_enabled=False)
    pick = StubPick([LineAir(StubTnc(), lambda: config), LineAir(StubTnc(), lambda: config, id=3, name="FM 2")], chosen={"OH2C": 3})        # (two FM radios, ids 1 and 3, as the round has them; OH2C is reached on the second)
    lines = pick.lines
    clock = FixedClock()
    at = clock()
    host = Host(pick, [record(1, "OH2B", at), record(2, "OH2C", at)])
    retries = Retries(host, pick, lambda: config, Interlock(lambda: config), clock, lambda: 1.0)
    for r in host.records.values():
        retries.plan(r)
    lines[3].state = Source.State.SILENT
    retries.tick()
    clock.advance(20)
    retries.tick()
    assert retries.away(pick.get(3)) and not retries.away(pick.get(FM_ID)), "the second FM radio is away, the first is not: by kind they would be one"     # type: ignore[arg-type]
    lines[3].state = Source.State.CONNECTED
    with caplog.at_level("INFO", logger="neoaprs.messaging"):
        retries.tick()
    assert retries._due[2] == at + timedelta(seconds=32 + 20) and retries._due[1] == at + timedelta(seconds=32), "the 20 s away moved on the wait of the message on radio 3 alone"
    assert "the FM 2 radio takes frames again after 20 s" in caplog.text, "a radio other than 1 and 2 is named by its name"


# ---- the sender and our objects

class Lines:
    """The station's radios of the settings as the registry gives them (RadioPick), each on a stub line of its own: `lines[id]`."""

    def __init__(self, config: Config, specs: tuple[RadioSpec, ...] | None = None, *, old: bool = False) -> None:
        self.specs = config.radios if specs is None else specs
        self.lines = {spec.id: StubTnc() for spec in self.specs}
        self.pick: object = RegistryShape([LiveShape(spec, self.specs, self.lines[spec.id]) for spec in self.specs])      # type: ignore[arg-type]
        if old:                                                             # (the old set of two of before the round, which the sender reads as a RadioPick: services/common.OldRadios)
            self.pick = StubRadios()
            self.lines = {FM_ID: self.pick.fm, HF_ID: self.pick.hf}                                                   # type: ignore[attr-defined]

    def __getitem__(self, id: int) -> StubTnc:
        return self.lines[id]


async def objects_on(tmp_path: Path, radios: Lines, config: Config) -> OwnObjects:
    log, _, clock = await log_at(tmp_path, OwnLog)
    objects = OwnObjects(Sender(radios.pick, lambda: config, clock, spacing_sec=0.0), lambda: config, log, clock=clock, tick_sec=3600.0)
    await objects.start()
    remember_stop(objects.stop)
    return objects


@pytest.mark.parametrize("old", [False, True], ids=["by id", "the old set"])
async def test_an_object_on_both_radios_goes_on_the_radio_that_takes_it_and_a_held_radio_gets_its_copy_later_without_the_other_sending_again(tmp_path: Path, old: bool) -> None:
    radios = Lines(BOTH, old=old)
    objects = await objects_on(tmp_path, radios, BOTH)
    clock = objects.clock
    fm, hf = radios[FM_ID], radios[HF_ID]
    hf.held = "the channel is busy"
    objects.set("BOTHWAYS", "object", 60.2, 24.9, "/", ">", "on both", radios=(FM_ID, HF_ID))
    objects.tick()
    assert [f.info[:10] for f in fm.sent] == [b";BOTHWAYS "] and hf.sent == [], "FM took it at once, HF is held"
    assert objects._taken["BOTHWAYS"] == {FM_ID}, "the round is kept by the radio's id"
    objects.tick()
    objects.tick()
    assert len(fm.sent) == 1, "FM does not send the object again while HF owes its copy"
    hf.held = ""
    objects.tick()
    assert len(hf.sent) == 1 and len(fm.sent) == 1 and hf.sent[0].path == ()
    found = objects.get("BOTHWAYS")
    assert found is not None and found.sent == 1 and found.last_sent_at == clock(), "the round is done when every radio has taken it"
    fm.state = Source.State.SILENT                                          # (the FM radio away: it does not hold the next round up)
    clock.advance(600)                                                      # type: ignore[attr-defined]
    objects.tick()
    assert len(hf.sent) == 2 and len(fm.sent) == 1 and objects.get("BOTHWAYS").sent == 2       # type: ignore[union-attr]


async def test_an_object_on_hf_alone_goes_while_the_fm_radio_is_away(tmp_path: Path) -> None:
    radios = Lines(BOTH)
    radios[FM_ID].state = Source.State.SILENT
    objects = await objects_on(tmp_path, radios, BOTH)
    objects.set("FARAWAY", "object", 61.5, 23.8, "/", "-", "over HF", radios=(HF_ID,))
    assert objects.tick() and len(radios[HF_ID].sent) == 1 and radios[FM_ID].sent == []


async def test_with_one_radio_enabled_an_object_goes_on_it_whatever_it_was_given_and_with_none_it_waits(tmp_path: Path) -> None:
    only_hf = replace(BOTH, fm_enabled=False)
    radios = Lines(only_hf)
    objects = await objects_on(tmp_path, radios, only_hf)
    objects.set("FMSAID", "object", 61.5, 23.9, "/", ">", "said fm", radios=(FM_ID,))
    assert objects.tick() and [f.info[:8] for f in radios[HF_ID].sent] == [b";FMSAID "] and radios[FM_ID].sent == [], "the main radio, the HF one, takes it"
    assert objects.get("FMSAID").radios == (FM_ID,), "the choice is kept for the day the FM radio is on"       # type: ignore[union-attr]
    none = replace(only_hf, hf_enabled=False)                               # (no radio at all: what the settings refuse, and a fresh installation of the round)
    (tmp_path / "none").mkdir()
    idle = await objects_on(tmp_path / "none", Lines(none), none)
    idle.set("NOWHERE", "object", 61.5, 23.9, "/", ">", "", radios=(FM_ID, HF_ID))
    assert not idle.tick() and idle._sender.problem == "there is no radio" and idle.next_at("NOWHERE") is not None


async def test_two_radios_of_one_kind_are_two_radios_and_each_takes_its_own_copy_of_the_round(tmp_path: Path) -> None:
    specs = (RadioSpec(FM_ID, "fm", "kiss", "", True, 1, settings={"path": "WIDE2-1"}), RadioSpec(HF_ID, "fm", "kiss", "", True, 2, settings={"path": "OH2RCH-2"}))
    radios = Lines(BOTH, specs)
    objects = await objects_on(tmp_path, radios, BOTH)
    radios[HF_ID].held = "the channel is busy"
    objects.set("TWICE", "object", 60.2, 24.9, "/", ">", "", radios=(FM_ID, HF_ID))
    objects.tick()
    assert len(radios[FM_ID].sent) == 1 and radios[HF_ID].sent == [] and objects.get("TWICE").sent == 0, "the second radio of the kind still owes its copy"     # type: ignore[union-attr]
    radios[HF_ID].held = ""
    objects.tick()
    assert [f.path_text for f in radios[FM_ID].sent + radios[HF_ID].sent] == ["WIDE2-1", "OH2RCH-2"] and objects.get("TWICE").sent == 1, "each by its own path"     # type: ignore[union-attr]


# ---- the answers to queries and the status report

class Rig(ServiceRig):
    """The two radios of the settings (a short HF frame) and the queries on them: given the registry's radios (a StubPick over the two lines) as app.py gives them, radio 1's beacon and the status report
    made from the one maker of frames, or with `old` the old set of two of before the round, with the beacon and the status report made the old way."""

    def __init__(self, old: bool = False) -> None:
        super().__init__(**{"hf_enabled": True, "station_comment": BOTH.station_comment})
        self.radios = StubRadios(hf_max_frame=60)                           # (a short HF frame: what is built for HF is cut to it, what is built for FM is not)
        self.book = StationBook(self.clock)
        self.book.set_me(self.config.station_call, self.config.station_lat, self.config.station_lon)
        self.pick = StubPick([LineAir(self.radios.fm, lambda: self.config), LineAir(self.radios.hf, lambda: self.config)])      # (the same two lines as the registry's radios: what the queries take)
        if old:
            self.beacon = Beacon(self.radios.fm, lambda: self.config, self.clock)      # (the FM beacon, made the old way: the queries ask it for the frame of the radio the answer goes on)
            self.status = RigStatus(self.radios, lambda: self.config, self.beacon, self.clock)
        else:
            maker = BeaconFrames(lambda: self.config, None, self.clock)             # (app.py's shape: one maker, radio 1's beacon made from it, the status report on the registry's radios)
            fm = self.pick.get(FM_ID)
            assert fm is not None
            self.beacon = Beacon(fm, lambda: self.config, self.clock, frames=maker)
            self.status = RigStatus(self.pick, lambda: self.config, maker, self.clock)
        self.status.last_text = "QRV 14.074 MHz USB"
        self.q = Queries(self.radios if old else self.pick, lambda: self.config, self.beacon, self.status.status_frame, self.book, lambda call, attempt=None, radio=1: self.config.beacon_path_calls, self.clock, delay=lambda: 0.0,
                         heard=Log({}))
        remember_stop(self.q.stop)

    def ask(self, text: str, radio: RadioId) -> None:
        self.q.on_packet(Packet(self.clock(), "in", b"", "OH2RDG", "APZNEO", ("OH2RCH-2*",), b"", Message("OH2GBA", text, None), None, "rf", radio))

    def ask_around(self, text: str, radio: RadioId) -> None:
        """The general query in the information field of a packet, as it is asked."""
        self.q.on_packet(Packet(self.clock(), "in", b"", "OH2RDG", "APZNEO", ("OH2RCH-2*",), b"", Other("query", text), None, "rf", radio))


@pytest.mark.parametrize("old", [False, True], ids=["by id", "the old set"])
def test_a_query_asked_over_hf_is_answered_with_frames_built_for_hf_and_the_same_on_fm_with_the_path(old: bool) -> None:
    rig = Rig(old)
    rig.ask("?APRSP", HF_ID)
    rig.ask("?APRSS", HF_ID)
    assert len(rig.radios.hf.sent) == 2 and rig.radios.fm.sent == []
    for frame in rig.radios.hf.sent:
        assert frame.path == () and len(ax25.encode(frame)) <= 60, frame.tnc2()
    assert rig.radios.hf.sent[0].info.startswith(b"=6010.20N/02456.40E-a comment") and rig.radios.hf.sent[1].info.startswith(b">") and b"QRV" in rig.radios.hf.sent[1].info
    rig.clock.advance(31)                                                   # (the same station asking the same within 30 s is answered once)
    rig.ask("?APRSP", FM_ID)
    assert rig.radios.fm.sent[-1].path_text == "WIDE1-1,WIDE2-1" and rig.radios.fm.sent[-1].info == b"=6010.20N/02456.40E-" + BOTH.station_comment.encode()


@pytest.mark.parametrize("old", [False, True], ids=["by id", "the old set"])
async def test_the_general_query_and_the_heard_query_asked_over_hf_are_answered_on_hf_alone_with_no_path(old: bool) -> None:
    rig = Rig(old)
    rig.ask_around("?APRS?", HF_ID)
    await until(lambda: len(rig.radios.hf.sent) == 2)
    assert [f.info[:1] for f in rig.radios.hf.sent] == [b"=", b">"] and all(f.path == () and len(ax25.encode(f)) <= 60 for f in rig.radios.hf.sent), "our position and status, built for HF"
    rig.ask("?APRSH OH2X", HF_ID)
    await until(lambda: len(rig.radios.hf.sent) == 3)
    heard = rig.radios.hf.sent[2]
    assert heard.path == () and heard.info.startswith(b":OH2RDG   :OH2X NOT HEARD"), heard.tnc2()
    await idle_for(0.05)
    assert rig.radios.fm.sent == [], "nothing on FM"


def test_the_status_report_is_built_for_the_radio_it_goes_on() -> None:
    rig = Rig()
    rig.radios.enabled, rig.pick.on = {"hf"}, {HF_ID}                       # (the FM radio off: the default radio is the HF one)
    assert rig.status._try("QRV 14.074 MHz USB") == ""
    [frame] = rig.radios.hf.sent
    assert frame.path == () and len(ax25.encode(frame)) <= 60 and rig.radios.fm.sent == []


async def test_an_object_on_hf_alone_repeats_by_the_net_cycle_of_a_direct_frame_and_one_on_both_by_that_of_the_fm_path(tmp_path: Path) -> None:
    config = replace(BOTH, beacon_path="WIDE2-2")
    objects = await objects_on(tmp_path, Lines(config), config)
    clock = objects.clock
    objects.set("FARAWAY", "object", 61.5, 23.8, "/", "-", "over HF", radios=(HF_ID,))
    objects.set("BOTHWAYS", "object", 60.2, 24.9, "/", "-", "on both", radios=(FM_ID, HF_ID))
    for name in ("FARAWAY", "BOTHWAYS"):
        found = objects.get(name)
        assert found is not None
        objects._store(replace(found, sent=6, last_sent_at=clock()))
    assert objects._due("FARAWAY") == clock() + timedelta(seconds=600), "the HF frame carries no digipeater: ten minutes"
    assert objects._due("BOTHWAYS") == clock() + timedelta(seconds=1200), "WIDE2-2 on FM: twenty"
