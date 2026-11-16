"""A station of six made-up radios for a simulated day (plan step 7: any number of radios of any type, side by side): two Dummy FM radios, three Dummy Mercury radios and one Dummy LoRa radio on the real
controller, with the tests' clock moved over a whole day. Every radio beacons at its own interval and floor (FM at the station's 20 minutes, Mercury and LoRa at their own 30 with the pause after each), and the one
whose Send on is unticked never does; each hears its own made-up world and no other's; a message goes out by rule 3.2 (on the radio that heard the station, on the Mercury radio that heard it last, on the main
radio for a station nobody heard) and is acked from that radio's world; the digipeater repeats on the FM radio whose digipeater is on, what that radio heard, and nowhere else, and a type that may not repeat
has no digipeater to turn on; the status and the bulletins go on the main radio alone, an object on the radios set for it and on no other, Ask around on the main radio or on the one named, each by that
radio's own path; a radio switched off for two hours sends nothing and hears nothing in them, forgets none of the stations the other Dummy Mercury radios still hear (the Mercury worlds share their six cities), and a
message on its way on it goes on by another Mercury radio that hears the station. What went out on each radio is counted, by kind and by path, and the counts are held here: a change of any of them is a change on
the air of a station with many radios. The same day is played again with two real types beside the six, a LoRa iGate on the network and a text monitor (`tnc-text`), each on a fake line: the six's counts are the
same, the board keys its own beacons and nothing else, and the monitor's line gets not one byte; a Sound card radio (`direwolf`, on the made-up Direwolf) beside them sends its own beacons alone.

The day is played in steps of a minute (two seconds in the minutes after the messages go out); in each step every Dummy line asks its world and every timer looks at the clock several times, and each radio's
random pause after a timed beacon is drawn from a seed of its own, so the day is the same at every run.

The script of the same station on the real program, scripts/sim-radios, starts its daemon apart from the terminal, so that Ctrl+C stops it with one signal."""
import asyncio
import importlib.machinery
import importlib.util
import os
import random
import sys
from collections import Counter
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from neoaprs import ax25, direwolfmodem, dummyline, loralist, radioregistry
from neoaprs.aprsmessage import parse_message
from neoaprs.clock import utc
from neoaprs.controller import Controller
from neoaprs.dummyscene import Scene, call_of, name_of
from neoaprs.dummyworlds import made_up_calls
from neoaprs.packet import Packet
from neoaprs.radiospec import RadioError, RadioId
from neoaprs.services.beacon import Beacon
from neoaprs.services.digipeater import BURST_MAX
from neoaprs.source import Source
from tests.support import fakedirewolf
from tests.support.air import on_air
from tests.support.clock import FixedClock
from tests.support.env import Env, until, until_started
from tests.support.fakelora import Board, BoardOnTcp, ListServer
from tests.support.fakeradio import FakeRadio
from tests.support.modemports import base_of_this_test

ROOT = Path(__file__).resolve().parent.parent
START = utc(2026, 11, 16, 0, 0, 0)
STEP_SEC, FINE_SEC = 60, 2            # how far the clock moves at a time over the day, and in the minutes after the messages go out (so that an ack and an answer come in their own steps)
TICK_SEC = 0.002                      # how often a Dummy line asks its world and a timer looks at the clock ...
STEP_WAIT_SEC = 0.012                 # ... in the real time each step is given: several times
ME = "OH2GBA"
HELSINKI = (60.17, 24.94)
FM1, HF1, FM2, HF2, HF3, LORA = 1, 2, 3, 4, 5, 6        # radios 1 and 2 from the settings of the first start, the others added in this order
IDS = (FM1, HF1, FM2, HF2, HF3, LORA)
HF_IDS = (HF1, HF2, HF3)
OFF = HF1                             # the radio switched off for two hours in the day (the settings' own HF radio, radio 2) ...
OFF_FROM, OFF_UNTIL = START + timedelta(hours=12), START + timedelta(hours=14)        # ... from and until
POST_AT = START + timedelta(hours=1)   # the bulletin posted and the object set (on FM2 and LoRa)
ASK_AT = START + timedelta(hours=3)    # Ask around, on the main radio and on the LoRa radio
SEND_AT = START + timedelta(hours=6)
CITY = "Q3TKU"                        # the HF station that answers a message
QUIET = "Q1KUO"                       # an HF station that takes none
NOBODY = "Q0ZZZ"                      # a call no world has
STATUS = {"station/status": "QRV 145.500", "status/source": "text", "status/interval_min": "60"}       # the station's status, by its text, every hour

# What of ours went out on each radio over the day: our beacons, status reports, bulletins, objects, queries, messages (every attempt) and acks. (What the digipeater repeated is held by its rule below: how many
# of a step's frames its burst limit lets through depends on how many fell in that minute of the stepped clock.)
OUT = {
    FM1: {"beacon": 72, "status": 25, "bulletin": 14, "query": 1, "message": 5, "ack": 1},   # beacons every 20 minutes; the status every hour from 00:00 to 24:00; the bulletin posted at 01:00 by its plan (at
                                                                       # once, +2 and +6 minutes, then every 20 up to four hours: 3 + 11); Ask on the main radio; the message to its home station, and four
                                                                       # attempts to the station nobody heard (the main radio's)
    HF1: {"beacon": 41, "message": 3, "ack": 1},                       # every 30 minutes and its pause, but for its two hours off; the message to the city (it heard the city last of the three) and the
                                                                       # first two attempts to the quiet city before it was switched off
    FM2: {"object": 50, "message": 1, "ack": 1},                       # Send on unticked: no beacon; the object set for it and LoRa (at 0, 1, 3, 7, 15 and 31 minutes, then every 30, LoRa's floor, on both: 6 + 44);
                                                                       # its home station's message
    HF2: {"beacon": 44},
    HF3: {"beacon": 44, "message": 2},                                 # the last two attempts to the quiet city, once HF1 was off
    LORA: {"beacon": 44, "object": 50, "query": 1, "message": 1, "ack": 1},
}
# The paths our own frames went by on each radio, by kind (the digipeater's repeats aside): the radio's own path (FM1 the station's, FM2 none of its own: the symbol's WIDE2-2, LoRa its WIDE1-1, HF none at all) for
# what is not a message, a query with RFONLY after it; the first attempts of a message by the path the station was heard by (direct, for a world's home station: policy.HEARD_PATH_ATTEMPTS), the later ones and
# those to a station nobody heard by the radio's own path.
PATHS = {
    FM1: {("beacon", "WIDE1-1,WIDE2-1"): 72, ("status", "WIDE1-1,WIDE2-1"): 25, ("bulletin", "WIDE1-1,WIDE2-1"): 14, ("query", "WIDE1-1,WIDE2-1,RFONLY"): 1, ("message", ""): 1,
          ("message", "WIDE1-1,WIDE2-1"): 4, ("ack", "WIDE1-1,WIDE2-1"): 1},
    HF1: {("beacon", ""): 41, ("message", ""): 3, ("ack", ""): 1},
    FM2: {("object", "WIDE2-2"): 50, ("message", ""): 1, ("ack", "WIDE2-2"): 1},
    HF2: {("beacon", ""): 44},
    HF3: {("beacon", ""): 44, ("message", ""): 2},
    LORA: {("beacon", "WIDE1-1"): 44, ("object", "WIDE1-1"): 50, ("query", "WIDE1-1,RFONLY"): 1, ("message", ""): 1, ("ack", "WIDE1-1"): 1},
}
NAMES = {FM1: "FM", HF1: "Mercury", FM2: "FM 2", HF2: "Mercury 2", HF3: "Mercury 3", LORA: "LoRa"}
TEXT, BOARD, WOLF = 7, 8, 9           # beside the six: a text monitor (tnc-text), a LoRa iGate on the network (lora-tcp) and a Sound card radio (direwolf), each a real type on a fake line or program
BOARD_BEACONS = 44                    # the board's beacons over the day: LoRa's 30 minutes and the pause, as the Dummy LoRa radio's
WOLF_BEACONS = 72                     # the Sound card radio's: the station's 20 minutes, as radio 1's
FLOOR_SEC = {FM1: 20 * 60, HF1: 30 * 60, HF2: 30 * 60, HF3: 30 * 60, LORA: 30 * 60}
PAUSE_SEC = {FM1: 0, HF1: 300, HF2: 300, HF3: 300, LORA: 300}


def kind_of(frame: ax25.Frame) -> str:
    """What a frame that went out is: our beacon, status, bulletin, object, query, message or ack, or another station's frame repeated by our digipeater."""
    if str(frame.source) != ME:
        return "digipeat"
    first = frame.info[:1]
    if first == b":":
        message = parse_message(frame.info[1:])
        return "bulletin" if message.addressee.startswith("BLN") else "ack" if message.ack_id else "message"
    return {b">": "status", b";": "object", b"?": "query"}.get(first, "beacon" if first in (b"!", b"=", b"/", b"@") else "other")


def asks_us(frame: ax25.Frame) -> bool:
    """Whether a frame heard asks for a fill-in: its first hop not yet used is WIDE1-1."""
    hop = next((a for a in frame.path if not a.repeated), None)
    return hop is not None and str(hop) == "WIDE1-1" and str(frame.source) != ME


def path_of(frame: ax25.Frame) -> str:
    return ",".join(str(a) for a in frame.path)


def fm_world(seed: int) -> set[str]:
    """The calls of the Dummy FM world of a seed, and its club's objects."""
    scene = Scene(HELSINKI, START, seed)
    return {a.call for a in scene.actors} | set(scene.digipeaters) | {name_of(name, seed) for name in ("FIELDDAY", "PARKING")}


TICKED: dict[object, datetime] = {}   # each beacon's and each of the station's own senders' timer, and the time it last looked at the clock


@pytest.fixture
def quick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every Dummy line asks its world and every radio's beacon looks at the clock several times in each step; each radio's pause after a timed beacon is drawn from a seed of its own (its id)."""
    monkeypatch.setattr(dummyline, "TICK_SEC", TICK_SEC)
    TICKED.clear()
    made: Callable[[Controller, object], Beacon] = Controller._make_beacon      # type: ignore[assignment]

    def beacon(self: Controller, radio: object) -> Beacon:
        b = made(self, radio)
        rng = random.Random(b.radio.id)  # noqa: S311  (a pause on the made-up air)
        b.tick_sec, b.retry_sec, b.jitter = TICK_SEC, 0.05, lambda most: rng.uniform(0.0, most)
        tick = b._tick

        def ticked() -> None:                                                         # (the time its timer last looked at: a step waits for every beacon to have seen it)
            tick()
            TICKED[b] = b.clock()
        b._tick = ticked                                                              # type: ignore[method-assign]
        return b

    monkeypatch.setattr(Controller, "_make_beacon", beacon)


class Day:
    """The station of six radios, its clock, and every packet of every radio with the time it came at."""

    def __init__(self, tmp_path: Path) -> None:
        self.clock = FixedClock(START)
        self.e = Env(tmp_path, clock=self.clock, radio=False, settings={"station/lat": str(HELSINKI[0]), "station/lon": str(HELSINKI[1]), "tnc/profile": "dummy", "hf/enabled": "true",
                                                                          "hf/profile": "dummy-hf", "beacon/interval_min": "20", "digi/enabled": "true", "messages/alert": "false", **STATUS})
        ctl = self.e.ctl
        self.e.mercury._finder = lambda: None                                        # (no program: a Dummy HF radio works without its speaker)
        ctl.messaging.tick_sec = ctl.ownobjects.tick_sec = ctl.ownbulletins.tick_sec = ctl.rigstatus.poll_sec = TICK_SEC
        self.senders: tuple[object, ...] = (ctl.ownobjects, ctl.ownbulletins, ctl.rigstatus)      # (each records the time it last looked at, as each beacon does: a step waits for them too)
        for repeater in (ctl.ownobjects, ctl.ownbulletins):
            repeater.tick = self._seen(repeater, repeater.tick)                       # type: ignore[method-assign]
        poll = ctl.rigstatus.poll

        async def polled() -> None:
            await poll()
            TICKED[ctl.rigstatus] = self.clock()
        ctl.rigstatus.poll = polled                                                   # type: ignore[method-assign]
        self.packets: list[tuple[datetime, Packet]] = []
        ctl.radio_packet.connect(lambda p: self.packets.append((self.clock(), p)))

    def _seen(self, owner: object, tick: Callable[[], bool]) -> Callable[[], bool]:
        def ticked() -> bool:
            sent = tick()
            TICKED[owner] = self.clock()
            return sent
        return ticked

    def hear(self, radio: RadioId, source: str, info: str) -> None:
        """A frame from `source`, direct, heard on the radio's Dummy line as its world hands one over."""
        on = self.e.ctl.radios.get(radio)
        assert on is not None
        on.line._port._deliver(on_air(source, info.encode(), path=""))

    def out(self, radio: RadioId) -> list[tuple[datetime, ax25.Frame]]:
        return [(at, ax25.decode(p.raw)) for at, p in self.packets if p.direction == "out" and p.radio_id == radio]

    def heard(self, radio: RadioId) -> list[tuple[datetime, Packet]]:
        return [(at, p) for at, p in self.packets if p.direction == "in" and p.radio_id == radio]

    async def until(self, at: datetime, step_sec: int = STEP_SEC) -> None:
        while self.clock() < at:
            self.clock.advance(step_sec)
            await asyncio.sleep(STEP_WAIT_SEC)
            await until(lambda: all(TICKED.get(r.beacon) == self.clock() for r in self.e.ctl.radios.all() if r.beacon.running)
                        and all(TICKED.get(s) == self.clock() for s in self.senders))      # (on a loop that is slow, no beacon, status, object or bulletin misses a minute)


@pytest.fixture
async def beside_boards(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[Board, BoardOnTcp, FakeRadio]]:
    """The two real types beside the six: a LoRa iGate on the network (the fake board behind its TNC server, its list of heard packets on the list server) and a TNC that prints what it hears."""
    board = Board("igate")
    end, server, text = BoardOnTcp(board), await ListServer(board).start(), FakeRadio()
    await end.start()
    await text.start()
    monkeypatch.setattr(loralist, "PORT", server.port)
    monkeypatch.setitem(radioregistry.CARRIED, "direwolf", lambda: True)             # (the Sound card radio's Direwolf is the made-up one: it gives back each frame it is sent as heard)
    monkeypatch.setattr("neoaprs.direwolfprogram.find", lambda tools=None: fakedirewolf.program())
    monkeypatch.setattr(direwolfmodem, "FIRST_PORT", base_of_this_test())
    monkeypatch.setattr(direwolfmodem, "_numbers_of", lambda name: (1, 1))           # (Windows: its card is the second input and output of the made-up Direwolf's WinMM lists; the machine's own name none)
    yield board, end, text
    await end.aclose()
    await text.aclose()
    await server.stop()


@pytest.mark.parametrize("beside", [False, True], ids=["six", "six-and-a-lora-board-a-text-monitor-and-a-sound-card-radio"])
async def test_six_made_up_radios_for_a_day_each_by_its_own_rules_and_nothing_on_a_radio_it_should_not_go_on(tmp_path: Path, quick: None, beside: bool,
                                                                                                    beside_boards: tuple[Board, BoardOnTcp, FakeRadio]) -> None:
    """With `beside`, a real LoRa iGate on the network (radio 8), a text monitor (radio 7, `tnc-text`) and a Sound card radio (radio 9, `direwolf`) are added after the six: the six's day is the same frame for
    frame, the board and the Sound card radio send their own beacons and nothing else, and not one byte goes to the monitor's line, though a station it hears asks for an answer."""
    board, end, text = beside_boards
    day = Day(tmp_path)
    e = day.e
    await e.start(connected=False)
    for type in ("dummy", "dummy-hf", "dummy-hf", "dummy-lora"):
        await e.ctl.add_radio(type)
    if beside:
        assert await e.ctl.add_radio("tnc-text") == TEXT and await e.ctl.add_radio("lora-tcp") == BOARD and await e.ctl.add_radio("direwolf") == WOLF
        assert await e.ctl.save_radio_settings(TEXT, {"port": text.url}) and await e.ctl.save_radio_settings(BOARD, {"tcp_host": "127.0.0.1", "tcp_port": str(end.port)})
        assert await e.ctl.save_radio_settings(WOLF, {"sound_card": "plughw:7,0", "keying": "vox"})
    assert [(s.id, s.type) for s in e.ctl.config.live_radios][:6] == [(FM1, "dummy"), (HF1, "dummy-hf"), (FM2, "dummy"), (HF2, "dummy-hf"), (HF3, "dummy-hf"), (LORA, "dummy-lora")]
    assert {id: e.ctl.radios.name_of(id) for id in IDS} == NAMES, "each radio is called by its kind and its number in the kind"
    assert await e.ctl.save_radio_settings(FM2, {"beacon": "false"})              # (Send on unticked on the second FM radio; its digipeater is off, as a new radio's is)
    for id in (*HF_IDS, LORA):
        with pytest.raises(RadioError):
            await e.ctl.save_radio_settings(id, {"digipeat": "true"})
    await until_started(lambda: all(r.usable and r.beacon.running for r in e.ctl.radios.all() if r.id != TEXT))      # (connected, settled and its beacon's timer going while the clock stands: each first beacon 30 s in)
    assert [r.id for r in e.ctl.radios.beaconing()] == [FM1, HF1, HF2, HF3, LORA, *((BOARD, WOLF) if beside else ())] and e.ctl.radios.main is not None and e.ctl.radios.main.id == FM1
    if beside:
        monitor = e.ctl.radios.get(TEXT)
        assert monitor is not None
        await until_started(lambda: monitor.state is Source.State.CONNECTED)
        assert {id: e.ctl.radios.name_of(id) for id in (TEXT, BOARD)} == {TEXT: "FM 3", BOARD: "LoRa 2"}, "the two are called by their kind and number as every other radio"
        text.feed(b"OH2TXT-7>APRS,WIDE1-1:!6011.00N/02457.00E>heard on the monitor\r" + b"OH2TXT-7>APRS,WIDE1-1:?APRS?\r")      # (a station, and a query of it heard on the monitor alone)

    await day.until(POST_AT)
    e.ctl.ownbulletins.post("BLN1", "net tonight 20z")
    e.ctl.ownobjects.set("SIXOBJ", "object", 60.2, 24.9, "/", "r", "on two radios", radios=(FM2, LORA))
    await day.until(ASK_AT)
    assert [e.ctl.generalask.ask("aprs").radio, e.ctl.generalask.ask("aprs", radio=LORA).radio] == [FM1, LORA], "Ask around on the main radio, and on the radio named"
    await day.until(SEND_AT)
    book = {s.call: s for s in e.ctl.stationbook.stations()}
    latest = max(book[CITY].heard_on(r).last_at or START for r in HF_IDS)
    city_radio = [r for r in HF_IDS if book[CITY].heard_on(r).last_at == latest]
    sent = {to: await e.ctl.messaging.send(to, f"to {to}") for to in (call_of("Q1ABC", FM1), call_of("Q1ABC", FM2), call_of("Q9KOT", LORA), CITY, NOBODY)}
    await day.until(SEND_AT + timedelta(minutes=10), FINE_SEC)
    await day.until(OFF_FROM - timedelta(minutes=1))
    quiet = await e.ctl.messaging.send(QUIET, f"to {QUIET}")                          # (on the way while OFF is switched off: a city that takes no message, heard last on OFF)
    await day.until(OFF_FROM)
    off = e.ctl.radios.get(OFF)
    assert off is not None and await e.ctl.change_radio(OFF, enabled=False)
    await until_started(lambda: off.state is Source.State.STOPPED)                  # (the clock waits while the radio is stopped and started again, as no minute of the air passes in it)
    still = {s.call for s in e.ctl.stationbook.stations() if s.heard_on(HF2).count}
    assert still == made_up_calls("dummy-hf", HF2) and getattr(e.ctl.messaging.get(quiet.id), "state", "") == "sending", \
        "a Dummy Mercury radio switched off forgets nothing that the other Dummy Mercury radios, still on, hear, and cancels no message to them"
    await day.until(OFF_UNTIL)
    assert await e.ctl.change_radio(OFF, enabled=True)
    await until_started(lambda: off.usable and off.beacon.running)
    await day.until(START + timedelta(days=1))
    stations = e.ctl.stationbook.stations()
    await e.stop()

    out = {r: Counter(kind_of(f) for _, f in day.out(r) if kind_of(f) != "digipeat") for r in IDS}
    assert out == OUT, f"what of ours went out on each radio over the day: {out}"
    repeated = {r: [(at, f) for at, f in day.out(r) if kind_of(f) == "digipeat"] for r in IDS}
    asked = {r: Counter(ax25.decode(p.raw).info for _, p in day.heard(r) if asks_us(ax25.decode(p.raw))) for r in (FM1, FM2)}
    assert asked[FM1] and asked[FM2] and not any(repeated[r] for r in IDS if r != FM1), "the frames that ask for a fill-in are repeated on the FM radio whose digipeater is on, and on no other radio"
    assert all(asked[FM1][f.info] for _, f in repeated[FM1]) and all(str(f.path[0]) == f"{ME}*" for _, f in repeated[FM1]), "what radio 1 heard, with our call in the place of WIDE1-1"
    assert max(Counter(at for at, _ in repeated[FM1]).values()) <= BURST_MAX < len(repeated[FM1]), "no more than its burst at a time"
    paths = {r: Counter((kind_of(f), path_of(f)) for _, f in day.out(r) if kind_of(f) != "digipeat") for r in IDS}
    assert paths == PATHS, f"the paths of our frames on each radio, by kind: {paths}"

    for r, floor in FLOOR_SEC.items():
        beacons = [at for at, f in day.out(r) if kind_of(f) == "beacon"]
        gaps = [(b - a).total_seconds() for a, b in zip(beacons, beacons[1:])]
        longer = [g for g in gaps if g > floor + PAUSE_SEC[r] + STEP_SEC]
        assert min(gaps) >= floor and len(longer) == (r == OFF), f"radio {r}: its beacons {floor // 60} minutes apart, with a pause of up to {PAUSE_SEC[r]} s (and OFF's two hours off): {gaps}"

    heard = {r: {s.call for s in stations if s.heard_on(r).count} for r in IDS}
    assert heard[FM1] == fm_world(FM1) and heard[FM2] == fm_world(FM2) and heard[LORA] == made_up_calls("dummy-lora", LORA), "each radio hears its own world, all of it, and nothing of another's"
    assert all(heard[r] == made_up_calls("dummy-hf", r) for r in HF_IDS), "each Dummy Mercury radio hears the six cities (the same in every Mercury world: neoaprs/dummyworlds.py)"
    assert not any(s.heard_by.keys() - {FM1} for s in stations if s.call in heard[FM1]) and not any(s.heard_by.keys() - {LORA} for s in stations if s.call in heard[LORA])
    assert not [p for at, p in day.heard(OFF) if OFF_FROM < at < OFF_UNTIL] and not [f for at, f in day.out(OFF) if OFF_FROM < at < OFF_UNTIL], "a radio that is off hears and sends nothing"

    done = {to: e.ctl.messaging.get(record.id) for to, record in sent.items()}
    assert {to: getattr(r, "state", None) for to, r in done.items()} == {"Q1ABC": "acked", "Q3ABC": "acked", call_of("Q9KOT", LORA): "acked", CITY: "acked", NOBODY: "failed"}
    went = {to: {r for r in IDS for _, f in day.out(r) if kind_of(f) == "message" and parse_message(f.info[1:]).addressee == to} for to in sent}
    assert {to: radios for to, radios in went.items() if to != CITY} == {"Q1ABC": {FM1}, "Q3ABC": {FM2}, call_of("Q9KOT", LORA): {LORA}, NOBODY: {FM1}} \
        and went[CITY] == {city_radio[0]}, f"each message on the radio of rule 3.2 (the city on the Mercury radio that heard it last, the first by position of those that heard it at once: {city_radio}): {went}"
    tries = sorted((at, r) for r in IDS for at, f in day.out(r) if kind_of(f) == "message" and parse_message(f.info[1:]).addressee == QUIET)
    before, after = {r for at, r in tries if at <= OFF_FROM}, {r for at, r in tries if at > OFF_FROM}
    assert len(tries) == 4 and before == {OFF} and len(after) == 1 and after < set(HF_IDS) - {OFF}, \
        f"a message on its way when its radio is switched off goes on by another Mercury radio that hears the station: {tries}"
    assert getattr(e.ctl.messaging.get(quiet.id), "state", "") == "failed", "(and fails as any message no station answers)"
    if beside:
        monitor = e.ctl.radios.get(TEXT)
        assert monitor is not None and text.connections >= 1 and monitor.stats.bytes_out == 0 and await text.said(1, 0.3) == b"" and not day.out(TEXT), \
            "not one byte on the monitor's line in the whole day, though a station it heard asked for an answer"
        assert {s.call for s in stations if s.heard_on(TEXT).count} == {"OH2TXT-7"}, "what the monitor hears is the station's as anything heard on the air"
        wolf = Counter((kind_of(f), path_of(f)) for _, f in day.out(WOLF))
        assert wolf == {("beacon", "WIDE2-2"): WOLF_BEACONS}, f"the Sound card radio sends its own beacons, every 20 minutes by the symbol's WIDE2-2 (no path of its own), and nothing else: {wolf}"
        gaps = [(b - a).total_seconds() for (a, _), (b, _) in zip(day.out(WOLF), day.out(WOLF)[1:])]
        assert min(gaps) >= 20 * 60 and max(gaps) <= 20 * 60 + STEP_SEC, f"at the station's 20 minutes, as the FM radio's: {gaps}"
        ours = Counter((kind_of(f), path_of(f)) for _, f in day.out(BOARD))
        assert ours == {("beacon", "WIDE1-1"): BOARD_BEACONS} and len(board.transmitted) == BOARD_BEACONS, f"the board keys its own beacons, on LoRa's WIDE1-1, and nothing else: {ours}"
        gaps = [(b - a).total_seconds() for (a, _), (b, _) in zip(day.out(BOARD), day.out(BOARD)[1:])]
        assert min(gaps) >= 30 * 60 and max(gaps) <= 30 * 60 + 300 + STEP_SEC, f"at LoRa's floor and its pause, as the Dummy LoRa radio: {gaps}"


async def test_three_hf_radios_a_message_goes_on_the_one_that_heard_the_station_last(tmp_path: Path, quick: None) -> None:
    """Rule 3.2 among three Mercury radios: a station heard on one Mercury radio alone takes its message there, one heard on two takes it on the one that heard it last, and one heard on an FM radio and then on a Mercury
    radio takes it on the FM radio (a local kind before Mercury, within six hours)."""
    day = Day(tmp_path)
    e = day.e
    await e.start(connected=False)
    for type in ("dummy", "dummy-hf", "dummy-hf", "dummy-lora"):
        await e.ctl.add_radio(type)
    await until_started(lambda: all(r.usable and r.beacon.running for r in e.ctl.radios.all()))
    stories = {"OH7HFA": (HF2,), "OH7HFB": (HF2, HF3), "OH7HFC": (FM2, HF3)}      # each station's radios, in the order they hear it, a minute apart
    for minute, (call, radios) in enumerate(stories.items()):
        for at, radio in enumerate(radios):
            await day.until(START + timedelta(minutes=10 + 3 * minute + at))
            day.hear(radio, call, f"!6200.00N/02500.00E-heard on {NAMES[radio]}")
    await day.until(START + timedelta(minutes=20))
    for call in stories:
        await e.ctl.messaging.send(call, f"to {call}")
    await day.until(START + timedelta(minutes=22), FINE_SEC)
    await e.stop()
    went = {call: {r for r in IDS for _, f in day.out(r) if kind_of(f) == "message" and parse_message(f.info[1:]).addressee == call} for call in stories}
    assert went == {"OH7HFA": {HF2}, "OH7HFB": {HF3}, "OH7HFC": {FM2}}, f"each message on the radio of rule 3.2: {went}"


def test_sim_radios_starts_its_daemon_apart_from_the_terminal(tmp_path: Path) -> None:
    """Ctrl+C in a terminal is a SIGINT to every process of the terminal's group. The daemon of scripts/sim-radios is in a session of its own, so that only the script gets it and stops the daemon with one
    SIGTERM: a daemon that got both would take the second signal, while it closes, as the operator's way out and end at once (exit code 143, the log ending 'NeoAPRS is closing')."""
    if sys.platform == "win32":
        pytest.skip("on Windows the daemon has a process group of its own (CREATE_NEW_PROCESS_GROUP), which Ctrl+C does not reach")
    loader = importlib.machinery.SourceFileLoader("sim_radios", str(ROOT / "scripts" / "sim-radios"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    sim = importlib.util.module_from_spec(spec)
    loader.exec_module(sim)
    child = sim.start_daemon([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path / "data")
    try:
        assert os.getsid(child.pid) == child.pid != os.getsid(0), "the daemon leads a session of its own, apart from the terminal's"
    finally:
        child.kill()
        child.wait()
