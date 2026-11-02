"""The Dummy HF radio (neoaprs/dummyhfscene.py, dummyline.py, the profile `dummy-hf` of tncprofile.py): a handful of distant fixed stations whose beacons come every half hour to an hour with the HF pause, the first within
two minutes, every frame direct, the nearest answering a message at the pace of HF, calls that can be nobody's; the Tnc on it marks every packet `dummy` on the radio `hf` and opens nothing; the daemon with the
HF radio as the Dummy starts no modem for a radio but the speaker, which is handed our frames to be heard, and nothing of it goes on any air (the HF world: a dummy station beside two real ones)."""
import asyncio
import contextlib
import logging
import os
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs import ax25, dummyline, kiss
from neoaprs.aprsmessage import parse_message
from neoaprs.clock import utc
from neoaprs.dummyhfscene import ACK_AFTER_SEC, FIRST_BEACONS_SEC, HELLO, STATIONS, HfScene
from neoaprs.dummyline import DUMMY_PATH
from neoaprs.geo import distance_km
from neoaprs.mercury import DELIVERY_SEC
from neoaprs.mercuryspeaker import BLOCK_BYTES, SILENCE, SpeakerAudio
from neoaprs.packet import Position
from neoaprs.radiorules import HF_BEACON_JITTER_SEC
from neoaprs.radios import hf_is_mercury
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from neoaprs.tncmode import read_frame
from neoaprs.tncprofile import DUMMY_HF, HF_PROFILES, MERCURY, hf_profile_of
from tests.support import fakemercury
from tests.support.clock import FixedClock
from tests.support.env import Env, until
from tests.support.mercuryworld import World
from tests.test_dummy import refuse_the_world

START = utc(2026, 11, 2, 12, 0, 0)
HELSINKI = (60.17, 24.94)
ME = "OH2GBA"


def play(scene: HfScene, seconds: int, step: int = 5) -> list[tuple[int, ax25.Frame]]:
    out: list[tuple[int, ax25.Frame]] = []
    for t in range(0, seconds + 1, step):
        out += [(t, f) for f in scene.due(START + timedelta(seconds=t))]
    return out


def test_the_profile_is_the_hf_radios_second_type_with_the_rules_of_hf_and_no_line() -> None:
    assert HF_PROFILES == (MERCURY, DUMMY_HF) and hf_profile_of("dummy-hf") is DUMMY_HF and hf_profile_of(" mercury ") is MERCURY
    assert DUMMY_HF.transport == "dummy" and DUMMY_HF.rules.kind == "hf" and DUMMY_HF.max_frame == 123 and not DUMMY_HF.can_probe and DUMMY_HF.baud is None
    with pytest.raises(Exception, match="not a type of the HF radio") as refused:
        hf_profile_of("dummy")
    assert getattr(refused.value, "code", "") == "setting.not_hf_profile"


def test_the_stations_are_fixed_hundreds_of_kilometres_away_on_the_q_prefix_and_every_frame_is_direct_and_decodes() -> None:
    frames = play(HfScene(HELSINKI, START), 3 * 3600)
    assert frames, "something came"
    calls = {str(f.source) for _, f in frames}
    assert calls == {s.call for s in STATIONS} and all(c.startswith("Q") and 4 <= len(c) <= 6 for c in calls)
    for _, frame in frames:
        [kiss_frame] = kiss.KissDecoder().feed(kiss.encode(ax25.encode(frame)))
        read = read_frame(kiss_frame, START, True, "hf")
        assert not isinstance(read, str), read
        packet = read[0]
        assert packet.via == "dummy" and packet.radio == "hf" and frame.path == () and isinstance(packet.decoded, Position)
        assert 140 < distance_km(*HELSINKI, packet.decoded.lat, packet.decoded.lon) < 1200
        assert packet.decoded.course_deg is None and packet.decoded.speed_kmh is None and packet.decoded.messaging, "a fixed station that takes messages"


def test_the_first_beacons_come_within_two_minutes_and_then_every_half_hour_to_an_hour_with_the_random_pause() -> None:
    scene = HfScene(HELSINKI, START)
    first = play(scene, 130, step=1)
    assert [t for t, _ in first] == [int(s) for s in FIRST_BEACONS_SEC] and len({str(f.source) for _, f in first}) == len(STATIONS)
    assert first[0][0] <= 10, "the map fills while the operator watches"
    later = play(HfScene(HELSINKI, START), 6 * 3600, step=1)
    for station in STATIONS:
        times = [t for t, f in later if str(f.source) == station.call]
        gaps = [b - a for a, b in zip(times, times[1:])]
        assert gaps and all(station.every_sec <= gap <= station.every_sec + HF_BEACON_JITTER_SEC + 1 for gap in gaps), (station.call, gaps)
        assert 1800 <= station.every_sec <= 3600
    assert len({str(f.source) for _, f in later}) == len(STATIONS) and len(later) < 60, "an HF channel is a quiet one"


def from_us(info: bytes) -> ax25.Frame:
    return ax25.Frame(ax25.Address("APRS"), ax25.Address.parse(ME), (), info=info)


def test_the_nearest_station_acks_a_message_a_frame_each_way_later_and_answers_once_nothing_else_is_repeated() -> None:
    scene = HfScene(HELSINKI, START)
    play(scene, 200)                                                             # (the first beacons are out of the way)
    talker = next(s for s in STATIONS if s.answers)
    scene.react(from_us(b":" + talker.call.ljust(9).encode() + b":Hello{7"), START + timedelta(seconds=200))
    scene.react(from_us(b"=6010.00N/02456.00E-me"), START + timedelta(seconds=200))
    heard = [(t - 200, f) for t, f in play(scene, 260, step=1) if t > 200]
    acks = [(t, f) for t, f in heard if parse_message(f.info[1:]).ack_id == "7"]
    texts = [(t, f) for t, f in heard if parse_message(f.info[1:]).text == HELLO]
    assert len(acks) == 1 and len(texts) == 1 and str(acks[0][1].source) == talker.call and str(texts[0][1].source) == talker.call
    assert abs(acks[0][0] - ACK_AFTER_SEC) < 1 and ACK_AFTER_SEC == 2 * DELIVERY_SEC and texts[0][0] > acks[0][0], "the ack a frame's time each way later, the text after it"
    assert all(str(f.source) != ME for _, f in heard), "no digipeater on HF: nothing of ours comes back"
    scene.react(from_us(b":" + talker.call.ljust(9).encode() + b":Hello{7"), START + timedelta(seconds=300))       # (a retry: acked again, not answered again)
    again = [f for t, f in play(scene, 400, step=1) if t > 300]
    assert [parse_message(f.info[1:]).ack_id for f in again] == ["7"]
    other = next(s for s in STATIONS if not s.answers)
    scene.react(from_us(b":" + other.call.ljust(9).encode() + b":Hello{8"), START + timedelta(seconds=400))
    assert [f for t, f in play(scene, 500, step=1) if t > 400] == [], "the other stations take a message and stay quiet, as most do"


@pytest.fixture
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dummyline, "TICK_SEC", 0.01)


class Spoken:
    def __init__(self) -> None:
        self.frames: list[bytes] = []

    def play(self, data: bytes) -> None:
        self.frames.append(data)


async def test_the_tnc_with_the_dummy_hf_profile_hears_the_stations_on_the_radio_hf_marked_dummy_plays_what_it_sends_and_opens_nothing(fast: None, monkeypatch: pytest.MonkeyPatch) -> None:
    tried = refuse_the_world(monkeypatch)
    clock = FixedClock(START)
    tnc = Tnc(profile=DUMMY_HF, port=DUMMY_PATH, clock=clock)
    spoken = Spoken()
    tnc.modem = spoken                                                           # type: ignore[assignment]
    heard: list[tuple[str, str, str, str]] = []
    tnc.packet.connect(lambda p: heard.append((p.direction, p.source, p.via, p.radio)))
    await tnc.start()
    assert tnc.state is Source.State.CONNECTED and tnc.usable and tnc.is_dummy and tnc.rules.kind == "hf" and tnc.max_frame == 123
    await until(lambda: tnc.confirmed)
    assert tnc.send_frame(from_us(b":Q3TKU    :Hello{5"))
    for _ in range(40):
        clock.advance(5)
        await asyncio.sleep(0.02)
    await tnc.stop()
    assert len(spoken.frames) == 1 and spoken.frames[0].startswith(b"\xc0"), "what we sent went to the speaker as KISS bytes"
    assert {s for d, s, _, _ in heard if d == "in"} >= {"Q3TKU", "Q5OUL"} and all(v == "dummy" and r == "hf" for _, _, v, r in heard)
    assert any(d == "in" and s == "Q3TKU" for d, s, _, _ in heard) and tnc.stats.rejected == 0
    assert tried == [] and "dummy HF radio" in tnc.describe() and "nothing goes on the air" in tnc.describe()


async def test_the_daemon_with_the_dummy_hf_radio_has_distant_stations_heard_on_hf_starts_mercury_as_the_speaker_and_plays_the_beacon(tmp_path: Path, fast: None, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="neoaprs.mercury")
    e = Env(tmp_path, radio=False, settings={"fm/enabled": "false", "hf/enabled": "true", "hf/profile": "dummy-hf", "station/lat": "60.17", "station/lon": "24.94", "beacon/interval_min": "30"})
    e.ctl.mercury._finder = fakemercury.program                                 # (the program that stands in for Mercury: it keeps what its KISS port is given)
    await e.start()
    await until(lambda: e.hf.state is Source.State.CONNECTED)
    assert e.hf.is_dummy and e.hf.rules.kind == "hf" and not hf_is_mercury(e.ctl.config)
    assert e.ctl.mercury.speaker and e.ctl.mercury.state in ("starting", "running") and e.ctl.mercury.keying.kind == "vox" and e.ctl.mercury.sound_card == ""
    started = next(line for line in caplog.text.splitlines() if "Mercury started" in line)
    if hasattr(os, "mkfifo"):
        assert (tmp_path / "mercury-capture.fifo").exists() and "-x fifo" in started, "Mercury runs on the fifo backend, paced by the daemon, where there are named pipes"
    else:
        assert not (tmp_path / "mercury-capture.fifo").exists() and "-x" not in started and "-i" not in started, "on Windows Mercury runs on its default recording and playback devices"
    assert "-P none" in started and "-m 1" in started
    await until(lambda: e.ctl.mercury.speaker_line.open, 5.0)
    for _ in range(40):
        e.now.advance(5)                                                         # type: ignore[attr-defined]
        await asyncio.sleep(0.02)
        if len(e.ctl.stationbook.stations()) >= 4 and e.ctl.mercury.speaker_line.played >= 1:
            break
    stations = [s for s in e.ctl.stationbook.stations() if s.call.startswith("Q")]
    assert len(stations) >= 4 and all(s.heard_hf > 0 and s.heard_fm == 0 for s in stations)
    assert e.ctl.mercury.speaker_line.played >= 1, "the beacon went to the speaker"
    await until(lambda: (tmp_path / fakemercury.BROADCAST_FILE).exists() and (tmp_path / fakemercury.BROADCAST_FILE).stat().st_size > 0, 5.0)
    assert e.ctl.config.serial_last_port == ""
    await e.stop()
    assert e.ctl.mercury.state == "stopped"


async def test_in_the_hf_world_a_dummy_station_hears_the_made_up_stations_and_nothing_of_it_reaches_the_air(tmp_path: Path, fast: None) -> None:
    w = World(tmp_path, frame_sec=0.2)
    a = await w.add("OH2A")
    b = await w.add("OH2B", lat=61.5, lon=23.8)
    d = Env(tmp_path / "OH2D", radio=False, settings={"station/call": "OH2D", "fm/enabled": "false", "hf/enabled": "true", "hf/profile": "dummy-hf", "station/lat": "60.17", "station/lon": "24.94", "beacon/interval_min": "30", "messages/alert": "false"})
    d.ctl.mercury._finder = lambda: None                                         # (no program at all: the speaker is a nice-to-have, and the dummy works without it)
    await w.start()
    await d.start()
    await until(lambda: d.hf.state is Source.State.CONNECTED)
    assert d.ctl.mercury.state == "waiting" and d.hf.usable, "no Mercury: nothing to hear, the Dummy HF radio runs all the same"
    assert d.ctl.hf_beacon.send_now("request")
    for _ in range(30):
        d.now.advance(5)                                                         # type: ignore[attr-defined]
        await asyncio.sleep(0.02)
    assert any(s.call.startswith("Q") and s.heard_hf > 0 for s in d.ctl.stationbook.stations())
    assert w.air.delivered == [] and not any(s.call == "OH2D" for s in a.ctl.stationbook.stations()) and not any(s.call == "OH2D" for s in b.ctl.stationbook.stations())
    await d.stop()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes: POSIX")
def test_the_speakers_audio_paces_silence_into_mercurys_capture_pipe_and_hands_what_mercury_plays_to_the_player(tmp_path: Path) -> None:
    out = tmp_path / "heard.raw"
    audio = SpeakerAudio(tmp_path, player=lambda: [sys.executable, "-c", "import sys; open(sys.argv[1], 'wb').write(sys.stdin.buffer.read())", str(out)])
    assert audio.prepare() and audio.capture.exists() and audio.playback.exists()
    started = time.monotonic()
    audio.start()
    try:
        cap = os.open(audio.capture, os.O_RDONLY | os.O_NONBLOCK)                 # (Mercury's side of the capture pipe)
        heard = bytearray()
        deadline = started + 10.0
        while len(heard) < 10 * BLOCK_BYTES and time.monotonic() < deadline:       # (it waits for the blocks and not for a time: a slow machine gets them later)
            with contextlib.suppress(BlockingIOError):
                heard += os.read(cap, 1 << 16)
            time.sleep(0.005)
        elapsed = time.monotonic() - started
        os.close(cap)
        blocks = len(heard) / BLOCK_BYTES
        assert blocks >= 10 and set(heard) == {0}, (blocks, "silence in blocks of 20 ms")
        assert blocks <= elapsed / 0.02 + 2, (blocks, elapsed, "at a sound card's pace and not faster")
        play = None
        for _ in range(50):                                                    # (the thread opens its reading end each block; the writing end can be opened once it has)
            try:
                play = os.open(audio.playback, os.O_WRONLY | os.O_NONBLOCK)
                break
            except OSError:
                time.sleep(0.02)
        assert play is not None
        os.write(play, b"\x01\x02\x03\x04" * 400)
        os.close(play)
        deadline = time.monotonic() + 2.0
        while audio.bytes_played < 1600 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert audio.bytes_played == 1600 and audio.player_said
    finally:
        audio.stop()
    assert out.read_bytes() == b"\x01\x02\x03\x04" * 400 and not audio.capture.exists() and not audio.playback.exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes: POSIX")
def test_the_speakers_audio_says_once_when_there_is_no_player_and_plays_nothing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="neoaprs.mercury")
    audio = SpeakerAudio(tmp_path, player=lambda: None)
    assert audio.prepare()
    audio.start()
    try:
        play = None
        for _ in range(50):
            try:
                play = os.open(audio.playback, os.O_WRONLY | os.O_NONBLOCK)
                break
            except OSError:
                time.sleep(0.02)
        assert play is not None
        os.write(play, SILENCE)
        os.write(play, SILENCE)
        os.close(play)
        deadline = time.monotonic() + 2.0
        while not audio.player_said and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        audio.stop()
    assert audio.bytes_played == 0 and caplog.text.count("no player for the Dummy HF radio's audio") == 1


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes: POSIX")
def test_the_speakers_audio_plays_again_after_a_stop_and_never_runs_two_clocks(tmp_path: Path) -> None:
    out = tmp_path / "heard.raw"
    audio = SpeakerAudio(tmp_path, player=lambda: [sys.executable, "-c", "import sys; open(sys.argv[1], 'wb').write(sys.stdin.buffer.read())", str(out)])

    def hand_over(data: bytes) -> None:
        play = None
        for _ in range(100):
            try:
                play = os.open(audio.playback, os.O_WRONLY | os.O_NONBLOCK)
                break
            except OSError:
                time.sleep(0.02)
        assert play is not None
        os.write(play, data)
        os.close(play)
        deadline = time.monotonic() + 3.0
        while audio.bytes_played < len(data) and time.monotonic() < deadline:
            time.sleep(0.02)

    def clocks() -> int:
        return len([t for t in threading.enumerate() if t.name == "mercury-speaker-audio"])

    assert audio.prepare()
    audio.start()
    audio.start()                                                           # (Mercury came back without a stop in between)
    try:
        assert clocks() == 1
        hand_over(b"\x01\x02\x03\x04" * 100)
        assert audio.bytes_played == 400 and audio.player_said
    finally:
        audio.stop()
    assert clocks() == 0 and not audio.player_said
    audio.bytes_played = 0
    assert audio.prepare()
    audio.start()
    try:
        hand_over(b"\x05\x06\x07\x08" * 100)
        assert audio.bytes_played == 400, "the radio's second run is heard as the first was"
    finally:
        audio.stop()
    assert out.read_bytes() == b"\x05\x06\x07\x08" * 100


async def test_our_position_is_withheld_from_the_internet_while_any_radio_that_is_on_is_a_dummy_and_not_for_one_that_is_off(tmp_path: Path, fast: None) -> None:
    dummy = Env(tmp_path / "dummy", radio=False, settings={"fm/enabled": "false", "hf/enabled": "true", "hf/profile": "dummy-hf"})
    dummy.ctl.mercury._finder = lambda: None
    await dummy.start()
    assert dummy.ctl.igate.made_up(), "the Dummy HF radio, with the FM radio off"
    await dummy.stop()
    air = fakemercury.Air(frame_sec=0.2)
    await air.start()
    real = Env(tmp_path / "real", radio=False, hf=air.station(), settings={"tnc/profile": "dummy"})       # (a leftover Dummy profile of the FM radio, which is off)
    await real.start()
    assert not real.ctl.igate.made_up(), "the real HF radio alone"
    await real.stop()
    await air.aclose()
