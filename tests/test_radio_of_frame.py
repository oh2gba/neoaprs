"""The radio of the frame, on stubs (tests/support/stubtnc.py: two stub radios as one set): every gate asks the radio the frame goes on and every frame is built for it, never for "the radio" of a station that has two.
The retry ticker (services/retries.py) attempts a message on HF while the FM radio is away and moves on only the waits of the radio that was away; the sender and our objects (services/sender.py, services/ownobjects.py)
send on the radio that takes a frame and give a held radio its copy later without the other sending again; a query asked over HF (services/queries.py) is answered with the beacon's and the status's frames built for HF,
no path and within the frame, while the same asked on FM has the path; the status report (services/rigstatus.py) is built for the radio it goes on."""
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from neoaprs import ax25
from neoaprs.config import Config
from neoaprs.interlock import Interlock
from neoaprs.message import MessageRecord, retry_pause
from neoaprs.radiorules import HF
from neoaprs.ownlog import OwnLog
from neoaprs.packet import Message, Packet
from neoaprs.services.beacon import Beacon
from neoaprs.services.common import Radio
from neoaprs.services.ownobjects import OwnObjects
from neoaprs.services.queries import Queries
from neoaprs.services.retries import Retries
from neoaprs.services.rigstatus import RigStatus
from neoaprs.services.sender import Sender
from neoaprs.source import Source
from neoaprs.stationbook import StationBook
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, remember_stop
from tests.support.rig import ServiceRig
from tests.support.storedb import log_at
from tests.support.stubtnc import StubRadios


BOTH: Config = replace(ON_AIR, hf_enabled=True, station_comment="a comment cut on a radio with a short frame")       # (43 characters, the most a comment may be)


class Host:
    """What the ticker asks of messaging, here by hand: the records by id, the radio of each by the station, and the attempts made."""

    def __init__(self, radios: StubRadios, records: list[MessageRecord]) -> None:
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

    def radio_of(self, record: MessageRecord) -> Radio | None:
        return self.radios.for_station(record.to_call)


def record(number: int, to: str, at: datetime, attempts: int = 1) -> MessageRecord:
    return MessageRecord(number, at, "out", "OH2GBA", to, "hello", f"0{number}", "sending", attempts=attempts, last_attempt_at=at if attempts else None)


# ---- the retry ticker

def test_the_ticker_attempts_a_message_on_hf_while_the_fm_radio_is_away_and_flushes_the_acks_that_wait() -> None:
    radios = StubRadios(hf_stations=("OH2C",))
    clock = FixedClock()
    at = clock() - timedelta(seconds=60)                                    # (both messages had their first attempt 60 s ago: the retry at 32 s is due, on HF after its pause of at most 20 s too)
    host = Host(radios, [record(1, "OH2B", at), record(2, "OH2C", at)])
    flushed: list[int] = []
    retries = Retries(host, radios, lambda: BOTH, Interlock(lambda: BOTH), clock, lambda: 1.0, lambda: flushed.append(1))
    for r in host.records.values():
        retries.plan(r)
    radios.fm.state = Source.State.SILENT
    retries.tick()
    assert host.attempted == [2] and flushed == [1], "the message to the station on HF went, the acks were flushed; the message to the station on FM waits"
    assert retries.away(radios.fm) and not retries.away(radios.hf)


def test_the_time_a_radio_was_away_moves_on_the_waits_of_that_radio_alone_and_not_a_clock_jump_after_its_return() -> None:
    radios = StubRadios(hf_stations=("OH2C",))
    clock = FixedClock()
    at = clock()
    host = Host(radios, [record(1, "OH2B", at), record(2, "OH2C", at)])
    retries = Retries(host, radios, lambda: BOTH, Interlock(lambda: BOTH), clock, lambda: 1.0)
    for r in host.records.values():
        retries.plan(r)
    radios.fm.state = Source.State.SILENT
    retries.tick()                                                          # (the FM radio is away from now)
    clock.advance(10)
    retries.tick()                                                          # (... and still at +10)
    clock.advance(52)                                                       # (it came back somewhere in these 52 s, which nobody saw: the jump is not its time away)
    radios.fm.state = Source.State.CONNECTED
    retries.tick()
    hf_pause = retry_pause(record(2, "OH2C", at), HF.retry_jitter_sec)            # (of the message as it was planned, with its one attempt)
    assert retries._due[1] == at + timedelta(seconds=32 + 10) and retries._due[2] == at + timedelta(seconds=32) + hf_pause, "FM's wait moved on by the 10 s seen away, HF's not at all (it has its pause)"
    assert host.attempted == [1, 2], "both retries were due by +62 and went: the jump moved neither on"


# ---- the sender and our objects

async def test_an_object_on_both_radios_goes_on_the_radio_that_takes_it_and_a_held_radio_gets_its_copy_later_without_the_other_sending_again(tmp_path: Path) -> None:
    log, _, clock = await log_at(tmp_path, OwnLog)
    radios = StubRadios()
    sender = Sender(radios, lambda: BOTH, clock, spacing_sec=0.0)
    objects = OwnObjects(sender, lambda: BOTH, log, clock=clock, tick_sec=3600.0)
    await objects.start()
    remember_stop(objects.stop)
    radios.hf.held = "the channel is busy"
    objects.set("BOTHWAYS", "object", 60.2, 24.9, "/", ">", "on both", radio="both")
    objects.tick()
    assert [f.info[:10] for f in radios.fm.sent] == [b";BOTHWAYS "] and radios.hf.sent == [], "FM took it at once, HF is held"
    objects.tick()
    objects.tick()
    assert len(radios.fm.sent) == 1, "FM does not send the object again while HF owes its copy"
    radios.hf.held = ""
    objects.tick()
    assert len(radios.hf.sent) == 1 and len(radios.fm.sent) == 1 and radios.hf.sent[0].path == ()
    found = objects.get("BOTHWAYS")
    assert found is not None and found.sent == 1 and found.last_sent_at == clock(), "the round is done when every radio has taken it"
    radios.fm.state = Source.State.SILENT                                   # (the FM radio away: it does not hold the next round up)
    clock.advance(600)
    objects.tick()
    assert len(radios.hf.sent) == 2 and len(radios.fm.sent) == 1 and objects.get("BOTHWAYS").sent == 2       # type: ignore[union-attr]


async def test_an_object_on_hf_alone_goes_while_the_fm_radio_is_away(tmp_path: Path) -> None:
    log, _, clock = await log_at(tmp_path, OwnLog)
    radios = StubRadios()
    radios.fm.state = Source.State.SILENT
    objects = OwnObjects(Sender(radios, lambda: BOTH, clock, spacing_sec=0.0), lambda: BOTH, log, clock=clock, tick_sec=3600.0)
    await objects.start()
    remember_stop(objects.stop)
    objects.set("FARAWAY", "object", 61.5, 23.8, "/", "-", "over HF", radio="hf")
    assert objects.tick() and len(radios.hf.sent) == 1 and radios.fm.sent == []


# ---- the answers to queries and the status report

class Rig(ServiceRig):
    def __init__(self) -> None:
        super().__init__(**{"hf_enabled": True, "station_comment": BOTH.station_comment})
        self.radios = StubRadios(hf_max_frame=60)                           # (a short HF frame: what is built for HF is cut to it, what is built for FM is not)
        self.book = StationBook(self.clock)
        self.book.set_me(self.config.station_call, self.config.station_lat, self.config.station_lon)
        self.beacon = Beacon(self.radios.fm, lambda: self.config, self.clock)          # (the FM beacon, as app.py gives the queries)
        self.status = RigStatus(self.radios, lambda: self.config, self.beacon, self.clock)
        self.status.last_text = "QRV 14.074 MHz USB"
        self.q = Queries(self.radios, lambda: self.config, self.beacon, self.status.status_frame, self.book, lambda call: self.config.beacon_path_calls, self.clock, delay=lambda: 0.0)
        remember_stop(self.q.stop)

    def ask(self, text: str, radio: str) -> None:
        self.q.on_packet(Packet(self.clock(), "in", b"", "OH2RDG", "APZNEO", ("OH2RCH-2*",), b"", Message("OH2GBA", text, None), None, "rf", radio))


def test_a_query_asked_over_hf_is_answered_with_frames_built_for_hf_and_the_same_on_fm_with_the_path() -> None:
    rig = Rig()
    rig.ask("?APRSP", "hf")
    rig.ask("?APRSS", "hf")
    assert len(rig.radios.hf.sent) == 2 and rig.radios.fm.sent == []
    for frame in rig.radios.hf.sent:
        assert frame.path == () and len(ax25.encode(frame)) <= 60, frame.tnc2()
    assert rig.radios.hf.sent[0].info.startswith(b"=6010.20N/02456.40E-a comment") and rig.radios.hf.sent[1].info.startswith(b">") and b"QRV" in rig.radios.hf.sent[1].info
    rig.clock.advance(31)                                                   # (the same station asking the same within 30 s is answered once)
    rig.ask("?APRSP", "fm")
    assert rig.radios.fm.sent[-1].path_text == "WIDE1-1,WIDE2-1" and rig.radios.fm.sent[-1].info == b"=6010.20N/02456.40E-" + BOTH.station_comment.encode()


def test_the_status_report_is_built_for_the_radio_it_goes_on() -> None:
    rig = Rig()
    rig.radios.enabled = {"hf"}                                             # (the FM radio off: the default radio is the HF one)
    assert rig.status._try(("text", "QRV"), "QRV 14.074 MHz USB") == ""
    [frame] = rig.radios.hf.sent
    assert frame.path == () and len(ax25.encode(frame)) <= 60 and rig.radios.fm.sent == []
