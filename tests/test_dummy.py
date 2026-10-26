"""The Dummy radio (neoaprs/dummyscene.py, dummyline.py): made-up traffic around the station that the parser reads like a radio's, stations that answer a message, a digipeater that repeats a position of ours, calls that
can be nobody's, and nothing ever written or sent anywhere. The scene is pure, so it is driven by hand with a clock; the Tnc and the Controller run it on a fast tick."""
import asyncio
import socket
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs import ax25, dummyline, kiss, serialport
from neoaprs.aprsmessage import parse_message
from neoaprs.clock import utc
from neoaprs.dummyline import DUMMY_PATH
from neoaprs.dummyscene import DIGIPEATERS, HELLO, HELSINKI, Scene
from neoaprs.geo import distance_km
from neoaprs.packet import Message, Position
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from neoaprs.tncmode import read_frame
from neoaprs.tncprofile import DUMMY, KISS
from tests.support.clock import FixedClock
from tests.support.env import Env, until

START = utc(2026, 10, 26, 12, 0, 0)
ME = "OH2GBA"


def play(scene: Scene, seconds: int, step: int = 1) -> list[tuple[int, ax25.Frame]]:
    """What the scene puts on the air in `seconds`, second by second: (second, frame)."""
    out: list[tuple[int, ax25.Frame]] = []
    for second in range(0, seconds + 1, step):
        out += [(second, f) for f in scene.due(START + timedelta(seconds=second))]
    return out


def packet_of(frame: ax25.Frame):  # type: ignore[no-untyped-def]
    [kiss_frame] = kiss.KissDecoder().feed(kiss.encode(ax25.encode(frame)))
    read = read_frame(kiss_frame, START)
    assert not isinstance(read, str), read
    return read[0]


def positions(frames: list[tuple[int, ax25.Frame]], call: str) -> list[Position]:
    found = [packet_of(f).decoded for _, f in frames if str(f.source) == call]
    return [d for d in found if isinstance(d, Position)]


# ---- what it makes

def test_a_quarter_of_an_hour_of_traffic_is_valid_ax25_that_the_parser_decodes() -> None:
    frames = play(Scene(None, START), 900)
    assert len(frames) > 60
    for _, frame in frames:
        assert ax25.decode(ax25.encode(frame)) == frame
        assert packet_of(frame).kind != "undecoded", frame.tnc2()


def test_there_is_something_on_the_air_within_half_a_minute_and_every_kind_of_station_is_there() -> None:
    frames = play(Scene(None, START), 900)
    assert frames[0][0] <= 5 and {str(f.source) for s, f in frames if s <= 30} >= {"Q1ABC", "Q4CAR-9", "Q5VAN-7", "Q3WX", "Q2DIG-2", "Q1CLB"}
    kinds = {packet_of(f).kind for _, f in frames}
    assert kinds >= {"position", "status", "message", "object"}
    assert any(isinstance(d := packet_of(f).decoded, Position) and d.weather is not None for _, f in frames)
    assert {str(f.source) for _, f in frames} >= {"Q1ABC", "Q1CLB", "Q8QTH", "Q4CAR-9", "Q5VAN-7", "Q6CAR-1", "Q7WLK-7", "Q3WX", "Q2DIG-2", "Q7DIG-1"}


def test_positions_are_round_the_station_wherever_it_is_and_round_helsinki_when_it_has_no_position() -> None:
    for centre in ((60.2231, 24.7152), (-33.87, 151.21), (40.71, -74.0), (35.68, 139.69), HELSINKI):
        for _, frame in play(Scene(centre, START), 1800, 5):
            decoded = packet_of(frame).decoded
            if isinstance(decoded, Position):
                assert distance_km(*centre, decoded.lat, decoded.lon) < 8, (centre, frame.tnc2())
    assert Scene(None, START).centre == HELSINKI


def test_the_cars_use_mic_e_and_compressed_positions_and_move_along_a_road_at_a_plausible_speed() -> None:
    frames = play(Scene(None, START), 1200)
    mice_car, compressed_van = positions(frames, "Q4CAR-9"), positions(frames, "Q5VAN-7")
    assert len(mice_car) > 15 and len(compressed_van) > 15
    assert any(f.info[:1] == b"`" for _, f in frames if str(f.source) == "Q4CAR-9") and all(not p.compressed for p in mice_car)
    assert all(p.compressed for p in compressed_van)
    for track in (mice_car, compressed_van):
        hops = [distance_km(a.lat, a.lon, b.lat, b.lon) for a, b in zip(track, track[1:])]
        assert 0.1 < sum(hops) / len(hops) < 2.0 and max(hops) < 3.0
        assert all(p.speed_kmh is not None and 5 < p.speed_kmh < 90 for p in track) and all(p.course_deg is not None for p in track)


def test_the_walker_walks() -> None:
    walk = positions(play(Scene(None, START), 1800), "Q7WLK-7")
    assert len(walk) > 20 and all(p.speed_kmh is not None and p.speed_kmh < 7 for p in walk)
    assert 0.05 < distance_km(walk[0].lat, walk[0].lon, walk[-1].lat, walk[-1].lon) + 0.1 < 3


def test_the_weather_station_reports_every_five_minutes_with_values_a_station_could_have() -> None:
    sent = [(s, f) for s, f in play(Scene(None, START), 3600) if str(f.source) == "Q3WX" and not any(a.repeated for a in f.path)]
    gaps = [b[0] - a[0] for a, b in zip(sent, sent[1:])]
    assert 10 <= len(sent) <= 14 and all(250 <= g <= 350 for g in gaps)
    for _, frame in sent:
        weather = packet_of(frame).decoded.weather                                  # type: ignore[union-attr]
        assert weather is not None and weather.temp_c is not None and weather.pressure_hpa is not None and weather.humidity is not None and weather.wind_kmh is not None
        assert -30 < weather.temp_c < 40 and 950 < weather.pressure_hpa < 1060 and 1 <= weather.humidity <= 100 and 0 <= weather.wind_kmh < 60


def test_two_digipeaters_with_phg_repeat_the_others_with_a_star_in_the_path() -> None:
    frames = play(Scene(None, START), 1800)
    beacons = [f for _, f in frames if str(f.source) in DIGIPEATERS]
    assert {str(f.source) for f in beacons} == set(DIGIPEATERS) and all(b"PHG" in f.info for f in beacons)
    repeats = [f for _, f in frames if any(a.repeated for a in f.path) and str(f.source) not in DIGIPEATERS]
    assert len(repeats) > 30
    for f in repeats:
        assert str(f.path[0]) in {d + "*" for d in DIGIPEATERS}, f.tnc2()
    assert {str(f.path[0]) for f in repeats} == {d + "*" for d in DIGIPEATERS}
    first = {(str(f.source), f.info) for _, f in frames if not any(a.repeated for a in f.path)}
    assert all((str(f.source), f.info) in first for f in repeats)                  # (what is repeated was sent before)


def test_there_are_objects_a_bulletin_and_a_status() -> None:
    packets = [packet_of(f) for _, f in play(Scene(None, START), 2400)]
    assert {p.decoded.name for p in packets if p.kind == "object"} == {"FIELDDAY", "PARKING"}
    board = [p for p in packets if p.kind == "message" and isinstance(p.decoded, Message) and p.decoded.addressee.startswith("BLN")]
    assert len(board) >= 1 and board[0].decoded.addressee == "BLN1"            # type: ignore[union-attr]
    assert any(p.kind == "status" for p in packets)


def test_every_call_is_on_the_itu_q_prefix_which_no_country_has_so_none_is_a_real_station() -> None:
    scene = Scene(None, START)
    frames = play(scene, 1800)
    for _, f in frames:
        assert str(f.source).startswith("Q"), f.tnc2()
        for hop in f.path:
            assert str(hop).startswith(("Q", "WIDE")), f.tnc2()
    scene.react(air_from_us(b":Q1ABC    :hi{1"), START + timedelta(seconds=1801))
    for f in scene.due(START + timedelta(seconds=1900)):
        assert str(f.source).startswith("Q")
    assert all(a.call.startswith("Q") for a in scene.actors)


def test_the_same_seed_makes_the_same_traffic_and_another_seed_another() -> None:
    a, b, c = (play(Scene(None, START, seed), 600) for seed in (1, 1, 2))
    assert a == b and a != c


def air_from_us(info: bytes, path: str = "WIDE1-1,WIDE2-1") -> ax25.Frame:
    return ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse(ME), tuple(ax25.Address.parse(p) for p in path.split(",")), info=info)


# ---- what answers

def quiet() -> Scene:
    """A scene whose stations send nothing by themselves for a day (they still answer)."""
    scene = Scene(None, START)
    for actor in scene.actors:
        actor.next_at = START + timedelta(days=1)
    return scene


def test_a_message_to_a_station_is_acked_after_a_moment_and_answered_after_a_few_seconds() -> None:
    scene = quiet()
    scene.react(air_from_us(b":" + b"Q1ABC    :Hello Q1ABC{12"), START)
    got = play(scene, 10)
    [ack] = [(s, f) for s, f in got if parse_message(f.info[1:]).ack_id]
    assert ack[0] <= 2 and str(ack[1].source) == "Q1ABC" and parse_message(ack[1].info[1:]).ack_id == "12" and parse_message(ack[1].info[1:]).addressee == ME
    [answer] = [(s, f) for s, f in got if not parse_message(f.info[1:]).ack_id]
    said = parse_message(answer[1].info[1:])
    assert 3 <= answer[0] <= 7 and said.text == HELLO and said.addressee == ME and said.msg_id
    assert HELLO == "Hello from the dummy radio"


def test_a_retry_of_the_message_is_acked_again_and_not_answered_again() -> None:
    scene = quiet()
    scene.react(air_from_us(b":Q4CAR-9  :Hi{7"), START)
    scene.react(air_from_us(b":Q4CAR-9  :Hi{7"), START + timedelta(seconds=30))
    said = [f for _, f in play(scene, 90)]
    acks = [f for f in said if parse_message(f.info[1:]).ack_id]
    texts = [f for f in said if not parse_message(f.info[1:]).ack_id]
    assert len(acks) == 2 and len(texts) == 1


def test_a_message_to_nobody_to_a_digipeater_or_an_ack_of_ours_gets_no_answer() -> None:
    scene = quiet()
    for body in (b":Q9XYZ    :Hi{1", b":Q2DIG-2  :Hi{1", b":OH2XYZ   :Hi{1", b":Q1ABC    :ack4", b":Q1ABC    :rej4", b"not a message"):
        scene.react(air_from_us(body), START)
    assert play(scene, 60) == []


def test_a_message_without_a_number_is_answered_but_not_acked() -> None:
    scene = quiet()
    scene.react(air_from_us(b":Q8QTH    :Are you there"), START)
    got = [parse_message(f.info[1:]) for _, f in play(scene, 30)]
    assert [m.text for m in got] == [HELLO] and got[0].ack_id is None


def test_the_club_station_is_a_qru_server_that_lists_its_groups_and_sends_the_objects_of_a_group_with_a_closing_line() -> None:
    scene = quiet()
    scene.react(air_from_us(b":QRU      :INFO"), START)
    [(after, listing)] = play(scene, 30)
    assert after <= 4 and str(listing.source) == "Q1CLB" and parse_message(listing.info[1:]).text == "de Q1CLB:FOOD(2) RP70(1) Max 5@50km" and parse_message(listing.info[1:]).msg_id is None
    scene.react(air_from_us(b":QRU      :?food 20"), START + timedelta(seconds=60))
    got = [f for second, f in play(scene, 90) if second >= 60]
    assert [f.info[:1] for f in got] == [b";", b";", b":"] and [f.info[1:10].decode().strip() for f in got[:2]] == ["CAFE", "KIOSK"]
    assert parse_message(got[2].info[1:]).text == "Sent 2 FOOD Objects Max 5@50km de Q1CLB" and all(str(f.source) == "Q1CLB" for f in got)


def test_a_request_to_qru_for_a_group_it_does_not_serve_or_that_is_none_gets_no_answer() -> None:
    scene = quiet()
    for body in (b":QRU      :HOSP", b":QRU      :hello there", b":QRU      :ack1"):
        scene.react(air_from_us(body), START)
    assert play(scene, 30) == []


def test_a_position_of_ours_is_repeated_by_a_digipeater_now_and_then_the_first_always() -> None:
    scene = quiet()
    beacon = air_from_us(b"=6010.00N/02456.00E-test")
    echoed = []
    for n in range(20):
        at = START + timedelta(seconds=100 * n)
        scene.react(beacon, at)
        echoed.append([f for f in scene.due(at + timedelta(seconds=10))])
    assert len(echoed[0]) == 1
    sent = echoed[0][0]
    assert str(sent.source) == ME and [str(a) for a in sent.path] == ["Q2DIG-2*", "WIDE2-1"] and sent.info == beacon.info
    counts = [len(e) for e in echoed]
    assert set(counts) == {0, 1} and 5 < sum(counts) < 19


def test_a_frame_of_a_made_up_station_is_not_repeated_back() -> None:
    scene = quiet()
    scene.react(ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("Q3WX"), info=b"!6010.00N/02456.00E_"), START)
    assert play(scene, 30) == []


# ---- the Tnc

def test_the_dummy_is_a_profile_that_is_first_in_no_list_and_needs_neither_a_port_nor_a_speed() -> None:
    assert DUMMY.transport == "dummy" and DUMMY.baud is None and DUMMY.enter == () and not DUMMY.can_probe and not DUMMY.detect_command_mode
    assert DUMMY.name == "Dummy (no radio, made-up traffic)"


@pytest.fixture
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dummyline, "TICK_SEC", 0.01)


def refuse_the_world(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Whatever opens a serial port, a pseudo-terminal or a socket is a failure of the test; the record is empty when nothing tried."""
    tried: list[str] = []

    def no(what: str):  # type: ignore[no-untyped-def]
        def refuse(*a: object, **k: object) -> None:
            tried.append(what)
            raise AssertionError(f"the Dummy radio opened {what}")
        return refuse

    monkeypatch.setattr(serialport.serial, "serial_for_url", no("a serial port"))
    monkeypatch.setattr(serialport.SerialPort, "_open_blocking", no("a line"))
    monkeypatch.setattr(socket.socket, "connect", no("a socket"))
    monkeypatch.setattr(socket, "create_connection", no("a connection"))
    monkeypatch.setattr(asyncio, "open_connection", no("a connection"))
    return tried


async def test_the_tnc_with_the_dummy_profile_connects_hears_made_up_stations_and_opens_nothing(fast: None, monkeypatch: pytest.MonkeyPatch) -> None:
    tried = refuse_the_world(monkeypatch)
    clock = FixedClock(START)
    tnc = Tnc(profile=DUMMY, port=DUMMY_PATH, clock=clock)
    tnc.where = lambda: (60.2231, 24.7152)
    heard: list[tuple[str, bool]] = []
    tnc.packet.connect(lambda p: heard.append((p.source, tnc.is_dummy and p.via == "dummy")))
    await tnc.start()
    assert tnc.state is Source.State.CONNECTED and tnc.usable and tnc.path == DUMMY_PATH and tnc.is_dummy
    assert "opened the dummy radio" in tnc.lines[0] and "at 9600" not in tnc.lines[0]
    for _ in range(40):
        clock.advance(30)
        await asyncio.sleep(0.03)
    await tnc.stop()
    assert len(heard) > 50 and all(call.startswith("Q") and dummy for call, dummy in heard)       # (every packet of it was marked `dummy` where the Tnc made it, while the Tnc said it is the dummy)
    assert tnc.stats.rejected == 0 and tnc.stats.packets == len(heard)
    assert tried == []
    assert "dummy radio" in tnc.describe() and "nothing goes on the air" in tnc.describe()


async def test_a_real_radios_tnc_does_not_say_it_is_the_dummy() -> None:
    assert not Tnc(profile=KISS, clock=FixedClock(START)).is_dummy and not Source("x").is_dummy


async def test_what_the_tnc_sends_to_the_dummy_goes_nowhere_a_message_is_acked_and_answered_and_a_beacon_is_repeated(fast: None, monkeypatch: pytest.MonkeyPatch) -> None:
    tried = refuse_the_world(monkeypatch)
    clock = FixedClock(START)
    tnc = Tnc(profile=DUMMY, port=DUMMY_PATH, clock=clock)
    heard: list[tuple[str, str]] = []
    vias: set[str] = set()
    tnc.packet.connect(lambda p: vias.add(p.via))
    tnc.packet.connect(lambda p: heard.append((p.direction, p.raw.decode("latin-1")[0:0] + p.source + ">" + (p.decoded.text if isinstance(p.decoded, Message) else p.info.decode("latin-1")))))
    await tnc.start()
    await until(lambda: tnc.confirmed)
    assert tnc.send_frame(air_from_us(b":Q1ABC    :Hello{5"))
    assert tnc.send_frame(air_from_us(b"=6010.00N/02456.00E-me"))
    assert tnc.stats.bytes_out > 0
    for _ in range(30):
        clock.advance(1)
        await asyncio.sleep(0.03)
    await tnc.stop()
    text = [h for h in heard if h[0] == "in" and h[1].startswith("Q1ABC>")]
    assert any(t[1] == f"Q1ABC>{HELLO}" for t in text)
    assert any(d == "in" and s.startswith(f"{ME}>=6010") for d, s in heard)                     # the digipeater's repeat of our beacon
    assert [d for d, _ in heard if d == "out"] == ["out", "out"]
    assert vias == {"dummy"}, "what is heard and what is sent are both marked dummy"
    assert tried == []


async def test_stopping_the_tnc_ends_the_dummy_for_good(fast: None) -> None:
    clock = FixedClock(START)
    tnc = Tnc(profile=DUMMY, port=DUMMY_PATH, clock=clock)
    await tnc.start()
    port = tnc._port
    assert port is not None and port.is_open
    await tnc.stop()
    await asyncio.sleep(0.05)
    assert not port.is_open and tnc.state is Source.State.STOPPED


# ---- the daemon

async def test_the_daemon_with_the_dummy_radio_type_has_stations_on_the_map_and_remembers_no_port(tmp_path: Path, fast: None) -> None:
    e = Env(tmp_path, radio=False, settings={"tnc/profile": "dummy", "station/lat": "60.2231", "station/lon": "24.7152"})
    await e.start()
    await until(lambda: e.tnc.state is Source.State.CONNECTED)
    assert e.tnc.is_dummy and e.ctl.config.serial_last_port == "" and e.ctl.config.serial_port == ""
    for _ in range(60):
        e.now.advance(10)                                                               # type: ignore[attr-defined]
        await asyncio.sleep(0.02)
        if len(e.ctl.stationbook.stations()) > 8:
            break
    calls = {s.call for s in e.ctl.stationbook.stations()}
    assert {"Q1ABC", "Q4CAR-9", "Q2DIG-2"} <= calls
    near = [s for s in e.ctl.stationbook.stations() if s.call.startswith("Q") and s.lat is not None and s.lon is not None]
    assert near and all(distance_km(60.2231, 24.7152, s.lat, s.lon) < 8 for s in near if s.lat is not None and s.lon is not None)
    assert e.ctl.config.serial_last_port == ""
    assert replace(e.ctl.config).profile.transport == "dummy"
