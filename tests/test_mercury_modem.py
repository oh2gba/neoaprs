"""The Mercury HF modem as a part of the daemon (neoaprs/mercurymodem.py, mercuryhelper.py, mercurycontrol.py) on the program that stands in for Mercury (tests/support/fakemercury.py, run as the binary) and on a station of the
fake air: the program found, given free ports and the configuration, started, read, started again when it dies, stopped with nothing left behind; a program that is not installed, that cannot be started, whose ports are taken;
the control port's `PTT ON/OFF`, `BUSY ON/OFF` and `SN` as the hold the Tnc asks about and the words of the status line; and the Tnc on a Mercury station: the frame cap as the last guard, the hold while a frame is on the
air, the modem's problem as the radio's."""
import asyncio
import itertools
import logging
import os
import shlex
import signal
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs import ax25, kiss
from dataclasses import replace

from neoaprs.config import DEFAULTS, Config
from neoaprs.mercury import BROADCAST_PORT, CONTROL_OFFSET, Keying, SerialPort, SoundCard
from neoaprs import mercuryhelper, mercurymodem
from neoaprs.mercuryhelper import PORT_TRIES, end_stale, environment, find, free_ports, list_sound_cards
from neoaprs.mercurymodem import CHANNEL_BUSY, INI_FILE, NOT_INSTALLED, PID_FILE, SOUND_CARD_FAILED, TRANSMITTING, Mercury, proposal
from neoaprs.serialprobe import PortInfo
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import MERCURY
from tests.support import fakemercury
from tests.support.env import until
from tests.support.fakemercury import Air
from tests.test_tnc import Rigs, stops_rigs, ui_frame

HF: Config = replace(DEFAULTS, hf_enabled=True, fm_enabled=False, mercury_keying="rts:/dev/ttyUSB0", mercury_sound_card="plughw:1,0", station_call="OH2GBA")
QUICK = Backoff([0.1, 0.1])


@pytest.fixture
def rig() -> Rigs:
    return Rigs()


WORKER_SPAN = 1000                      # the ports of a pytest-xdist worker: its own thousand from 20000 up, all below the ephemeral ranges (Linux from 32768, Windows from 49152), so that nothing the system hands out lies in them
WORKERS = 12                            # (scripts/check runs at most twelve; more wrap round to a worker that is not likely to run beside them)
_tests_run = itertools.count()


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """The modem asks for free ports from Mercury's defaults up; here each test asks from a base of its own, so that two tests running side by side (pytest-xdist) do not both find 8100 free between the probe and
    the bind (one of them then started a program that could not listen). A worker has a range of its own and its tests, which run one after the other, take its two halves in turn: no two workers share a port, and a
    test does not start where the one before it may still hold a port."""
    worker = int("".join(c for c in os.environ.get("PYTEST_XDIST_WORKER", "") if c.isdigit()) or 0) % WORKERS
    base = 20000 + WORKER_SPAN * worker + WORKER_SPAN // 2 * (next(_tests_run) % 2)
    monkeypatch.setattr(mercurymodem, "free_ports", lambda first=BROADCAST_PORT, tries=PORT_TRIES: free_ports(base, tries))


def modem(tmp_path: Path, program: bool = True) -> Mercury:
    m = Mercury(tmp_path, finder=(fakemercury.program if program else lambda: None), backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []                                                  # (never the operator's serial ports)
    return m


async def stopped(m: Mercury) -> None:
    await m.stop()
    assert m.state == "stopped" and m.pid is None or not _alive(m.pid)


def _alive(pid: int | None) -> bool:
    """Whether the process is still running. On Windows os.kill(pid, 0) is TerminateProcess, and a handle to a process that has ended still opens, so the exit code is asked instead."""
    if pid is None:
        return False
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32                          # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)             # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259                                  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


async def connects(port: int) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 1.0)
    except (OSError, TimeoutError):
        return False
    writer.close()
    return True


# ---- finding the program and its ports

def test_the_program_is_the_shipped_one_in_the_tools_folder_and_nothing_else(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Not on the PATH, not in the data folder: the operator's system is left alone, and the Mercury that runs is the one the release carries (bundled.py says where each install kind puts it)."""
    name = "mercury.exe" if sys.platform == "win32" else "mercury"
    assert find(tmp_path / "nothing") is None
    on_path = tmp_path / "path" / name
    on_path.parent.mkdir()
    on_path.write_text("#!/bin/sh\n")
    on_path.chmod(0o755)
    monkeypatch.setenv("PATH", str(on_path.parent))
    assert find(tmp_path / "nothing") is None, "a Mercury on the PATH is the operator's, not ours"
    shipped = tmp_path / "tools" / "mercury" / name
    shipped.parent.mkdir(parents=True)
    shipped.write_text("#!/bin/sh\n")
    if sys.platform != "win32":                                        # (Windows has no executable bit: a .exe can always be run)
        assert find(tmp_path / "tools") is None, "a file that cannot be run is no program"
    shipped.chmod(0o755)
    assert find(tmp_path / "tools") == [str(shipped)]
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    assert find() == [str(shipped)], "a venv, the AppImage and the .deb: tools/ of the Python's prefix"


def test_the_bundled_alsa_configuration_is_given_to_the_program_through_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The Linux bundle carries its own ALSA library and configuration (a machine without ALSA installed has no /usr/share/alsa/alsa.conf); ALSA_CONFIG_PATH is the one way to tell the library where it is."""
    monkeypatch.delenv("ALSA_CONFIG_PATH", raising=False)
    program = tmp_path / "mercury" / "mercury"
    program.parent.mkdir()
    program.write_text("")
    assert "ALSA_CONFIG_PATH" not in environment([str(program)]), "no configuration beside the program: the system's"
    conf = tmp_path / "mercury" / "share" / "alsa" / "alsa.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("")
    assert environment([str(program)])["ALSA_CONFIG_PATH"] == str(conf)
    assert "ALSA_CONFIG_PATH" not in environment([sys.executable, "-m", "tests.support.fakemercury"]), "the fake that stands in for the program is not a bundle"
    assert "PATH" in environment([str(program)]), "the reduced environment of a child, as for every program the daemon starts"


def test_the_ports_are_mercurys_defaults_when_free_else_the_next_pair_with_the_control_port_200_above() -> None:
    first = 18100
    assert free_ports(first, 3) == (first, first + CONTROL_OFFSET)
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", first + CONTROL_OFFSET))                           # (a program holds the control port: the pair is skipped)
        assert free_ports(first, 3) == (first + 1, first + 1 + CONTROL_OFFSET)
        with socket.socket() as second, socket.socket() as third:
            second.bind(("127.0.0.1", first + 1))
            third.bind(("127.0.0.1", first + 2))
            with pytest.raises(OSError, match="no free pair"):
                free_ports(first, 3)
    assert BROADCAST_PORT == 8100 and CONTROL_OFFSET == 200


def test_the_sound_cards_come_from_the_program_and_a_program_that_cannot_run_lists_none(caplog: pytest.LogCaptureFixture) -> None:
    assert list_sound_cards(fakemercury.program()) == [SoundCard("plughw:1,0", "USB Audio CODEC", True, True, True), SoundCard("plughw:0,0", "HDA Intel PCH", True, False, False)]
    assert list_sound_cards(["/nonexistent/mercury"]) == [] and "could not be run" in caplog.text


# ---- the program's life

async def test_the_modem_chooses_the_sound_card_and_the_keying_when_the_settings_are_empty_and_takes_them_when_set(tmp_path: Path) -> None:
    m = modem(tmp_path)
    m.ports = lambda: [SerialPort("/dev/ttyUSB0", 0x10C4, 0xEA60)]
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    try:
        await until(lambda: m.state == "running", 5.0)
        assert (m.sound_card, m.keying) == ("", Keying("rts", "/dev/ttyUSB0")), "the fake program lists a USB Audio CODEC that is the system's default (a computer whose only card is the radio's): Mercury's default device is right, and the one CP2102 port keys it"
        assert "line = rts" in (tmp_path / INI_FILE).read_text()
    finally:
        await m.stop()
    m.ports = lambda: []
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    try:
        await until(lambda: m.state == "running", 5.0)
        assert (m.sound_card, m.keying) == ("", Keying("vox")), "no serial port: VOX"
    finally:
        await m.stop()
    await m.start(HF)
    try:
        await until(lambda: m.state == "running", 5.0)
        assert (m.sound_card, m.keying) == ("plughw:1,0", Keying("rts", "/dev/ttyUSB0")), "the settings as they are"
    finally:
        await stopped(m)


async def test_the_modem_writes_its_configuration_starts_the_program_on_free_ports_and_hears_its_control_port(tmp_path: Path) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    try:
        assert m.state == "starting" and m.starts == 1 and _alive(m.pid)
        ini = (tmp_path / INI_FILE).read_text()
        assert "busy_detect = true" in ini and "line = rts" in ini and (tmp_path / PID_FILE).read_text() == str(m.pid)
        await until(lambda: m.state == "running", 5.0)
        assert await connects(m.broadcast_port) and m.control_port == m.broadcast_port + CONTROL_OFFSET
        assert m.describe() == "Mercury DATAC3, listening" and m.hold() == "" and m.problem == "", "the ports are the log's, not the status line's"
    finally:
        pid = m.pid
        await stopped(m)
    assert not _alive(pid) and m.describe() == "Mercury DATAC3, stopped"


async def test_a_program_that_dies_is_said_in_the_problem_and_started_again_after_the_back_off(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.mercury.program")
    m = Mercury(tmp_path, finder=lambda: fakemercury.program(die_after_sec=0.3), backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    changes: list[str] = []
    m.changed.connect(lambda: changes.append(m.state))
    await m.start(HF)
    try:
        await until(lambda: m.state == "waiting", 5.0)
        assert m.problem.startswith("Mercury stopped (exit 3)") and "dies as told" in caplog.text
        await until(lambda: m.starts >= 2, 5.0)
        assert "starting" in changes[changes.index("waiting"):]
    finally:
        await stopped(m)


async def test_a_program_that_is_not_installed_is_one_plain_problem_and_nothing_is_started(tmp_path: Path) -> None:
    m = modem(tmp_path, program=False)
    await m.start(HF)
    assert m.state == "waiting" and m.problem == NOT_INSTALLED and m.starts == 0 and not (tmp_path / INI_FILE).exists()
    assert m.describe() == f"Mercury DATAC3: {NOT_INSTALLED}" and m.sound_cards() == []
    await stopped(m)


async def test_a_program_that_cannot_be_started_is_said_in_the_systems_words(tmp_path: Path) -> None:
    m = Mercury(tmp_path, finder=lambda: [str(tmp_path / "not-there")], backoff=QUICK)
    await m.start(HF)
    assert m.state == "waiting" and m.problem.startswith("Mercury could not be started: ") and "No such file" in m.problem
    await stopped(m)


async def test_a_stale_program_of_ours_is_ended_at_the_next_start_and_a_pid_that_is_not_a_mercury_is_left_alone(tmp_path: Path) -> None:
    pid_file = tmp_path / PID_FILE
    assert not end_stale(pid_file), "no file: nothing to end"
    pid_file.write_text("not a number")
    assert not end_stale(pid_file) and not pid_file.exists()
    pid_file.write_text(str(os.getpid()))
    assert not end_stale(pid_file), "our own process is never a Mercury"
    first = modem(tmp_path)
    await first.start(HF)
    await until(lambda: first.state == "running", 5.0)
    orphan = first.pid
    first._program._process = None                                        # (the daemon crashed: the program lives on, the pid file stays)
    await first.stop()
    assert _alive(orphan) and pid_file.read_text() == str(orphan)
    try:
        if sys.platform == "win32":
            pytest.skip("the command line of another process is not read on Windows")
        second = modem(tmp_path)
        await second.start(HF)
        try:
            await until(lambda: not _alive(orphan), 5.0)
            assert second.pid != orphan and _alive(second.pid)
        finally:
            await stopped(second)
    finally:
        if _alive(orphan):
            os.kill(orphan, signal.SIGTERM)


async def test_stop_ends_the_program_and_the_control_line_and_a_second_start_is_a_fresh_one(tmp_path: Path) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    await until(lambda: m.state == "running", 5.0)
    first_pid, first_port = m.pid, m.broadcast_port
    await m.stop()
    assert not _alive(first_pid)
    for _ in range(20):                                                    # (the system may take a moment to let go of a dead process's sockets)
        if not await connects(first_port):
            break
        await asyncio.sleep(0.1)
    assert not await connects(first_port), "nothing listens on the dead program's port: it and whatever it started are gone"
    await m.start(HF)
    await until(lambda: m.state == "running", 5.0)
    assert m.pid != first_pid and m.starts == 2
    await stopped(m)


# ---- the control port

async def test_the_control_lines_of_a_station_are_the_hold_and_the_words_of_the_status(tmp_path: Path) -> None:
    air = Air(frame_sec=0.3)
    station = air.station()
    await air.start()
    m = modem(tmp_path)
    try:
        await m.start(HF, attach=station.url)
        assert m.attached == station.url and m.broadcast_port == station.port and m.control_port == station.control_port and m.starts == 0
        await until(lambda: m.state == "running")
        station.say_control("PTT ON")
        await until(lambda: m.keyed)
        assert m.hold() == TRANSMITTING and m.describe().endswith("transmitting") and m.frames_keyed == 1
        station.say_control("PTT OFF")
        await until(lambda: not m.keyed)
        station.say_control("BUSY ON")
        await until(lambda: m.busy)
        assert m.hold() == CHANNEL_BUSY and m.describe().endswith("channel busy")
        station.say_control("SN -2.5")
        await until(lambda: m.snr == -2.5)
        station.say_control("BUSY OFF")
        await until(lambda: not m.busy)
        assert m.hold() == "" and m.describe().endswith("listening, SNR -2 dB")
        station.say_control("REGISTERED OH2GBA")                             # (a line NeoAPRS has no use for)
        station.drop_control()
        await until(lambda: m.state == "starting")
        await until(lambda: m.state == "running")                            # (the line is opened again)
        assert station.control_connections == 2
    finally:
        await m.stop()
        await air.aclose()


async def test_a_busy_that_never_ends_holds_nothing_after_a_minute_and_a_ptt_on_that_never_ends_is_not_believed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m = modem(tmp_path, program=False)
    m.busy, m._busy_at = True, 0.0                                           # (BUSY ON came a long time ago)
    assert m.hold() == ""
    m.keyed, m._keyed_at = True, 0.0
    assert m.hold() == ""
    import time
    m._busy_at = m._keyed_at = time.monotonic()
    assert m.hold() == TRANSMITTING, "the hold for the radio keyed comes first"
    m.keyed = False
    assert m.hold() == CHANNEL_BUSY


# ---- the Tnc on a Mercury station

@stops_rigs
async def test_the_tnc_refuses_a_frame_the_modem_would_cut_and_says_so_in_the_terminal(rig: Rigs, caplog: pytest.LogCaptureFixture) -> None:
    r = await rig(profile=MERCURY)
    assert r.tnc.max_frame == 123 and r.tnc.usable
    short = ui_frame(info=b"!6010.00N/02456.00E>hello")
    long = ui_frame(info=b"!6010.00N/02456.00E>" + b"x" * 100)
    assert r.tnc.send_frame(short) and (await r.radio.said(5))[:1] == b"\xc0"
    assert not r.tnc.send_frame(long)
    assert await r.radio.said(1, 0.3) == b"", "nothing of it went to the modem"
    assert any(f"not sent: {len(ax25.encode(long))} bytes, the radio carries 123" in line for line in r.tnc.lines) and "a frame was not sent" in caplog.text
    assert r.tnc.stats.bytes_out == len(kiss.encode(ax25.encode(short)))


@stops_rigs
async def test_the_tnc_holds_its_frames_while_the_modem_transmits_or_hears_a_busy_channel(rig: Rigs, tmp_path: Path) -> None:
    r = await rig(profile=MERCURY)
    m = modem(tmp_path, program=False)
    r.tnc.modem = m
    m.state = "running"
    import time
    m.keyed, m._keyed_at = True, time.monotonic()
    assert not r.tnc.usable and r.tnc.why_unusable() == TRANSMITTING and not r.tnc.send_frame(ui_frame())
    assert r.tnc.describe().startswith("Mercury DATAC3, transmitting")
    m.keyed = False
    m.busy, m._busy_at = True, time.monotonic()
    assert r.tnc.why_unusable() == CHANNEL_BUSY and not r.tnc.send_frame(ui_frame())
    m.busy = False
    assert r.tnc.usable and r.tnc.send_frame(ui_frame())
    r.tnc.profile = replace(MERCURY, key="kiss-tcp", transport="tcp")       # type: ignore[arg-type]
    m.keyed, m._keyed_at = True, time.monotonic()
    assert r.tnc.usable, "the modem is asked only while the profile is a modem's"


async def test_the_tnc_tells_the_modems_problem_when_its_line_cannot_be_opened(tmp_path: Path) -> None:
    m = modem(tmp_path, program=False)
    tnc = Tnc(f"socket://127.0.0.1:{free_ports(18200, 5)[0]}", profile=MERCURY, check_sec=0.0, backoff=Backoff([0.05, 0.05]), fallback_probe=False)
    tnc.modem = m
    await m.start(HF)
    await tnc.start()
    try:
        await until(lambda: tnc.state is Source.State.WAITING)
        assert tnc.problem == NOT_INSTALLED and tnc.describe() == f"Mercury DATAC3: {NOT_INSTALLED}, 0 packets", "the socket the modem is reached on is nowhere in the words of the status"
    finally:
        await tnc.stop()
        await m.stop()


async def test_a_frame_from_a_station_of_the_fake_air_reaches_the_tnc_with_the_senders_command_byte(tmp_path: Path) -> None:
    air = Air(frame_sec=0.05)
    a, b = air.station(), air.station()
    await air.start()
    tnc = Tnc(b.url, profile=MERCURY, check_sec=0.0, backoff=Backoff([0.05, 0.05]), fallback_probe=False)
    heard: list[str] = []
    tnc.packet.connect(lambda p: heard.append(p.source))
    await tnc.start()
    try:
        assert tnc.state is Source.State.CONNECTED
        await b.connected()
        a.feed(b"")                                                           # (a is the other station: what its client hands in goes on the air)
        a.heard_bytes(kiss.encode(ax25.encode(ui_frame("OH2XYZ"))))
        await until(lambda: heard == ["OH2XYZ"])
        assert air.delivered[0][2] == ax25.encode(ui_frame("OH2XYZ")) and air.collisions == 0
        a.heard_bytes(kiss.encode(ax25.encode(ui_frame("OH2LNG", b"!6010.00N/02456.00E>" + b"x" * 120))))
        await until(lambda: len(heard) == 2)
        assert heard[1] == "OH2LNG" and air.truncated == [(len(ax25.encode(ui_frame("OH2LNG", b"!6010.00N/02456.00E>" + b"x" * 120))), 123)], "the air cut it, as Mercury does, and the cut frame still decodes"
    finally:
        await tnc.stop()
        await air.aclose()
    logging.getLogger("neoaprs.tnc").info("done")


# ---- the rest of the shipped program's path: no free pair of ports, a data folder that cannot be written, a program that ignores the request to end (and lists no sound card)

async def test_no_free_pair_of_ports_is_said_and_nothing_is_started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def none() -> tuple[int, int]:
        raise OSError("no free pair of ports from 8100 to 8150")
    monkeypatch.setattr(mercurymodem, "free_ports", none)
    m = modem(tmp_path)
    await m.start(HF)
    assert m.state == "waiting" and m.problem == "no free port for Mercury; the log says which were tried" and m.starts == 0           # (the ports are chosen last, after the configuration is written: that file may be there)
    await stopped(m)


async def test_a_data_folder_that_cannot_be_written_is_said_in_the_systems_words(tmp_path: Path) -> None:
    m = modem(tmp_path / "gone")                    # (no such folder: the configuration cannot be written there)
    await m.start(HF)
    assert m.state == "waiting" and m.problem.startswith("Mercury's configuration could not be written in the data folder: ") and str(tmp_path) not in m.problem and m.starts == 0
    await stopped(m)


async def test_a_program_that_ignores_the_request_to_end_is_killed_and_one_that_lists_no_sound_card_runs_on_the_default_device(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mercury is asked to end (SIGTERM) and killed after STOP_WAIT_SEC when it does not; a `-z` that lists nothing leaves the sound card the system's default and the keying VOX."""
    monkeypatch.setattr(mercuryhelper, "STOP_WAIT_SEC", 0.2)
    stubborn = [sys.executable, "-c", "import signal, sys, time\nif '-z' in sys.argv: sys.exit(0)\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nprint('up', flush=True)\ntime.sleep(60)"]
    m = Mercury(tmp_path, finder=lambda: stubborn, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    pid = m.pid
    assert pid is not None and _alive(pid) and m.starts == 1 and m.sound_card == "" and m.keying == Keying("vox")
    await m.stop()
    assert not _alive(pid) and m.state == "stopped"



async def test_a_sound_card_the_program_cannot_open_ends_the_program_and_is_the_problem_of_the_modem_and_the_radio_until_a_start_succeeds(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """On a station with two USB sound cards Mercury ran on deaf and mute after `[ERR] [audio-play] error in audio->open()`, and the status said "running"."""
    m = Mercury(tmp_path, finder=lambda: fakemercury.program(audio_error=True), backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []
    await m.start(HF)
    tnc = Tnc(f"socket://127.0.0.1:{m.broadcast_port}", profile=MERCURY, check_sec=0.0, backoff=Backoff([0.05, 0.05]), fallback_probe=False)
    tnc.modem = m
    await tnc.start()
    try:
        first = m.pid
        await until(lambda: m.state == "waiting" and m.problem == SOUND_CARD_FAILED, 5.0)              # (the fake prints the error once its ports listen: whether the control line connected first is the machine's business)
        await until(lambda: not _alive(first), 5.0)
        assert m.problem == SOUND_CARD_FAILED and m.hold() == "" and "could not open its sound card" in caplog.text
        if m.state == "waiting":                                                                                       # (the quick back-off may have begun the next start already: the words of the wait are checked while it lasts)
            assert m.describe() == f"Mercury DATAC3: {SOUND_CARD_FAILED}"
        await until(lambda: tnc.state is Source.State.WAITING and tnc.problem == SOUND_CARD_FAILED, 5.0)              # (the line went with the program: the radio is not connected, and says why)
        assert not tnc.usable
        await until(lambda: m.starts >= 2, 5.0)                                                                        # (tried again after the back-off: a card chosen anew is taken then)
        await until(lambda: m.state == "waiting" and m.problem == SOUND_CARD_FAILED and m.starts >= 2, 5.0)
    finally:
        await tnc.stop()
        await stopped(m)


# ---- the ports across a relaunch (the HF Tnc waits on the port it was given; a program started again must be where the dead one was), and where the program listens

def test_a_port_whose_last_connection_is_in_time_wait_counts_as_free_as_it_does_for_mercury() -> None:
    """The HF Tnc's line to a Mercury that died leaves the port in TIME_WAIT; a probe that called that busy made the relaunch take the next pair, which the Tnc never learnt. Mercury binds with SO_REUSEADDR, so the pair is free for it."""
    if sys.platform == "win32":
        pytest.skip("Windows lets a bind through a TIME_WAIT without the option, and the option there means something else")
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)       # (as Mercury's listener does, tcp_interfaces.c; the connections it accepts inherit it, and Linux lets a bind through their TIME_WAIT only then)
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port)) as client:
            conn, _ = server.accept()
            conn.close()                                                   # (the side that closes first is the one left in TIME_WAIT: the server's, on `port`)
            client.recv(1)
    assert mercuryhelper._free(port), "a port with nothing but a TIME_WAIT on it is free"
    with socket.socket() as holder:
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        holder.bind(("127.0.0.1", port))
        holder.listen()
        assert not mercuryhelper._free(port), "a port something listens on is not"


async def tnc_on(m: Mercury) -> Tnc:
    tnc = Tnc(f"socket://127.0.0.1:{m.broadcast_port}", profile=MERCURY, check_sec=0.0, backoff=Backoff([0.05, 0.1]), fallback_probe=False)
    tnc.modem = m
    await tnc.start()
    return tnc


async def test_a_program_that_dies_is_started_again_on_the_same_ports_and_the_tnc_that_waited_on_them_connects_again(tmp_path: Path) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    await until(lambda: m.state == "running", 5.0)
    ports, pid = (m.broadcast_port, m.control_port), m.pid
    tnc = await tnc_on(m)
    try:
        await until(lambda: tnc.usable)
        assert m._program._process is not None
        m._program._process.kill()                                         # (a sound device unplugged: Mercury is gone without a word)
        await until(lambda: m.state == "waiting" and not tnc.usable, 5.0)
        assert tnc.state is not Source.State.CONNECTED and "Mercury stopped" in m.problem, "meanwhile the status is the truth: the modem is down and the radio is not connected"
        await until(lambda: m.starts == 2 and m.running, 5.0)
        assert (m.broadcast_port, m.control_port) == ports and m.pid != pid, "the same pair, where the Tnc waits"
        await until(lambda: tnc.usable, 5.0)
        assert tnc.port == f"socket://127.0.0.1:{ports[0]}"
    finally:
        await tnc.stop()
        await stopped(m)


async def test_a_pair_taken_while_the_program_was_down_gives_another_and_the_owner_is_told_to_point_the_tnc_at_it(tmp_path: Path) -> None:
    m = Mercury(tmp_path, finder=fakemercury.program, backoff=Backoff([1.0, 1.0]), control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []
    told: list[int] = []
    m.ports_changed.connect(lambda: told.append(m.broadcast_port))
    await m.start(HF)
    await until(lambda: m.state == "running", 5.0)
    old = m.broadcast_port
    assert m._program._process is not None
    m._program._process.kill()
    await until(lambda: m.state == "waiting", 5.0)
    with socket.socket() as holder:                                        # (another program takes the KISS port in the second the back-off waits)
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        holder.bind(("127.0.0.1", old))
        holder.listen()
        try:
            await until(lambda: m.starts == 2 and m.running, 5.0)
            assert m.broadcast_port != old and m.control_port == m.broadcast_port + CONTROL_OFFSET
            assert told == [m.broadcast_port], "told once, after the new pair was chosen"
        finally:
            await stopped(m)


def test_the_listeners_of_the_kernels_table_are_read_by_port_and_the_loopback_ones_are_nobodys_concern() -> None:
    tcp = ("  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
           "   0: 0100007F:1FA4 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1 0000000000000000 100 0 0 10 0\n"       # 127.0.0.1:8100 LISTEN
           "   1: 00000000:206C 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1 0000000000000000 100 0 0 10 0\n"       # 0.0.0.0:8300 LISTEN
           "   2: 0100007F:206D 0100007F:B2E4 01 00000000:00000000 00:00000000 00000000  1000        0 1 0000000000000000 100 0 0 10 0\n"       # 8301 ESTABLISHED: not a listener
           "   3: 0100007F:1F41 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1 0000000000000000 100 0 0 10 0\n")      # 8001: not asked about
    tcp6 = ("  sl  local_address                         remote_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
            "   0: 00000000000000000000000000000000:206D 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1 0000000000000000 100 0 0 10 0\n"
            "   1: 00000000000000000000000001000000:1FA4 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1 0000000000000000 100 0 0 10 0\n")
    found = mercuryhelper._listeners((tcp, tcp6), (8100, 8300, 8301))
    assert found == {8100: {"0100007F", "00000000000000000000000001000000"}, 8300: {"00000000"}, 8301: {"00000000000000000000000000000000"}}
    foreign = [f"{a}:{p}" for p, s in sorted(found.items()) for a in sorted(s) if a not in mercuryhelper.LOOPBACK_HEX]
    assert foreign == ["00000000:8300", "00000000000000000000000000000000:8301"], "the IPv4 and the IPv6 loopback are ours; INADDR_ANY and :: are the LAN's"
    assert mercuryhelper._listeners((tcp,), ()) == {} and mercuryhelper._listeners((), (8100,)) == {}


async def test_the_fake_program_listens_on_the_loopback_and_one_that_listens_on_the_network_is_ended_and_not_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until(lambda: m.state == "running", 5.0)
        assert mercuryhelper.foreign_listeners((m.broadcast_port, m.control_port)) == [], "the fake binds 127.0.0.1, as the shipped program does"
    finally:
        await stopped(m)
    monkeypatch.setattr(mercurymodem, "foreign_listeners", lambda ports: [f"00000000:{p}" for p in ports])        # (a Mercury that is not the shipped one: INADDR_ANY)
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until(lambda: m.state == "waiting", 5.0)
        pid = m.pid
        assert m.problem == mercurymodem.OPEN_TO_NETWORK and m.starts == 1
        await until(lambda: not _alive(pid), 5.0)
        await asyncio.sleep(0.5)                                           # (the back-off of a program that died is 0.1 s: a relaunch would have come)
        assert m.starts == 1 and m.state == "waiting", "ended, and not started again"
        assert m.describe() == f"Mercury DATAC3: {mercurymodem.OPEN_TO_NETWORK}"
    finally:
        await stopped(m)


# ---- the rest of the review's list for the modem part: a launch that fails and is tried again, the ports left alone, the speaker without pipes, the order of a launch, the shipped program

async def test_a_launch_that_fails_for_a_reason_that_may_pass_is_tried_again_after_the_back_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    real = mercurymodem.free_ports

    def once_none() -> tuple[int, int]:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("no free pair of ports from 8100 to 8150")
        return real()
    monkeypatch.setattr(mercurymodem, "free_ports", once_none)
    m = modem(tmp_path)
    await m.start(HF)
    try:
        assert m.state == "waiting" and m.reason == "no_port" and m.starts == 0
        await until(lambda: m.running, 5.0)
        assert m.starts == 1 and len(calls) == 2, "the second try, after the back-off, had its pair"
    finally:
        await stopped(m)


async def test_the_fm_radios_the_gpss_and_the_skipped_ports_are_never_chosen_to_key_the_radio(tmp_path: Path) -> None:
    m = modem(tmp_path)
    m.ports = lambda: [SerialPort("/dev/ttyUSB0", 0x10C4, 0xEA60), SerialPort("/dev/ttyUSB1", 0x10C4, 0xEA60)]
    await m.start(replace(HF, mercury_sound_card="", mercury_keying="", serial_port="/dev/ttyUSB0"))
    try:
        await until(lambda: m.running, 5.0)
        assert m.keying == Keying("rts", "/dev/ttyUSB1"), "the FM radio's port is not the one"
    finally:
        await m.stop()
    await m.start(replace(HF, mercury_sound_card="", mercury_keying="", gps_device="/dev/ttyUSB1", serial_skip="/dev/ttyUSB0"))
    try:
        await until(lambda: m.running, 5.0)
        assert m.keying == Keying("vox"), "the GPS's port and a skipped port leave no serial port: VOX"
    finally:
        await stopped(m)


def test_the_page_is_proposed_the_card_and_the_keying_the_daemon_would_choose_and_the_ports_of_the_other_radios_key_nothing() -> None:
    cards = [SoundCard("plughw:1,0", "USB AUDIO  CODEC USB Audio", True, True, False), SoundCard("plughw:0,0", "HDA Intel PCH", True, True, True)]
    usb = [PortInfo("/dev/ttyUSB0", "CP2102", "USB VID:PID=10C4:EA60", 0x10C4, 0xEA60)]
    assert proposal(cards, usb, DEFAULTS) == ("plughw:1,0", "rts:/dev/ttyUSB0")
    assert proposal(cards, usb, replace(DEFAULTS, serial_port="/dev/ttyUSB0")) == ("plughw:1,0", "vox"), "the FM radio's port keys no HF radio"
    assert proposal(cards[1:], usb, DEFAULTS) == ("plughw:0,0", "vox"), "the system's default device, named, and no radio's sound card to key a line by"
    assert proposal([], usb, DEFAULTS) == ("", "")


async def test_the_stale_program_is_ended_before_the_sound_cards_are_listed_and_the_ports_are_chosen_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    real_free, real_stale, real_cards = mercurymodem.free_ports, mercurymodem.end_stale, mercuryhelper.list_sound_cards
    monkeypatch.setattr(mercurymodem, "free_ports", lambda: (order.append("ports"), real_free())[1])
    monkeypatch.setattr(mercurymodem, "end_stale", lambda pid_file: (order.append("stale"), real_stale(pid_file))[1])
    monkeypatch.setattr(mercuryhelper, "list_sound_cards", lambda command, timeout_sec=15.0: (order.append("cards"), real_cards(command, timeout_sec))[1])
    m = modem(tmp_path)
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    try:
        await until(lambda: m.running, 5.0)
        assert order == ["stale", "cards", "ports"], "a program left behind holds the ports: ended first; the pair chosen after the seconds mercury -z takes, so that nobody takes it meanwhile"
    finally:
        await stopped(m)


async def test_without_named_pipes_the_speaker_of_the_dummy_hf_radio_is_not_started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """A Mercury started on the system's default devices for real would play DATAC3 out of the speakers' output and open the microphone, which "nothing goes on the air" does not allow (a VOX radio on the default output would key)."""
    caplog.set_level(logging.INFO, "neoaprs.mercury")
    monkeypatch.setattr(mercurymodem.SpeakerAudio, "prepare", lambda self: False)
    m = modem(tmp_path)
    await m.start(HF, speaker=True)
    assert m.state == "stopped" and m.starts == 0 and "no named pipes" in caplog.text
    await stopped(m)


@pytest.mark.skipif(sys.platform == "win32", reason="the shipped program here is a shell script that stands in for mercury.exe")
async def test_the_shipped_program_is_started_with_no_question_asked_of_the_system_and_is_said_to_be_the_shipped_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """The Mercury NeoAPRS ships binds the loopback on every system, so it is started at once: no PowerShell and no netsh are run for it, whatever the system (the Windows installer's firewall rule and the daemon's
    check of the firewall are gone); the log says the program is the shipped one, and that a program named by its path elsewhere is not."""
    asked: list[str] = []
    real_run = subprocess.run

    def run(command: list[str] | str, *args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        asked.append(str(command))
        return real_run(command, *args, **kwargs)  # type: ignore[call-overload, no-any-return]

    monkeypatch.setattr(subprocess, "run", run)
    shipped = tmp_path / "tools" / "mercury" / mercuryhelper.program_file()
    shipped.parent.mkdir(parents=True)
    shipped.write_text("#!/bin/sh\nexec " + " ".join(shlex.quote(part) for part in fakemercury.program()) + ' "$@"\n')
    shipped.chmod(0o755)
    monkeypatch.setattr(mercuryhelper, "tools_dir", lambda: tmp_path / "tools")
    assert mercuryhelper.is_shipped([str(shipped)]) and not mercuryhelper.is_shipped([str(tmp_path / "mercury.exe")]) and not mercuryhelper.is_shipped(fakemercury.program())
    caplog.set_level(logging.INFO, "neoaprs.mercury")
    m = Mercury(tmp_path, finder=lambda: [str(shipped)], backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []                                                  # (never the operator's serial ports)
    await m.start(HF)
    try:
        await until(lambda: m.running, 5.0)
        assert m.starts == 1 and m.reason == "" and "(not the one NeoAPRS ships)" not in caplog.text
        assert not [call for call in asked if "powershell" in call.lower() or "netsh" in call.lower()], asked
    finally:
        await stopped(m)
    m = Mercury(tmp_path, finder=lambda: [str(tmp_path / "not-there")], backoff=QUICK)          # (a program named by its path elsewhere: said not to be the shipped one; what it is said to be is the system's words)
    await m.start(HF)
    assert m.reason == "not_started" and "(not the one NeoAPRS ships)" in caplog.text
    await stopped(m)


def test_a_warning_the_program_repeats_is_in_the_log_the_first_tenth_and_every_hundredth_time(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.mercury.program")
    program = mercuryhelper.Program(lambda code, lines: None)
    for _ in range(250):
        program._tell("[WRN] [audio] snd_pcm_readi: Input/output error")
    program._tell("[INF] [engine] Mercury engine initialised")
    said = [r for r in caplog.records if r.name == "neoaprs.mercury.program"]
    assert [r.levelno for r in said if "snd_pcm" in r.getMessage()] == [logging.INFO] * 4, "the 1st, the 10th, the 100th and the 200th"
    assert "(the 200th time)" in said[3].getMessage() and said[-1].levelno == logging.DEBUG
