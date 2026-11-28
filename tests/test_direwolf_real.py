"""Tests for the real Direwolf that scripts/build-direwolf --install puts in the venv, run by the
test itself without a sound card: UDP input, standard-input decoding, receive level, and long
configuration paths; then the daemon's driver on ALSA's `null` device. Skipped without the build and
off Linux."""

import asyncio
import logging
import math
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

from neoaprs import direwolfmodem, kiss
from tests.support import direwolfaudio
from neoaprs.bundled import tools_dir
from neoaprs.claims import Claims
from neoaprs.clock import utcnow
from neoaprs.config import DEFAULTS
from neoaprs.direwolfdriver import DirewolfDriver
from neoaprs.radiodriver import RunOverrides
from neoaprs.radioregistry import make_driver
from neoaprs.radiospec import RadioSpec
from neoaprs.source import Source
from neoaprs.childprogram import environment
from neoaprs.direwolf import LEVEL_NOW_MS, level_now_of

FOLDER = tools_dir() / "direwolf"
PROGRAM = FOLDER / "direwolf"
pytestmark = [
    pytest.mark.skipif(
        not sys.platform.startswith("linux") or not PROGRAM.is_file(),
        reason="a Direwolf in the venv (scripts/build-direwolf --install), and the kernel's table of sockets, are needed",
    ),
    pytest.mark.real_direwolf,
]
its_tools = pytest.mark.skipif(
    not (FOLDER / "dev" / "gen_packets").is_file(),
    reason="gen_packets and atest, which scripts/build-direwolf --install builds beside it, are needed",
)
LOOPBACK = "0100007F"


def _bound(port: int, tables: tuple[str, ...]) -> set[str]:
    found: set[str] = set()
    for name in tables:
        for line in Path(name).read_text(encoding="ascii").splitlines()[1:]:
            fields = line.split()
            address, _, at = fields[1].rpartition(":")
            if int(at, 16) == port and ("/tcp" not in name or fields[3] == "0A"):
                found.add(address)
    return found


def _conf(folder: Path, adevice: str, port: int) -> Path:
    conf = folder / "direwolf.conf"
    conf.write_text(
        f"ADEVICE {adevice}\nACHANNELS 1\nCHANNEL 0\nMODEM 1200\nKISSPORT 0\nKISSPORT {port}\nAGWPORT 0\nDNSSD 0\n",
        encoding="utf-8",
    )
    return conf


def _start(folder: Path, conf: Path, *extra: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [str(PROGRAM), "-c", str(conf), "-t", "0", "-q", "d", "-d", "o", *extra],
        cwd=folder,
        env=environment([str(PROGRAM)]),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


@its_tools
def test_closing_its_input_ends_it_cleanly_and_it_listens_on_this_computer_only(tmp_path: Path) -> None:
    udp, port = 17311, 17411
    child = _start(tmp_path, _conf(tmp_path, f"udp:{udp} null", port), "-Q")
    try:
        deadline = time.monotonic() + 30
        while (
            not _bound(port, ("/proc/net/tcp", "/proc/net/tcp6"))
            and time.monotonic() < deadline
            and child.poll() is None
        ):
            time.sleep(0.2)
        assert _bound(port, ("/proc/net/tcp", "/proc/net/tcp6")) == {LOOPBACK} and _bound(
            udp, ("/proc/net/udp", "/proc/net/udp6")
        ) == {LOOPBACK}
        assert child.stdin is not None
        child.stdin.close()
        # (communicate would flush the closed pipe: "flush of closed file")
        child.stdin = None
        closed = time.monotonic()
        output = child.communicate(timeout=10)[0].decode("utf-8", "replace")
        assert (
            child.returncode == 0 and "PTT 0 = 0" in output and "QRT" in output and time.monotonic() - closed < 3.0
        ), output
    finally:
        if child.poll() is None:
            child.kill()


@its_tools
async def test_it_decodes_the_frames_of_its_own_gen_packets_and_hands_each_to_its_kiss_client(tmp_path: Path) -> None:
    wav = tmp_path / "sample.wav"
    subprocess.run(
        [str(FOLDER / "dev" / "gen_packets"), "-o", str(wav)], cwd=tmp_path, check=True, capture_output=True, timeout=60
    )
    counted = subprocess.run(
        [str(FOLDER / "dev" / "atest"), str(wav)], cwd=tmp_path, check=False, capture_output=True, text=True, timeout=60
    ).stdout
    expected = int(next(line.split()[0] for line in counted.splitlines() if "packets decoded" in line))
    assert expected > 0
    port = 17421
    child = _start(tmp_path, _conf(tmp_path, "stdin null", port))
    try:
        assert child.stdout is not None and child.stdin is not None
        while b"Ready to accept KISS TCP client" not in await asyncio.to_thread(child.stdout.readline):
            assert child.poll() is None, "it ended before it listened"
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        # (the samples, without the WAV header)
        await asyncio.to_thread(child.stdin.write, wav.read_bytes()[44:])
        await asyncio.to_thread(child.stdin.flush)
        frames: list[kiss.KissFrame] = []
        decoder = kiss.KissDecoder()
        deadline = asyncio.get_running_loop().time() + 60
        while len(frames) < expected and asyncio.get_running_loop().time() < deadline:
            data = await asyncio.wait_for(reader.read(4096), 60)
            frames += decoder.feed(data)
        writer.close()
        child.stdin.close()
        assert len(frames) == expected and child.wait(10) == 0
    finally:
        if child.poll() is None:
            child.kill()


def _sine(seconds: float, amplitude: int, rate: int = 44100) -> bytes:
    """A 1000 Hz tone of this amplitude as Direwolf reads its standard input: 16-bit little-endian
    samples, one channel."""
    return b"".join(
        struct.pack("<h", round(amplitude * math.sin(2 * math.pi * 1000 * n / rate)))
        for n in range(round(seconds * rate))
    )


def _levels_heard(folder: Path, gain: int, audio: bytes) -> tuple[list[int], str]:
    """Direwolf on audio read from its standard input (`ADEVICE stdin null`) at the transmit level
    `gain` with `-R`: the levels it said, and all it said. It ends at the end of its input."""
    done = subprocess.run(
        [
            str(PROGRAM),
            "-c",
            str(_conf(folder, "stdin null", 17431)),
            "-t",
            "0",
            "-q",
            "d",
            "-G",
            str(gain),
            "-R",
            str(LEVEL_NOW_MS),
        ],
        cwd=folder,
        env=environment([str(PROGRAM)]),
        input=audio,
        capture_output=True,
        timeout=60,
        check=False,
    )
    said = (done.stdout + done.stderr).decode("utf-8", "replace")
    return [level for line in said.splitlines() if (level := level_now_of(line)) is not None], said


def test_its_receive_level_comes_every_tenth_of_a_second_of_audio_and_no_transmit_level_scales_it(
    tmp_path: Path,
) -> None:
    """The receive level does not depend on the transmit level (`-G`): the same audio at two
    transmit levels gives the same level. The transmit level reaches the tone generators only
    (gen_tone_init, dtmf_init and morse_init in direwolf.c); the receive level is
    demod_get_audio_level's. It is counted in the samples read, so audio written faster than real
    time still gives one level every LEVEL_NOW_MS of it."""
    audio = _sine(3.0, 8000)
    low, said = _levels_heard(tmp_path, 30, audio)
    full, _ = _levels_heard(tmp_path, 100, audio)
    assert len(low) == len(full) and 3000 // LEVEL_NOW_MS - 2 <= len(low) <= 3000 // LEVEL_NOW_MS, said
    # (half of peak to peak, on its scale of 100 for a quarter of full scale: 8000/16384·100/2 is
    # 49)
    assert low == full and 45 <= low[-1] <= 53, (low, full)
    assert _levels_heard(tmp_path, 100, _sine(1.0, 16000))[0][-1] > 2 * low[-1] - 5


def test_it_reads_a_configuration_whose_path_is_longer_than_99_characters(tmp_path: Path) -> None:
    folder = tmp_path / ("a-data-folder-with-a-long-name-" * 4)
    folder.mkdir()
    assert len(str(folder / "direwolf.conf")) > 140
    levels, said = _levels_heard(folder, 100, _sine(0.5, 8000))
    # (it ended at once there, exit 1: config.c)
    assert (
        "Could not open configuration file" not in said
        and f"Reading config file {folder / 'direwolf.conf'}" in said
        and levels
    ), said


async def test_the_daemons_line_to_it_is_opened_once_though_it_says_ready_again_at_every_client(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """The daemon's Sound card radio with the real program: started by the modem, its line pointed
    at the KISS port when Direwolf says it listens (wiring.py ties `ports_changed` to the registry's
    repoint). This Direwolf offers the next place as soon as our line has attached; taken as a
    start, that opened the line endlessly. Also in a data folder with a long path: Direwolf cut the
    path of its configuration at 99 characters (confpath.patch)."""
    from tests.support.modemports import base_of_this_test

    monkeypatch.setattr(direwolfmodem, "FIRST_PORT", base_of_this_test())
    # the switch would keep the modem from starting Direwolf; its card is ALSA's null, its keying VOX
    monkeypatch.delenv("NEOAPRS_NO_DEVICES", raising=False)
    radio = RadioSpec(
        3,
        "fm",
        "direwolf",
        "",
        True,
        3,
        settings={
            "sound_card": "null",
            "keying": "vox",
            "tx_gain_db": "0",
            "beacon": "true",
            "path": "",
            "digipeat": "false",
        },
    )
    await _opened_once(tmp_path / ("a-data-folder-with-a-long-name-" * 4), radio, caplog)


async def _opened_once(folder: Path, radio: RadioSpec, caplog: pytest.LogCaptureFixture) -> None:
    from tests.support import fakemercury
    from tests.support.env import until_started

    assert len(str(folder / "radios" / "3" / "direwolf.conf")) > 140
    driver = make_driver(radio, Claims(), utcnow, folder)
    assert isinstance(driver, DirewolfDriver)
    # (no sound card of the machine is listed and no serial port looked at: the card is ALSA's
    # `null`, the keying VOX)
    driver.modem._lister, driver.modem.ports = fakemercury.program, lambda: []
    driver.configure(radio, DEFAULTS, RunOverrides(check_sec=0.0))
    told: list[int] = []
    tasks: set[asyncio.Task[None]] = set()

    async def repoint() -> None:
        await driver.line.stop()
        driver.configure(radio, DEFAULTS, RunOverrides(check_sec=0.0))
        await driver.line.start()

    def follow() -> None:
        told.append(driver.modem.kiss_port)
        task = asyncio.ensure_future(repoint())
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    driver.modem.ports_changed.connect(follow)
    with caplog.at_level(logging.INFO, logger="neoaprs.direwolf.program"):
        await driver.start()
        try:
            await until_started(lambda: driver.line.state is Source.State.CONNECTED and not tasks)
            await asyncio.sleep(2.0)
            assert (
                told == [driver.modem.kiss_port]
                and driver.line.state is Source.State.CONNECTED
                and driver.modem.state == "running"
            )
            said = [
                record.getMessage() for record in caplog.records if "KISS TCP client application" in record.getMessage()
            ]
            assert sum("Attached to KISS TCP client application" in line for line in said) == 1, said
            assert sum(line.startswith("Ready to accept KISS TCP client application") for line in said) == 2, (
                f"this Direwolf says Ready again once a client has attached: {said}"
            )
            # (its statistics line, every STATS_SEC: the receive level as it is now, which the
            # radio's row has)
            await until_started(lambda: driver.modem.rx_level is not None)
            # (and every LEVEL_NOW_MS, for the pages that show it)
            assert driver.modem.level_now.value is not None
            assert not [record for record in caplog.records if "RXLEVEL" in record.getMessage()]
        finally:
            await driver.stop()
        assert driver.modem.level_now.value is None


@pytest.mark.parametrize("name", sorted(direwolfaudio.FILES))
def test_it_decodes_the_recorded_audio_of_the_frames_we_send_each_frame_once_and_unchanged(name: str) -> None:
    atest = FOLDER / "dev" / "atest"
    if not atest.is_file():
        pytest.skip("atest, which scripts/build-direwolf --install builds beside it, is needed")
    assert direwolfaudio.decoded(str(atest), direwolfaudio.FIXTURES / name) == list(direwolfaudio.FRAMES)


def test_it_decodes_as_many_frames_of_the_recording_under_rising_noise_as_the_direwolf_that_made_it() -> None:
    atest = FOLDER / "dev" / "atest"
    if not atest.is_file():
        pytest.skip("atest, which scripts/build-direwolf --install builds beside it, is needed")
    got = direwolfaudio.decoded(str(atest), direwolfaudio.FIXTURES / direwolfaudio.NOISE_FILE)
    assert len(got) == direwolfaudio.NOISE_DECODED, f"{len(got)} of {direwolfaudio.NOISE_FRAMES} decoded"
