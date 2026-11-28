"""The sound server's devices on a real PipeWire of the test's own (tests/support/soundrig.py): the list, the
ALSA names of neoaprs/soundserver.conf opened by aplay and arecord, the check of where a program's streams
sit, and the channels of a 4-channel source. Skipped unless NEOAPRS_SOUND_RIG=1 (the CI job soundrig).
"""

import array
import math
import subprocess
import time
import wave
from pathlib import Path

import pytest

from neoaprs import soundserver
from neoaprs.childprogram import environment
from tests.support.soundrig import START_SEC, Rig, sound_rig as sound_rig

pytestmark = pytest.mark.slow("each test starts a PipeWire of its own, and a channel is read for a second")
QUAD = "front-left,front-right,rear-left,rear-right"
TONE = 12000  # the amplitude of the tone; its RMS is TONE / sqrt(2)


def devices(rig: Rig) -> None:
    """A user's own devices: a sink (a remap of a null sink, as one makes for a radio) and a 4-channel source."""
    rig.pactl("load-module", "module-null-sink", "sink_name=speakers", "sink_properties=device.description=Speakers")
    rig.pactl("set-default-sink", "speakers")
    rig.pactl(
        "load-module", "module-null-sink", "sink_name=Radio_null", "sink_properties=device.description=Radio_null"
    )
    rig.pactl(
        "load-module",
        "module-remap-sink",
        "sink_name=Radio_remap",
        "master=Radio_null",
        "sink_properties=device.description=Radio",
    )
    rig.pactl("load-module", "module-null-sink", "sink_name=quad", "channels=4", f"channel_map={QUAD}")
    rig.pactl(
        "load-module",
        "module-remap-source",
        "source_name=quad_in",
        "master=quad.monitor",
        "channels=4",
        f"channel_map={QUAD}",
        "source_properties=device.description=Rubix44",
    )


def alsa_env(rig: Rig) -> dict[str, str]:
    """The environment of a program on our ALSA names: the one a modem on such a device gets."""
    assert soundserver.system_alsa() is not None, "the rig has the server's ALSA plug-in"
    return environment(["aplay"], system_sound=True)


def streams_of(pid: int) -> list[list[int]]:
    clients = soundserver.clients_of(soundserver.pactl(["list", "clients"]), pid)
    return [
        soundserver.stream_targets(soundserver.pactl(["list", part]), pid, kind, clients) or []  # type: ignore[arg-type]
        for part, kind in (("sink-inputs", "sink"), ("source-outputs", "source"))
    ]


def until_streams(pid: int, count: int) -> list[list[int]]:
    deadline = time.monotonic() + START_SEC
    while sum(map(len, found := streams_of(pid))) < count:
        assert time.monotonic() < deadline, f"process {pid} has no {count} streams: {found}"
        time.sleep(0.05)
    return found


def test_the_list_holds_the_devices_a_user_made_by_their_descriptions_and_no_monitor(sound_rig: Rig) -> None:
    devices(sound_rig)
    rows = soundserver.server_cards({})
    assert {(r.name, r.playback, r.capture, r.channel) for r in rows} >= {
        ("Radio", True, False, 0),
        ("Rubix44", False, True, 0),
        ("Rubix44", False, True, 4),
    }
    assert not [r for r in rows if r.id.endswith(".monitor")]


def test_a_player_on_our_alsa_name_plays_on_the_named_sink_and_the_check_says_so(sound_rig: Rig) -> None:
    devices(sound_rig)
    nodes = soundserver.list_nodes() or []
    setting = "pulse:DEVICE=quad_in|pulse:DEVICE=Radio_remap"
    via = soundserver.plugin(soundserver.plugin_dir())
    _, playback = soundserver.alsa_setting(setting, nodes, via).split("|")
    env = alsa_env(sound_rig)
    play = subprocess.Popen(
        ["aplay", "-q", "-D", playback, "-f", "S16_LE", "-r", "48000", "-c", "2", "/dev/zero"], env=env
    )
    try:
        assert until_streams(play.pid, 1)[0] == [sound_rig.index("sinks", "Radio_remap")]
        assert soundserver.misplaced(setting, play.pid) == ""
        sound_rig.pactl("unload-module", "module-remap-sink")
        deadline = time.monotonic() + START_SEC
        while not soundserver.misplaced(setting, play.pid):
            assert time.monotonic() < deadline, "the device that went is not found gone"
            time.sleep(0.05)
    finally:
        play.terminate()
        play.wait()


def test_a_name_the_server_does_not_know_plays_on_the_default_and_the_check_finds_it(sound_rig: Rig) -> None:
    """The hazard the check is for: no error, the loudspeakers."""
    devices(sound_rig)
    nodes = soundserver.list_nodes() or []
    radio = next(n for n in nodes if n.name == "Radio_remap")
    ghost = soundserver.Node("sink", 999999, "Radio_remap", "Radio", radio.positions)
    via = soundserver.plugin(soundserver.plugin_dir())
    name = soundserver.alsa_name("pulse:DEVICE=Radio_remap", "sink", [ghost], via)
    play = subprocess.Popen(
        ["aplay", "-q", "-D", name, "-f", "S16_LE", "-r", "48000", "-c", "2", "/dev/zero"], env=alsa_env(sound_rig)
    )
    try:
        on = until_streams(play.pid, 1)[0]
        assert on != [radio.index]
        assert "not on Radio_remap" in soundserver.misplaced("plughw:CARD=X,DEV=0|pulse:DEVICE=Radio_remap", play.pid)
    finally:
        play.terminate()
        play.wait()


def _tone(channel: int, path: Path, seconds: float = 9.0) -> None:
    samples = array.array("h")
    for i in range(int(48000 * seconds)):
        value = int(TONE * math.sin(2 * math.pi * 1000 * i / 48000))
        samples.extend(value if c == channel else 0 for c in range(4))
    path.write_bytes(samples.tobytes())


def _rms(path: Path) -> list[int]:
    with wave.open(str(path)) as w:
        n, data = w.getnchannels(), array.array("h", w.readframes(w.getnframes()))
    frames = len(data) // n
    start = frames // 3  # (the start may be silence while the link forms)
    return [
        round(math.sqrt(sum(data[i * n + c] ** 2 for i in range(start, frames)) / (frames - start))) for c in range(n)
    ]


def _read(env: dict[str, str], device: str, channels: int, out: Path) -> list[int]:
    done = subprocess.run(
        ["arecord", "-q", "-D", device, "-f", "S16_LE", "-r", "48000", "-c", str(channels), "-d", "1", str(out)],
        env=env,
        capture_output=True,
        timeout=START_SEC,
    )
    assert done.returncode == 0, done.stderr
    return _rms(out)


@pytest.mark.parametrize("played", range(4), ids=QUAD.split(","))
def test_a_source_of_four_channels_is_mixed_for_a_reader_of_fewer_and_one_channel_row_reads_it_alone(
    sound_rig: Rig, tmp_path: Path, played: int
) -> None:
    devices(sound_rig)
    nodes = soundserver.list_nodes() or []
    via = soundserver.plugin(soundserver.plugin_dir())
    env = alsa_env(sound_rig)
    raw = tmp_path / "tone.raw"
    _tone(played, raw)
    feed = sound_rig.start(
        [
            "pacat",
            "--playback",
            "-d",
            "quad",
            "--format=s16le",
            "--rate=48000",
            "--channels=4",
            f"--channel-map={QUAD}",
            str(raw),
        ]
    )
    whole = soundserver.alsa_name("pulse:DEVICE=quad_in", "source", nodes, via)
    full = TONE / math.sqrt(2)
    try:
        mono = _read(env, whole, 1, tmp_path / "mono.wav")[0]
        assert abs(mono - full / 4) < full / 20, f"a 1-channel reader gets the four mixed: {mono}"
        for i, position in enumerate(QUAD.split(",")):
            name = soundserver.alsa_name(soundserver.server_id("quad_in", position), "source", nodes, via)
            level = _read(env, name, 1, tmp_path / f"{position}.wav")[0]
            assert (level > full * 0.9) if i == played else (level < full * 0.02), f"{position}: {level}"
    finally:
        feed.terminate()
        feed.wait()
