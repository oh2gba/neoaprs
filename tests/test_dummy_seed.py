"""Each Dummy radio has a world of its own (neoaprs/dummyscene.py, dummyline.py, tnc.py): the seed of its scene is the radio's id, the seed 1 gives the world there always was, byte for byte, and any other
seed the same town with other calls at other places. So two Dummy radios show different stations, and every packet says which radio it came on."""
import asyncio
import hashlib
from datetime import timedelta

import pytest

from neoaprs import ax25, dummyline, kiss
from neoaprs.aprsmessage import parse_message
from neoaprs.clock import utc
from neoaprs.dummyline import DUMMY_PATH
from neoaprs.dummyroutes import around
from neoaprs.dummyscene import HELLO, NAME_MAX, TURN_DEG, Scene, call_of, name_of
from neoaprs.geo import bearing_deg, distance_km
from neoaprs.packet import ObjectReport, Packet, Position
from neoaprs.stationbook import StationBook
from neoaprs.tnc import Tnc
from neoaprs.tncmode import read_frame
from neoaprs.tncprofile import DUMMY, DUMMY_HF
from tests.support.clock import FixedClock

START = utc(2026, 10, 26, 12, 0, 0)
ME = "OH2GBA"
HOME = (60.2231, 24.7152)
FIRST_WORLD = {"Q1ABC", "Q1CLB", "Q8QTH", "Q4CAR-9", "Q5VAN-7", "Q6CAR-1", "Q7WLK-7", "Q2DIG-2", "Q7DIG-1", "Q3WX"}       # the stations of the Dummy radio as they always were
FIRST_HOUR = (652, "75a1947d3dbd659a31d9276c9b040e4daabfe5c6c7b45f8b45630c539c26d3b0")                             # an hour of them, counted and hashed with the scene as it was before it took other seeds


@pytest.fixture
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dummyline, "TICK_SEC", 0.01)


def air_from_us(info: bytes, path: str = "WIDE1-1,WIDE2-1") -> ax25.Frame:
    return ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse(ME), tuple(ax25.Address.parse(p) for p in path.split(",")), info=info)


def play(scene: Scene, seconds: int) -> list[ax25.Frame]:
    out: list[ax25.Frame] = []
    for second in range(seconds + 1):
        out += scene.due(START + timedelta(seconds=second))
    return out


def packet_of(frame: ax25.Frame) -> Packet:
    [kiss_frame] = kiss.KissDecoder().feed(kiss.encode(ax25.encode(frame)))
    read = read_frame(kiss_frame, START)
    assert not isinstance(read, str), read
    return read[0]


def places(seed: int) -> dict[str, tuple[float, float]]:
    """Where each fixed station and object of the world is, by the call (or name) it has in the first world."""
    found: dict[str, tuple[float, float]] = {}
    for frame in play(Scene(HOME, START, seed), 1300):
        decoded = packet_of(frame).decoded
        if isinstance(decoded, Position):
            found.setdefault(str(frame.source), (decoded.lat, decoded.lon))
        elif isinstance(decoded, ObjectReport):
            found.setdefault(decoded.name, (decoded.position.lat, decoded.position.lon))
    return found


# ---- the first world is the one there was

def test_the_world_of_the_seed_1_is_byte_for_byte_the_one_there_always_was() -> None:
    scene = Scene(HOME, START, 1)
    digest, count = hashlib.sha256(), 0
    for second in range(3601):
        now = START + timedelta(seconds=second)
        if second == 100:
            scene.react(air_from_us(b":QRU      :RP70{1"), now)
        if second == 200:
            scene.react(air_from_us(b":Q1ABC    :hello{2"), now)
        if second in (300, 900, 1500):
            scene.react(air_from_us(b"=6013.39N/02442.91E-me"), now)
        for frame in scene.due(now):
            digest.update(ax25.encode(frame))
            count += 1
    assert (count, digest.hexdigest()) == FIRST_HOUR, "its beacons, its answers to a message and to QRU and its repeats of our position: the radio 1 that is a Dummy plays what it played"


def test_the_first_world_has_its_calls_its_objects_and_its_places() -> None:
    scene = Scene(HOME, START)
    assert scene.seed == 1 and {a.call for a in scene.actors} == FIRST_WORLD == {call_of(call, 1) for call in FIRST_WORLD}
    assert (name_of("FIELDDAY", 1), name_of("PARKING", 1)) == ("FIELDDAY", "PARKING")
    assert scene.where(2.1, 1.4) == around(HOME, 2.1, 1.4) and scene.where(-4.1, -2.2) == around(HOME, -4.1, -2.2), "not turned: to the last digit where it was"


# ---- another seed is another world

def test_two_seeds_share_no_station_and_no_object() -> None:
    seeds = (1, 2, 3, 4, 7, 10, 11, 12, 21, 31, 112)
    worlds = {seed: {str(f.source) for f in play(Scene(HOME, START, seed), 700)} | {a.call for a in Scene(HOME, START, seed).actors} for seed in seeds}
    for seed, calls in worlds.items():
        assert len(calls) == len(FIRST_WORLD) and calls == {call_of(call, seed) for call in FIRST_WORLD}, seed
        for call in calls:
            assert call.startswith("Q") and str(ax25.Address.parse(call)) == call, f"{call}: on the Q prefix, which is nobody's, and a call a frame carries"
    for a in seeds:
        for b in seeds:
            assert a == b or not worlds[a] & worlds[b], f"the worlds of the seeds {a} and {b} share {worlds[a] & worlds[b]}"
    names = [name_of(name, seed) for seed in seeds for name in ("FIELDDAY", "PARKING")]
    assert len(set(names)) == len(names) and all(len(name) <= NAME_MAX for name in names) and name_of("FIELDDAY", 3) == "FIELDDAY3" and name_of("FIELDDAY", 112) == "FIELDD112"


def test_a_call_moves_on_by_its_digit_and_then_by_its_last_letter() -> None:
    assert [call_of("Q1ABC", seed) for seed in (1, 2, 3, 10, 11, 12, 21)] == ["Q1ABC", "Q2ABC", "Q3ABC", "Q0ABC", "Q1ABD", "Q2ABD", "Q1ABE"]
    assert (call_of("Q4CAR-9", 3), call_of("Q7DIG-1", 5), call_of("Q3WX", 9)) == ("Q6CAR-9", "Q1DIG-1", "Q1WX"), "the SSID stays"


def test_the_objects_of_another_world_have_other_names_and_its_club_reports_them() -> None:
    packets = [packet_of(f) for f in play(Scene(HOME, START, 3), 1300)]
    reports = {(p.decoded.name, p.source) for p in packets if isinstance(p.decoded, ObjectReport)}
    assert reports == {("FIELDDAY3", "Q3CLB"), ("PARKING3", "Q3CLB")}
    assert all(p.kind != "undecoded" for p in packets), "every packet of it is read as the first world's are"


def test_another_world_is_the_same_town_turned_round_the_station() -> None:
    first, third = places(1), places(3)
    assert len(first) == len(third) >= 11
    for call, place in first.items():
        other = third[name_of(call, 3) if call in ("FIELDDAY", "PARKING") else call_of(call, 3)]
        if call in ("Q4CAR-9", "Q5VAN-7", "Q6CAR-1", "Q7WLK-7"):
            continue                                                             # (the movers start at another point of their rounds: another draw)
        assert distance_km(*HOME, *other) == pytest.approx(distance_km(*HOME, *place), abs=0.03), f"{call}: as far from us"
        assert (bearing_deg(*HOME, *other) - bearing_deg(*HOME, *place)) % 360 == pytest.approx(2 * TURN_DEG, abs=1.0), f"{call}: turned by {TURN_DEG} degrees for each seed after the first"
        assert distance_km(*place, *other) > 0.5, f"{call}: not at the place of its twin"


def test_a_mover_of_a_turned_world_heads_where_it_goes() -> None:
    """The course a car, a van or a walker sends is turned with its places: the way from one of its positions to the next is, mostly, the way it says it heads (the corners of its round aside; unturned, a
    mover of the seed 3 would head 110 degrees off)."""
    movers = ("Q4CAR-9", "Q5VAN-7", "Q6CAR-1", "Q7WLK-7")
    for seed in (1, 3):
        track: dict[str, list[Position]] = {}
        for frame in play(Scene(HOME, START, seed), 1800):
            decoded = packet_of(frame).decoded
            if isinstance(decoded, Position) and decoded.course_deg is not None and str(frame.source) in {call_of(c, seed) for c in movers}:
                track.setdefault(str(frame.source), []).append(decoded)
        assert len(track) == len(movers), track.keys()
        off = sorted(abs((bearing_deg(a.lat, a.lon, b.lat, b.lon) - (b.course_deg or 0) + 180) % 360 - 180) for positions in track.values() for a, b in zip(positions, positions[1:], strict=False))
        assert len(off) > 100 and off[len(off) // 2] < 35, f"seed {seed}: the movers head {off[len(off) // 2]:.0f} degrees off the way they go"


def test_the_same_seed_is_the_same_world_at_every_start_and_its_draws_are_its_own() -> None:
    a, b, c = (play(Scene(HOME, START, seed), 900) for seed in (3, 3, 4))
    assert a == b and len(a) > 100
    assert [f.info for f in a] != [f.info for f in c], "other calls and other draws"


def test_a_station_of_another_world_answers_under_its_own_call_and_its_digipeater_repeats_us() -> None:
    scene = Scene(HOME, START, 3)
    play(scene, 60)
    at = START + timedelta(seconds=61)
    scene.react(air_from_us(b":Q3ABC    :Hello{5"), at)
    scene.react(air_from_us(b":Q1ABC    :Hello{6"), at)                        # (the first world's home station: nobody here)
    scene.react(air_from_us(b"=6013.39N/02442.91E-me"), at)
    scene.react(air_from_us(b":QRU      :RP70{7"), at)
    heard = [f for f in scene.due(at + timedelta(seconds=30))]
    to_us = [(str(f.source), parse_message(f.info[1:])) for f in heard if f.info[:1] == b":" and parse_message(f.info[1:]).addressee == ME]
    assert ("Q3ABC", "5") in [(source, m.ack_id) for source, m in to_us] and ("Q3ABC", HELLO) in [(source, m.text) for source, m in to_us]
    assert not [m for source, m in to_us if m.ack_id == "6"] and "Q1ABC" not in {source for source, _ in to_us}
    assert any(str(f.source) == ME and str(f.path[0]) == "Q4DIG-2*" for f in heard), "our position, repeated by this world's digipeater"
    club = [f for f in heard if str(f.source) == "Q3CLB" and (f.info[:1] == b";" or b" de " in f.info)]
    assert len(club) >= 2 and any(f.info.endswith(b"de Q3CLB") for f in club) and not any(b"Q1CLB" in f.info for f in heard), "the QRU server is this world's club, in its words too"


# ---- the seed is the radio's id

async def test_two_dummy_radios_show_different_stations_each_stamped_with_its_radio(fast: None) -> None:
    clock = FixedClock(START)
    book = StationBook(clock)
    heard: dict[int, list[Packet]] = {1: [], 3: []}
    tncs = []
    for radio_id in (1, 3):
        tnc = Tnc(profile=DUMMY, port=DUMMY_PATH, clock=clock)
        tnc.radio_id = radio_id                                                 # (as its driver sets it: neoaprs/tncdriver.py)
        tnc.where = lambda: HOME
        tnc.packet.connect(lambda p, radio_id=radio_id: heard[radio_id].append(p))
        tnc.packet.connect(lambda p: book.take(p) and None)
        tncs.append(tnc)
        await tnc.start()
    for _ in range(40):
        clock.advance(30)
        await asyncio.sleep(0.03)
    for tnc in tncs:
        await tnc.stop()
    first, third = ({p.source for p in heard[radio_id]} for radio_id in (1, 3))
    assert first == FIRST_WORLD and third == {call_of(call, 3) for call in FIRST_WORLD} and not first & third, "two Dummy radios: two worlds"
    assert all(p.radio_id == radio_id and p.via == "dummy" for radio_id in (1, 3) for p in heard[radio_id]), "every packet says the radio it came on"
    assert {p.radio for p in heard[1]} == {"fm"} and {p.radio for p in heard[3]} == {""}, "the old word knows radio 1; a third radio has none"
    stations = {s.call: s for s in book.stations()}
    assert len(stations) == 2 * (len(FIRST_WORLD) + 2), "ten stations and two objects of each"
    for call, station in stations.items():
        by = set(station.heard_by)
        assert by == ({1} if call in FIRST_WORLD | {"FIELDDAY", "PARKING"} else {3}), f"{call} was heard by {by}"
    assert stations["Q1ABC"].heard_on(1).count == stations["Q1ABC"].packets and stations["Q3ABC"].heard_on(3).count == stations["Q3ABC"].packets
    assert distance_km(stations["Q1CLB"].lat, stations["Q1CLB"].lon, stations["Q3CLB"].lat, stations["Q3CLB"].lon) > 0.5      # type: ignore[arg-type]


async def test_the_scene_of_a_dummy_radio_is_made_with_the_id_of_its_radio_as_the_seed(fast: None, monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[int] = []
    make_port = dummyline.DummyPort.__init__

    def spy(self: dummyline.DummyPort, *args: object, seed: int = 1, **kw: object) -> None:
        made.append(seed)
        make_port(self, *args, seed=seed, **kw)                                 # type: ignore[arg-type]

    monkeypatch.setattr(dummyline.DummyPort, "__init__", spy)
    for profile, radio_id in ((DUMMY, 1), (DUMMY, 5), (DUMMY_HF, 2), (DUMMY_HF, 6)):
        tnc = Tnc(profile=profile, port=DUMMY_PATH, clock=FixedClock(START))
        tnc.radio_id = radio_id                                                 # (as its driver sets it)
        await tnc.start()
        await tnc.stop()
        assert made.pop() == radio_id and not made, f"{profile.key} as radio {radio_id}"
    plain = Tnc(profile=DUMMY, port=DUMMY_PATH, clock=FixedClock(START))
    assert plain.radio_id == 1, "a Tnc no driver has set is radio 1, and plays the first world"
