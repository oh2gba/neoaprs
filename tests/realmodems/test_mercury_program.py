"""Tests for the real Mercury itself on the Linux runner, started with the command line and the
configuration the daemon writes: every line NeoAPRS reads of it that can be provoked without a radio
is the line its parser expects; its ports cannot be reached from the runner's own network address
(packaging/mercury/loopback.patch); and the recording of its frames that the Windows job decodes
(test_windows.py) is made here."""

import asyncio
import os
import socket
import threading
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from neoaprs import mercury, mercuryhelper
from neoaprs.childprogram import environment
from neoaprs.mercury import Keying, audio_open_error, command, ini_text, unstamped
from neoaprs.mercuryhelper import free_ports, pair_ports
from tests.realmodems.probe import Modem, decode_file
from tests.realmodems.stations import programs, read_machine, refusal
from tests.support.hfchannel import Channel
from tests.support.realmercury import fifo

pytestmark = pytest.mark.asyncio(loop_scope="module")

PROGRAM = str(programs()[0])
PAYLOAD = b"OH2GW>APZNEO:>the lines of the real Mercury"
FRAME_SEC = 30.0  # a frame keyed, played, heard and handed over
ALIVE_SEC = 30.0  # the daemon writes keepalive_s = 10
RECORDINGS = os.environ.get("NEOAPRS_RECORDINGS", "")
RECORDED = (
    b"OH2AA>APZNEO:!6010.20N/02456.40E-recorded on Linux",
    b"OH2AA>APZNEO::OH2BB    :recorded on Linux{1",
    b"OH2BB>APZNEO::OH2AA    :ack1",
)


@pytest.fixture(scope="module", autouse=True)
def allowed() -> None:
    why = refusal(os.environ, read_machine())
    if why:
        pytest.exit(why, returncode=3)
    assert Path(PROGRAM).is_file(), "the Mercury is not built (scripts/build-mercury --install)"


def start(folder: Path, name: str, card: str, first: int) -> tuple[Modem, tuple[int, int]]:
    """A Mercury on the sound card `card`, keyed by VOX, as the daemon starts one."""
    folder.mkdir(parents=True, exist_ok=True)
    ports = free_ports(first)
    ini = folder / f"{name}.ini"
    ini.write_text(ini_text(Keying("vox")), encoding="utf-8")
    argv = command([PROGRAM], str(ini), card, Keying("vox"), *ports)
    return Modem(name, argv, folder, environment([PROGRAM])), ports


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pair(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[tuple[Modem, Modem]]:
    """G on one end of the HF cable, B on the other."""
    folder = tmp_path_factory.mktemp("program")
    g, g_ports = start(folder, "g", "hf_g", 18300)
    b, b_ports = start(folder, "b", "hf_b", g_ports[0] + 10)
    try:
        await g.open(*g_ports)
        await b.open(*b_ports)
        yield g, b
    finally:
        await g.close()
        await b.close()


async def test_its_start_names_its_sound_devices_and_its_keying_in_the_lines_the_daemon_logs(
    pair: tuple[Modem, Modem],
) -> None:
    g, _ = pair
    await g.until("start lines", lambda: f"Mercury {mercury.VERSION} (git" in g.said(), 30.0)
    lines = g.said().splitlines()
    device = [line for line in lines if mercuryhelper._DEVICE_LINE.search(line)]
    assert any("[audio-play] I/O " in line for line in device), "the playing device"
    assert any("[audio-cap] I/O " in line for line in device), "the recording device"
    assert any("[radio-io] " in line for line in device), "the keying"
    version = next(line for line in lines if f"Mercury {mercury.VERSION} (git" in line)
    assert unstamped(version).startswith("[INF] [main] "), "the stamp of a log line is the one the daemon strips"


async def test_it_says_it_is_alive_on_its_control_port(pair: tuple[Modem, Modem]) -> None:
    g, _ = pair
    await g.until("IAMALIVE", lambda: bool(g.seen("alive")), ALIVE_SEC)


async def test_a_frame_keys_the_sender_and_the_receiver_says_busy_and_snr_and_hands_the_frame_over(
    pair: tuple[Modem, Modem],
) -> None:
    g, b = pair
    g_after, b_after = len(g.events), len(b.events)
    g.send(PAYLOAD)
    await g.until("PTT ON", lambda: bool(g.seen("ptt", True, g_after)), FRAME_SEC)
    await g.until("PTT OFF", lambda: bool(g.seen("ptt", False, g_after)), FRAME_SEC)
    await b.until("the frame", lambda: PAYLOAD in b.frames, FRAME_SEC)
    await b.until("SN", lambda: bool(b.seen("snr", after=b_after)), FRAME_SEC)
    await b.until(
        "BUSY ON and BUSY OFF",
        lambda: bool(b.seen("busy", True, b_after) and b.seen("busy", False, b_after)),
        FRAME_SEC,
    )
    assert all(e.value is not None for e in b.seen("snr", after=b_after))


async def test_the_tune_tone_keys_and_unkeys_on_the_commands_the_daemon_writes(pair: tuple[Modem, Modem]) -> None:
    g, _ = pair
    after = len(g.events)
    g.command(mercury.tune_command(mercury.tune_level(0)))
    await g.until("PTT ON for TUNE", lambda: bool(g.seen("ptt", True, after)), FRAME_SEC)
    g.command(mercury.TUNE_OFF)
    await g.until("PTT OFF after TUNE OFF", lambda: bool(g.seen("ptt", False, after)), FRAME_SEC)
    assert not [e.text for e in g.events[after:] if e.text.startswith("WRONG")], "both commands taken"


async def test_a_sound_card_that_is_not_there_is_said_in_the_line_the_daemon_reads(tmp_path: Path) -> None:
    modem, ports = start(tmp_path, "missing", "neoaprs_no_such_device", 18500)
    try:
        await modem.until(
            "the line of a sound card that cannot be opened",
            lambda: any(audio_open_error(line) for line in modem.said().splitlines()),
            60.0,
        )
    finally:
        await modem.close()


def own_address() -> str:
    """The runner's address on its network (a UDP socket's own address; nothing is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.0.2.1", 9))
        return str(probe.getsockname()[0])


async def test_its_ports_answer_on_the_loopback_and_are_refused_from_the_runners_own_address(tmp_path: Path) -> None:
    address = own_address()
    assert not address.startswith("127."), f"the runner has no address of its own to try ({address})"
    ports = free_ports(18600)
    folder = tmp_path / "loopback"
    folder.mkdir()
    ini = folder / "m.ini"
    ini.write_text(ini_text(Keying("vox"), ui_port=ports[0] + mercury.UI_OFFSET), encoding="utf-8")
    argv = command(
        [PROGRAM],
        str(ini),
        "",
        Keying("vox"),
        *ports,
        audio=mercury.speaker_audio(fifo(folder, "capture"), fifo(folder, "playback")),
    )
    modem = Modem("loopback", argv, folder, environment([PROGRAM]))
    try:
        await modem.open(*ports)
        for port in pair_ports(ports[0]):
            with socket.create_connection(("127.0.0.1", port), 10):
                pass
            with pytest.raises(ConnectionRefusedError), socket.create_connection((address, port), 10):
                pass
    finally:
        await modem.close()


class Recorder:
    """What the far end of the channel hears, read from its pipe as it is written, at the channel's pace."""

    def __init__(self, path: str) -> None:
        self.path, self.data = path, bytearray()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        with open(self.path, "rb", buffering=0) as pipe:
            while not self._stop.is_set() and (chunk := pipe.read(1 << 16)):
                self.data.extend(chunk)

    def stop(self) -> bytes:
        self._stop.set()
        self._thread.join(10)
        return bytes(self.data)


@pytest.mark.skipif(not RECORDINGS, reason="NEOAPRS_RECORDINGS names the folder of the Windows job's recordings")
async def test_it_records_its_frames_for_the_windows_job_and_another_mercury_here_hears_them(tmp_path: Path) -> None:
    channel = Channel(snr_db=60.0)
    pipes = {name: (fifo(tmp_path, f"{name}-rx"), fifo(tmp_path, f"{name}-tx")) for name in ("tx", "rec")}
    for name, (rx, tx) in pipes.items():
        channel.add(name, rx, tx)
    recorder = Recorder(pipes["rec"][0])
    holder = os.open(pipes["rec"][1], os.O_RDWR)  # the far end transmits nothing
    channel.start()
    ports = free_ports(18700)
    ini = tmp_path / "tx.ini"
    ini.write_text(ini_text(Keying("vox")), encoding="utf-8")
    argv = command([PROGRAM], str(ini), "", Keying("vox"), *ports, audio=mercury.speaker_audio(*pipes["tx"]))
    modem = Modem("tx", argv, tmp_path, environment([PROGRAM]))
    try:
        await modem.open(*ports)
        await asyncio.sleep(2.0)
        for payload in RECORDED:
            after = len(modem.events)
            modem.send(payload)
            await modem.until("PTT OFF", lambda after=after: bool(modem.seen("ptt", False, after)), FRAME_SEC)
            await asyncio.sleep(1.0)
        await asyncio.sleep(2.0)
    finally:
        await modem.close()
        channel.stop()
        os.close(holder)
        audio = recorder.stop()
    folder = Path(RECORDINGS)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "mercury-datac3.s32le").write_bytes(audio)
    (folder / "mercury-datac3.txt").write_bytes(b"\n".join(RECORDED) + b"\n")
    assert len(audio) > 8000 * 4 * 10, f"{len(audio)} bytes recorded"
    heard = await decode_file(
        PROGRAM,
        folder / "mercury-datac3.s32le",
        tmp_path / "decode",
        environment([PROGRAM]),
        free_ports(18800),
        set(RECORDED),
    )
    assert set(heard.frames) == set(RECORDED), f"heard {sorted(set(heard.frames))}"
