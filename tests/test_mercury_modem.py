"""The Mercury HF modem as a part of the daemon (neoaprs/mercurymodem.py, mercuryhelper.py, mercurycontrol.py) on the program that stands in for Mercury (tests/support/fakemercury.py, run as the binary) and on a station of the
fake air: the program found, given free ports and the configuration, started, read, started again when it dies, stopped with nothing left behind; a program that is not installed, that cannot be started, whose ports are taken;
the control port's `PTT ON/OFF`, `BUSY ON/OFF` and `SN` as the hold the Tnc asks about and the words of the status line; and the Tnc on a Mercury station: the frame cap as the last guard, the hold while a frame is on the
air, the modem's problem as the radio's."""
import asyncio
import logging
import os
import random
import signal
import socket
import sys
from pathlib import Path

import pytest

from neoaprs import ax25, kiss
from dataclasses import replace

from neoaprs.config import DEFAULTS, Config
from neoaprs.mercury import BROADCAST_PORT, CONTROL_OFFSET, Keying, SerialPort, SoundCard
from neoaprs import mercuryhelper, mercurymodem
from neoaprs.mercuryhelper import PORT_TRIES, end_stale, environment, find, free_ports, list_sound_cards
from neoaprs.mercurymodem import CHANNEL_BUSY, INI_FILE, NOT_INSTALLED, PID_FILE, TRANSMITTING, Mercury
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


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """The modem asks for free ports from Mercury's defaults up; here each test asks from a base of its own, so that two tests running side by side (pytest-xdist) do not both find 8100 free between the probe and
    the bind (one of them then started a program that could not listen)."""
    base = random.randrange(20000, 60000, 500)
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
        assert m.describe().startswith(f"Mercury DATAC3 at 127.0.0.1:{m.broadcast_port}, listening") and m.hold() == "" and m.problem == ""
    finally:
        pid = m.pid
        await stopped(m)
    assert not _alive(pid) and m.describe() == f"Mercury DATAC3 at 127.0.0.1:{m.broadcast_port}, stopped"


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
    assert not _alive(first_pid) and not await connects(first_port)
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
    assert r.tnc.describe().startswith("Mercury DATAC3 at 127.0.0.1:") and "transmitting" in r.tnc.describe()
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
        assert tnc.problem == NOT_INSTALLED and tnc.describe() == f"{tnc.port}, waiting"
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
    assert m.state == "waiting" and m.problem == "no free port for Mercury: no free pair of ports from 8100 to 8150" and m.starts == 0 and not (tmp_path / INI_FILE).exists()
    await stopped(m)


async def test_a_data_folder_that_cannot_be_written_is_said_in_the_systems_words(tmp_path: Path) -> None:
    m = modem(tmp_path / "gone")                    # (no such folder: the configuration cannot be written there)
    await m.start(HF)
    assert m.state == "waiting" and m.problem.startswith("Mercury's configuration could not be written to ") and "gone" in m.problem and m.starts == 0
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

