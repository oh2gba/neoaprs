"""The Mercury HF modem as part of the daemon (mercurymodem.py, mercuryhelper.py, mercurycontrol.py)
on the fake Mercury program and air: found, given ports and configuration, started, read, restarted,
stopped cleanly.
"""

import asyncio
import logging
import os
import shlex
import signal
import socket
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

from neoaprs import ax25, kiss
from dataclasses import replace

from neoaprs.config import DEFAULTS, Config
from neoaprs.mercury import BROADCAST_PORT, CONTROL_OFFSET, Keying, SerialPort, SoundCard
from neoaprs.mercurycontrol import EMPTY, HELD, ControlLine
from neoaprs import bundled, childprogram, mercuryhelper, mercurymodem, modemstate, soundserver
from neoaprs.mercuryhelper import environment, find, free_ports, list_sound_cards, pair_free
from neoaprs.mercurystale import end_stale
from neoaprs.claims import Claim, Claims
from neoaprs.mercurymodem import (
    CHANNEL_BUSY,
    INI_FILE,
    NOT_INSTALLED,
    PID_FILE,
    SOUND_CARD_FAILED,
    TRANSMITTING,
    Mercury,
)
from neoaprs.mercurychoice import proposal
from neoaprs.mercurydriver import MercuryDriver
from neoaprs.radiodriver import RunOverrides
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import HF_ID
from neoaprs.serialprobe import PortInfo, claim_value
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import MERCURY
from tests.support import fakemercury
from tests.support.env import until, until_started
from neoaprs.radiotypes import type_of
from tests.support.fakemercury import Air, of_radio
from tests.support.modemports import own_ports
from tests.test_tnc import Rigs, stops_rigs, ui_frame

HF: Config = replace(
    DEFAULTS,
    hf_enabled=True,
    fm_enabled=False,
    mercury_keying="rts:/dev/ttyUSB0",
    mercury_sound_card="plughw:1,0",
    station_call="OH2GBA",
)
QUICK = Backoff([0.1, 0.1])


@pytest.fixture
def rig() -> Rigs:
    return Rigs()


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test asks the modem for free ports from a base of its own (tests/support/modemports.py):
    no other test running beside it is handed its ports."""
    own_ports(monkeypatch)


# A radio's modem, and the modem of today's station (no table, no folder: the data folder)
SHAPES = pytest.mark.parametrize("radio", [True, False], ids=["radio", "folderless"])


def modem(tmp_path: Path, program: bool = True, radio: bool = True) -> Mercury:
    m = Mercury(
        tmp_path,
        finder=(fakemercury.program if program else lambda: None),
        backoff=QUICK,
        control_backoff=Backoff([0.05, 0.05]),
        **(of_radio(tmp_path) if radio else {}),
    )
    m.ports = lambda: []  # (never the operator's serial ports)
    return m


async def stopped(m: Mercury) -> None:
    await m.stop()
    assert m.state == "stopped" and m.pid is None or not _alive(m.pid)


def _alive(pid: int | None) -> bool:
    """Whether the process is still running. On Windows os.kill(pid, 0) is TerminateProcess, and a
    handle to a process that has ended still opens, so the exit code is asked instead."""
    if pid is None:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
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


def test_the_program_is_the_shipped_one_in_the_tools_folder_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not on the PATH, not in the data folder: the operator's system is left alone, and the Mercury
    that runs is the one the release carries (bundled.py says where each install kind puts it)."""
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
    # Windows has no executable bit: a .exe can always be run
    if sys.platform != "win32":
        assert find(tmp_path / "tools") is None, "a file that cannot be run is no program"
    shipped.chmod(0o755)
    assert find(tmp_path / "tools") == [str(shipped)]
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    # The guard of the tests gave it a folder that is not there; the prefix is this test's own
    # folder now
    monkeypatch.setattr(mercuryhelper, "tools_dir", bundled.tools_dir)
    assert find() == [str(shipped)], "a venv, the AppImage and the .deb: tools/ of the Python's prefix"


def test_the_bundled_alsa_configuration_is_given_to_the_program_through_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Linux bundle carries its own ALSA library and configuration (a machine without ALSA
    installed has no /usr/share/alsa/alsa.conf); ALSA_CONFIG_PATH is the one way to tell the library
    where it is."""
    monkeypatch.delenv("ALSA_CONFIG_PATH", raising=False)
    program = tmp_path / "mercury" / "mercury"
    program.parent.mkdir()
    program.write_text("")
    assert "ALSA_CONFIG_PATH" not in environment([str(program)]), "no configuration beside the program: the system's"
    conf = tmp_path / "mercury" / "share" / "alsa" / "alsa.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("")
    assert environment([str(program)])["ALSA_CONFIG_PATH"] == str(conf)
    assert "ALSA_CONFIG_PATH" not in environment([sys.executable, "-m", "tests.support.fakemercury"]), (
        "the fake that stands in for the program is not a bundle"
    )
    assert "PATH" in environment([str(program)]), (
        "the reduced environment of a child, as for every program the daemon starts"
    )


def three_free_pairs() -> int:
    """The first of three pairs that are free now: a Mercury of the machine's own (the developer's
    station, the simulation of another worktree's suite) may hold Mercury's defaults and any fixed
    range."""
    for first in range(18100, 19900, 10):
        if all(pair_free(port) for port in range(first, first + 3)):
            return first
    pytest.skip("no three free pairs of ports on this machine")


def test_the_ports_are_mercurys_defaults_when_free_else_the_next_pair_with_the_control_port_200_above() -> None:
    first = three_free_pairs()
    assert free_ports(first, 3) == (first, first + CONTROL_OFFSET)
    with socket.socket() as holder:
        # A program holds the control port: the pair is skipped
        holder.bind(("127.0.0.1", first + CONTROL_OFFSET))
        assert free_ports(first, 3) == (first + 1, first + 1 + CONTROL_OFFSET)
        with socket.socket() as second, socket.socket() as third:
            second.bind(("127.0.0.1", first + 1))
            third.bind(("127.0.0.1", first + 2))
            with pytest.raises(OSError, match="no free pair"):
                free_ports(first, 3)
    assert BROADCAST_PORT == 8100 and CONTROL_OFFSET == 200


def test_the_sound_cards_come_from_the_program_and_a_program_that_cannot_run_lists_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert list_sound_cards(fakemercury.program()) == [
        SoundCard("plughw:1,0", "USB Audio CODEC", True, True, True),
        SoundCard("plughw:0,0", "HDA Intel PCH", True, False, False),
    ]
    assert list_sound_cards(["/nonexistent/mercury"]) == [] and "could not be run" in caplog.text


# ---- the program's life


async def test_the_modem_chooses_the_sound_card_and_the_keying_when_the_settings_are_empty_and_takes_them_when_set(
    tmp_path: Path,
) -> None:
    m = modem(tmp_path)
    m.ports = lambda: [SerialPort("/dev/ttyUSB0", 0x10C4, 0xEA60)]
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    try:
        await until_started(lambda: m.state == "running")
        assert (m.sound_card, m.keying) == ("", Keying("rts", "/dev/ttyUSB0")), (
            "the fake program lists a USB Audio CODEC that is the system's default (a computer whose only card is the radio's): Mercury's default device is right, and the one CP2102 port keys it"
        )
        assert "line = rts" in (m.home / INI_FILE).read_text()
    finally:
        await m.stop()
    m.ports = lambda: []
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    try:
        await until_started(lambda: m.state == "running")
        assert (m.sound_card, m.keying) == ("", Keying("vox")), "no serial port: VOX"
    finally:
        await m.stop()
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "running")
        assert (m.sound_card, m.keying) == ("plughw:1,0", Keying("rts", "/dev/ttyUSB0")), "the settings as they are"
    finally:
        await stopped(m)


async def test_an_hf_radio_after_radio_2_was_removed_runs_its_modem_on_its_own_sound_card_keying_and_gain(
    tmp_path: Path,
) -> None:
    """The modem reads its own radio's settings, never radio 2's: a station that removed its radio 2
    and later added a Mercury radio (id 5) runs that radio's modem on the card, the keying and the
    gain the operator gave radio 5, not on the daemon's own choice and 0 dB."""
    fm = RadioSpec(1, "fm", "kiss", "", True, 1, None, {"port": "/dev/ttyUSB0"})
    gone = RadioSpec(
        2,
        "hf",
        "mercury",
        "",
        False,
        2,
        datetime(2026, 11, 1, tzinfo=timezone.utc),
        {"sound_card": "plughw:1,0", "keying": "rts:/dev/ttyUSB1"},
    )
    five = RadioSpec(
        5,
        "hf",
        "mercury",
        "",
        True,
        3,
        None,
        {"sound_card": "plughw:2,0", "keying": "rts:/dev/ttyUSB2", "tx_gain_db": "-6"},
    )
    station = Config.from_data({}, radios=(fm, gone, five))
    m = Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=QUICK,
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path, 5),
    )
    m.ports = lambda: []
    driver = MercuryDriver(five, m.claims or Claims(), m.home, modem=m)
    driver.configure(five, station, RunOverrides(check_sec=0.0))
    await driver.start()
    try:
        await until_started(lambda: m.state == "running")
        assert (m.sound_card, m.keying, m.tx_gain_db) == ("plughw:2,0", Keying("rts", "/dev/ttyUSB2"), -6), (
            "radio 5's own, not radio 2's and not the daemon's choice"
        )
    finally:
        await driver.stop()


@SHAPES
async def test_the_modem_writes_its_configuration_starts_the_program_on_free_ports_and_hears_its_control_port(
    tmp_path: Path, radio: bool
) -> None:
    m = modem(tmp_path, radio=radio)
    await m.start(HF)
    try:
        assert m.state == "starting" and m.starts == 1 and _alive(m.pid)
        ini = (m.home / INI_FILE).read_text()
        assert "busy_detect = true" in ini and "line = rts" in ini and (m.home / PID_FILE).read_text() == str(m.pid)
        if radio:
            assert (
                m.home == tmp_path / "radios" / "2"
                and not (tmp_path / INI_FILE).exists()
                and not (tmp_path / PID_FILE).exists()
            ), "the files are the radio's, in its own folder"
        else:
            assert (
                m.home == tmp_path and m.claims is None and [p.name for p in tmp_path.iterdir() if p.is_dir()] == []
            ), "today's modem: its files in the data folder, no folder made"
        await until_started(lambda: m.state == "running")
        assert await connects(m.broadcast_port) and m.control_port == m.broadcast_port + CONTROL_OFFSET
        assert m.describe() == "Mercury DATAC3, listening" and m.hold() == "" and m.problem == "", (
            "the ports are the log's, not the status line's"
        )
        held = [
            Claim("sound_card", "plughw:1,0", HF_ID),
            Claim("keying", claim_value("/dev/ttyUSB0"), HF_ID),
            Claim("modem_ports", str(m.broadcast_port), HF_ID),
        ]
        assert m.held() == (held if radio else []), (
            "the radio holds what its modem runs with; without the table nothing is held"
        )
    finally:
        pid = m.pid
        await stopped(m)
    assert not _alive(pid) and m.describe() == "Mercury DATAC3, stopped"
    assert m.held() == [] and (m.claims is None or m.claims.all() == ()), "a stopped modem holds nothing"
    assert not (m.home / PID_FILE).exists() and (m.home / INI_FILE).exists(), (
        "a clean stop removes the id where it was written"
    )


async def test_a_program_that_dies_is_said_in_the_problem_and_started_again_after_the_back_off(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, "neoaprs.mercury.program")
    m = Mercury(
        tmp_path,
        finder=lambda: fakemercury.program(die_after_sec=0.3),
        backoff=QUICK,
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path),
    )
    changes: list[tuple[str, str]] = []
    m.changed.connect(lambda: changes.append((m.state, m.problem)))
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "waiting")
        assert m.problem.startswith("Mercury stopped (exit 3)") and "dies as told" in caplog.text
        await until_started(lambda: m.starts >= 2)
        assert sorted(c.kind for c in m.held()) == ["keying", "modem_ports", "sound_card"], (
            "a program that died and is started again keeps what the radio holds"
        )
        after = changes[[state for state, _ in changes].index("waiting") :]
        assert all(
            state == "running" or (state == "waiting" and problem.startswith("Mercury stopped (exit 3)"))
            for state, problem in after
        ), f"the problem stands through the next start until it is running: {after}"
    finally:
        await stopped(m)


async def test_a_program_that_is_not_installed_is_one_plain_problem_and_nothing_is_started(tmp_path: Path) -> None:
    m = modem(tmp_path, program=False)
    await m.start(HF)
    assert (
        m.state == "waiting" and m.problem == NOT_INSTALLED and m.starts == 0 and not m.home.exists() and m.held() == []
    ), "nothing is made and nothing held"
    assert m.describe() == f"Mercury DATAC3: {NOT_INSTALLED}" and m.sound_cards() == []
    await stopped(m)


async def test_a_program_that_cannot_be_started_is_said_in_the_systems_words(tmp_path: Path) -> None:
    m = Mercury(tmp_path, finder=lambda: [str(tmp_path / "not-there")], backoff=QUICK, **of_radio(tmp_path))
    await m.start(HF)
    assert (
        m.state == "waiting" and m.problem.startswith("Mercury could not be started: ") and "No such file" in m.problem
    )
    await stopped(m)


@SHAPES
async def test_a_stale_program_of_ours_is_ended_at_the_next_start_and_a_pid_that_is_not_a_mercury_is_left_alone(
    tmp_path: Path, radio: bool
) -> None:
    pid_file, ini, program = tmp_path / PID_FILE, tmp_path / INI_FILE, fakemercury.program()
    assert not end_stale(pid_file, ini, program), "no file: nothing to end"
    pid_file.write_text("not a number")
    assert not end_stale(pid_file, ini, program) and not pid_file.exists()
    pid_file.write_text(str(os.getpid()))
    assert not end_stale(pid_file, ini, program), "our own process is never a Mercury"
    first = modem(tmp_path, radio=radio)
    await first.start(HF)
    await until_started(lambda: first.state == "running")
    orphan = first.pid
    # The daemon crashed: the program lives on, the pid file stays
    first._program._process = None
    await first.stop()
    assert (
        _alive(orphan) and (first.home / PID_FILE).read_text() == str(orphan) and (first.home == tmp_path) is not radio
    )
    try:
        if sys.platform == "win32":
            pytest.skip("the command line of another process is not read on Windows")
        second = modem(tmp_path, radio=radio)
        await second.start(HF)
        try:
            await until_started(lambda: not _alive(orphan))
            assert (
                second.pid != orphan and _alive(second.pid) and (second.home / PID_FILE).read_text() == str(second.pid)
            ), "ended where its file is, and the new id written there"
        finally:
            await stopped(second)
    finally:
        if _alive(orphan):
            os.kill(orphan, signal.SIGTERM)


async def test_stop_ends_the_program_and_the_control_line_and_a_second_start_is_a_fresh_one(tmp_path: Path) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    await until_started(lambda: m.state == "running")
    first_pid, first_port = m.pid, m.broadcast_port
    await m.stop()
    assert not _alive(first_pid)
    # The system may take a moment to let go of a dead process's sockets
    for _ in range(20):
        if not await connects(first_port):
            break
        await asyncio.sleep(0.1)
    assert not await connects(first_port), (
        "nothing listens on the dead program's port: it and whatever it started are gone"
    )
    await m.start(HF)
    await until_started(lambda: m.state == "running")
    assert m.pid != first_pid and m.starts == 2
    await stopped(m)


@pytest.mark.slow("a Mercury that takes a second to end, twice")
async def test_a_run_slow_to_end_is_gone_before_the_next_start_asks_who_listens_on_the_pair(tmp_path: Path) -> None:
    """An off and on, and a relaunch: the run before is never taken for another program."""
    m = modem(tmp_path)
    m._finder = lambda: fakemercury.program(linger_sec=1.0)
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "running")
        await m.start(HF)  # (a settings change: stop, then start)
        await until_started(lambda: m.state == "running")
        assert m.reason == "" and m.starts == 2
        m._end_run("for the test")  # a relaunch: ended on a thread, started again after the back-off
        await until_started(lambda: m.starts == 3 and m.state == "running")
        assert m.reason == "" and [s.words() for s in m.start_log].count("failed: ports_taken") == 0
    finally:
        await stopped(m)


# ---- the control port


async def test_a_control_port_another_program_holds_is_open_only_once_mercury_writes_on_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Mercury keeps its control port for the connected host and closes another one at once
    (refuse_client).

    The line of a Mercury whose port another program holds is not opened and lost at every try; it
    opens once Mercury takes the port and writes on it.
    """
    caplog.set_level(logging.INFO, "neoaprs.mercury")
    held, tries = [True], [0]

    async def mercury(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tries[0] += 1
        if not held[0]:
            writer.write(b"IAMALIVE\r")
            await writer.drain()
            await reader.read(4096)
        writer.close()

    server = await asyncio.start_server(mercury, "127.0.0.1", 0)
    states: list[tuple[bool, str]] = []
    events: list[str] = []
    line = ControlLine(
        "127.0.0.1",
        server.sockets[0].getsockname()[1],
        lambda e: events.append(e.kind),
        lambda up, why: states.append((up, why)),
        Backoff([0.01]),
    )
    line.start()
    try:
        await until_started(lambda: tries[0] >= 4)
        assert states == [(True, ""), (False, EMPTY)] and not line.connected, (
            "what was seen, once, and not open meanwhile"
        )
        assert [r.getMessage() for r in caplog.records].count(f"mercury control port {line.port}: {HELD}") == 1
        held[0] = False
        await until_started(lambda: states[-1] == (True, "") and events == ["alive"])
        assert line.connected and len(states) == 3
    finally:
        await line.stop()
        server.close()
        await server.wait_closed()


async def test_a_control_port_beyond_the_last_port_is_a_failed_connect_tried_again_and_never_the_lines_end() -> None:
    asked = [0]

    def refuses() -> bool:
        asked[0] += 1
        return False

    line = ControlLine(
        "127.0.0.1", 65400 + CONTROL_OFFSET, lambda e: None, lambda up, why: None, Backoff([0.01]), refuses
    )
    line.start()
    try:
        await until(lambda: asked[0] >= 3)
        assert not line.connected
    finally:
        await line.stop()


def test_your_own_programs_mercury_takes_only_a_kiss_port_whose_control_port_fits() -> None:
    port = type_of("mercury-own").field("tcp_port")
    assert port is not None and port.range == (1, 65535 - CONTROL_OFFSET)
    assert port.parse(str(65535 - CONTROL_OFFSET)) == 65535 - CONTROL_OFFSET
    with pytest.raises(ValueError):
        port.parse("65400")


async def test_a_mercury_that_ends_before_it_writes_a_line_is_not_said_to_be_held_by_another_program(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One connection that Mercury closes before its first line is Mercury ending as often as a
    refusal."""
    caplog.set_level(logging.INFO, "neoaprs.mercury")
    tries = [0]

    async def mercury(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tries[0] += 1
        if tries[0] > 1:
            writer.write(b"IAMALIVE\r")
            await writer.drain()
            await reader.read(4096)
        writer.close()

    server = await asyncio.start_server(mercury, "127.0.0.1", 0)
    states: list[tuple[bool, str]] = []
    events: list[str] = []
    line = ControlLine(
        "127.0.0.1",
        server.sockets[0].getsockname()[1],
        lambda e: events.append(e.kind),
        lambda up, why: states.append((up, why)),
        Backoff([0.01]),
    )
    line.start()
    try:
        await until_started(lambda: events == ["alive"])
        assert states == [(True, ""), (False, EMPTY), (True, "")]
        assert not any(HELD in r.getMessage() for r in caplog.records)
    finally:
        await line.stop()
        server.close()
        await server.wait_closed()


async def test_the_control_lines_of_a_station_are_the_hold_and_the_words_of_the_status(tmp_path: Path) -> None:
    air = Air(frame_sec=0.3)
    station = air.station()
    await air.start()
    m = modem(tmp_path)
    try:
        await m.start(HF, attach=station.url)
        assert (
            m.attached == station.url
            and m.broadcast_port == station.port
            and m.control_port == station.control_port
            and m.starts == 0
        )
        await until_started(lambda: m.state == "running")
        station.say_control("PTT ON")
        await until_started(lambda: m.keyed)
        assert m.hold() == TRANSMITTING and m.describe().endswith("transmitting") and m.frames_keyed == 1
        station.say_control("PTT OFF")
        await until_started(lambda: not m.keyed)
        station.say_control("BUSY ON")
        await until_started(lambda: m.busy)
        assert m.hold() == CHANNEL_BUSY and m.describe().endswith("channel busy")
        station.say_control("SN -2.5")
        await until_started(lambda: m.snr == -2.5)
        station.say_control("BUSY OFF")
        await until_started(lambda: not m.busy)
        assert m.hold() == "" and m.describe().endswith("listening, SNR -2 dB")
        station.say_control("REGISTERED OH2GBA")  # (a line NeoAPRS has no use for)
        station.drop_control()
        await until_started(lambda: m.state == "starting")
        await until_started(lambda: m.state == "running")  # (the line is opened again)
        assert station.control_connections == 2
    finally:
        await m.stop()
        await air.aclose()


async def test_a_busy_that_never_ends_holds_nothing_after_a_minute_and_a_ptt_on_that_never_ends_is_not_believed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = modem(tmp_path, program=False)
    m.busy, m._busy_at = True, 0.0  # (BUSY ON came a long time ago)
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
async def test_the_tnc_refuses_a_frame_the_modem_would_cut_and_says_so_in_the_terminal(
    rig: Rigs, caplog: pytest.LogCaptureFixture
) -> None:
    r = await rig(profile=MERCURY)
    assert r.tnc.max_frame == 123 and r.tnc.usable
    short = ui_frame(info=b"!6010.00N/02456.00E>hello")
    long = ui_frame(info=b"!6010.00N/02456.00E>" + b"x" * 100)
    assert r.tnc.send_frame(short) and (await r.radio.said(5))[:1] == b"\xc0"
    assert not r.tnc.send_frame(long)
    assert await r.radio.said(1, 0.3) == b"", "nothing of it went to the modem"
    assert (
        any(f"not sent: {len(ax25.encode(long))} bytes, the radio carries 123" in line for line in r.tnc.lines)
        and "a frame was not sent" in caplog.text
    )
    assert r.tnc.stats.bytes_out == len(kiss.encode(ax25.encode(short)))


@stops_rigs
async def test_the_tnc_holds_its_frames_while_the_modem_transmits_or_hears_a_busy_channel(
    rig: Rigs, tmp_path: Path
) -> None:
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
    r.tnc.profile = replace(MERCURY, key="kiss-tcp", transport="tcp")  # type: ignore[arg-type]
    m.keyed, m._keyed_at = True, time.monotonic()
    assert r.tnc.usable, "the modem is asked only while the profile is a modem's"


async def test_the_tnc_tells_the_modems_problem_when_its_line_cannot_be_opened(tmp_path: Path) -> None:
    m = modem(tmp_path, program=False)
    tnc = Tnc(
        f"socket://127.0.0.1:{free_ports(18200, 5)[0]}",
        profile=MERCURY,
        check_sec=0.0,
        backoff=Backoff([0.05, 0.05]),
        fallback_probe=False,
    )
    tnc.modem = m
    await m.start(HF)
    await tnc.start()
    try:
        await until_started(lambda: tnc.state is Source.State.WAITING)
        assert tnc.problem == NOT_INSTALLED and tnc.describe() == f"Mercury DATAC3: {NOT_INSTALLED}, 0 packets", (
            "the socket the modem is reached on is nowhere in the words of the status"
        )
    finally:
        await tnc.stop()
        await m.stop()


async def test_a_frame_from_a_station_of_the_fake_air_reaches_the_tnc_with_the_senders_command_byte(
    tmp_path: Path,
) -> None:
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
        # A is the other station: what its client hands in goes on the air
        a.feed(b"")
        a.heard_bytes(kiss.encode(ax25.encode(ui_frame("OH2XYZ"))))
        await until_started(lambda: heard == ["OH2XYZ"])
        assert air.delivered[0][2] == ax25.encode(ui_frame("OH2XYZ")) and air.collisions == 0
        a.heard_bytes(kiss.encode(ax25.encode(ui_frame("OH2LNG", b"!6010.00N/02456.00E>" + b"x" * 120))))
        await until_started(lambda: len(heard) == 2)
        assert heard[1] == "OH2LNG" and air.truncated == [
            (len(ax25.encode(ui_frame("OH2LNG", b"!6010.00N/02456.00E>" + b"x" * 120))), 123)
        ], "the air cut it, as Mercury does, and the cut frame still decodes"
    finally:
        await tnc.stop()
        await air.aclose()
    logging.getLogger("neoaprs.tnc").info("done")


async def test_a_station_message_another_program_sent_on_the_frequency_is_passed_over_and_the_next_frame_is_heard() -> (
    None
):
    """Mercury hands every station message it hears (packet type 0x07) to its broadcast client under
    KISS command 0x03."""
    air = Air(frame_sec=0.05)
    b = air.station()
    await air.start()
    tnc = Tnc(b.url, profile=MERCURY, check_sec=0.0, backoff=Backoff([0.05, 0.05]), fallback_probe=False)
    heard: list[str] = []
    tnc.packet.connect(lambda p: heard.append(p.source))
    await tnc.start()
    try:
        await b.connected()
        beacon = bytes([0x07 << 5 | 1]) + bytes(range(40))
        b.feed(kiss.encode(beacon, command=3) + kiss.encode(ax25.encode(ui_frame("OH2XYZ"))))
        await until_started(lambda: heard == ["OH2XYZ"])
        assert tnc.stats.rejected == 0 and tnc.stats.packets == 1
        assert any("another program's station message, not APRS: passed over (41 bytes)" in line for line in tnc.lines)
    finally:
        await tnc.stop()
        await air.aclose()


# ---- the shipped program's path: no free pair of ports, an unwritable data folder, a program that
# ignores the request to end (and lists no sound card)


async def test_no_free_pair_of_ports_is_said_and_nothing_is_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def none() -> tuple[int, int]:
        raise OSError("no free pair of ports from 8100 to 8150")

    monkeypatch.setattr(mercurymodem, "free_ports", none)
    m = modem(tmp_path)
    await m.start(HF)
    # The ports are chosen last, after the configuration is written: that file may be there
    assert (
        m.state == "waiting"
        and m.problem == "no free port for Mercury; the log says which were tried"
        and m.starts == 0
    )
    await stopped(m)


async def test_a_data_folder_that_cannot_be_written_is_said_in_the_systems_words(tmp_path: Path) -> None:
    # today's modem, and no such folder: the configuration cannot be written there
    m = modem(tmp_path / "gone", radio=False)
    await m.start(HF)
    assert (
        m.state == "waiting"
        and m.problem.startswith("Mercury's configuration could not be written in the data folder: ")
        and str(tmp_path) not in m.problem
        and m.starts == 0
    )
    await stopped(m)
    (tmp_path / "file").write_text("not a folder")
    m = modem(tmp_path / "file")  # (the radio's folder cannot be made in it)
    await m.start(HF)
    assert (
        m.state == "waiting"
        and m.problem.startswith("Mercury's folder could not be made in the data folder: ")
        and str(tmp_path) not in m.problem
        and m.starts == 0
        and m.held() == []
    )
    await stopped(m)
    m = modem(tmp_path)
    # The folder is there, and the configuration cannot be written in it
    (m.home / INI_FILE).mkdir(parents=True)
    await m.start(HF)
    assert (
        m.state == "waiting"
        and m.problem.startswith("Mercury's configuration could not be written in the data folder: ")
        and str(tmp_path) not in m.problem
        and m.starts == 0
    )
    await stopped(m)


async def test_a_program_that_ignores_the_request_to_end_is_killed_and_one_that_lists_no_sound_card_runs_on_the_default_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mercury is asked to end (SIGTERM) and killed after STOP_WAIT_SEC when it does not; a `-z`
    that lists nothing leaves the sound card the system's default and the keying VOX."""
    monkeypatch.setattr(mercuryhelper, "STOP_WAIT_SEC", 0.2)
    stubborn = [
        sys.executable,
        "-c",
        "import signal, sys, time\nif '-z' in sys.argv: sys.exit(0)\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nprint('up', flush=True)\ntime.sleep(600)",
    ]
    m = Mercury(
        tmp_path, finder=lambda: stubborn, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path)
    )
    m.ports = lambda: []
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    pid = m.pid
    assert pid is not None and _alive(pid) and m.starts == 1 and m.sound_card == "" and m.keying == Keying("vox")
    await m.stop()
    assert not _alive(pid) and m.state == "stopped"


async def test_a_sound_card_the_program_cannot_open_ends_the_program_and_is_the_problem_of_the_modem_and_the_radio_until_a_start_succeeds(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """On a station with two USB sound cards Mercury ran on deaf and mute after `[ERR] [audio-play]
    error in audio->open()`, and the status said "running"."""
    m = Mercury(
        tmp_path,
        finder=lambda: fakemercury.program(audio_error=True),
        backoff=QUICK,
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path),
    )
    m.ports = lambda: []
    seen: list[tuple[str, str]] = []
    m.changed.connect(lambda: seen.append((m.state, m.problem)))
    await m.start(HF)
    tnc = Tnc(
        f"socket://127.0.0.1:{m.broadcast_port}",
        profile=MERCURY,
        check_sec=0.0,
        backoff=Backoff([0.05, 0.05]),
        fallback_probe=False,
    )
    tnc.modem = m
    radio_seen: list[tuple[object, str, bool]] = []
    tnc.changed.connect(lambda: radio_seen.append((tnc.state, tnc.problem, tnc.usable)))
    await tnc.start()
    try:
        first = m.pid
        # The fake prints the error once its ports listen: whether the control line connected first
        # is the machine's business
        await until_started(lambda: m.state == "waiting" and m.problem == SOUND_CARD_FAILED)
        await until_started(lambda: not _alive(first))
        # The problem itself is checked over every change below: the quick back-off may have the
        # next start running by now
        assert m.hold() == "" and "could not open its sound card" in caplog.text
        # The quick back-off may have begun the next start already: the words of the wait are
        # checked while it lasts
        if m.state == "waiting":
            assert m.describe() == f"Mercury DATAC3: {SOUND_CARD_FAILED}"
        # The line went with the program: the radio is not connected, and says why (seen as it changed:
        # the quick back-off may have the radio trying the next start by now)
        await until_started(lambda: (Source.State.WAITING, SOUND_CARD_FAILED, False) in radio_seen)
        # Tried again after the back-off: a card chosen anew is taken then
        await until_started(lambda: m.starts >= 2)
        await until_started(lambda: m.state == "waiting" and m.problem == SOUND_CARD_FAILED and m.starts >= 2)
        after = seen[seen.index(("waiting", SOUND_CARD_FAILED)) :]
        assert all(change == ("waiting", SOUND_CARD_FAILED) or change[0] == "running" for change in after), (
            f"the problem stands through the next start until it is running (never `starting` with no problem between two failures): {after}"
        )
    finally:
        await tnc.stop()
        await stopped(m)


# Mercury 1.9.25 on Windows, after the radio's USB sound card went while it ran (a support file)
LOST_LINES = (
    "[ERR] [audio-cap] capture reopen failed (attempt 1): IMMDevice_Activate: (0x88890004) AUDCLNT_E_DEVICE_INVALIDATED",
    "[ERR] [audio-play] playback reopen failed (attempt 96): IMMDevice_Activate: (0x88890004) AUDCLNT_E_DEVICE_INVALIDATED",
    "[ERR] [audio-cap] the capture device delivers no audio: 2 reopens in a row brought nothing (unplugged, or its USB codec reset?) -- still trying it",
    "[ERR] [audio-play] the playback device takes no audio: 3 reopens in a row brought nothing (unplugged, or its USB codec reset?) -- still trying it",
    "[WRN] [audio-cap] capture device 'Mic (USB Audio CODEC )' ({0.0.1.00000000}.{00000000-0000-0000-0000-000000000000}) is no longer listed: unplugged? -- waiting for it",
)
# what it says on the way, before it knows: a reopen that may well work
NOT_LOST = (
    "[WRN] [audio-cap] capture stalled 2000 ms, reopening device (reopen #1)",
    "[WRN] [audio-play] playback took no audio for 1016 ms, reopening device (reopen #1)",
    "[ERR] [audio-cap] ffaudio.read: IAudioCaptureClient_GetBuffer: (0x88890004) AUDCLNT_E_DEVICE_INVALIDATED (error 1)",
    "[WRN] [audio-cap] Buffer full in capture buffer!",
)


def test_the_lines_of_a_sound_card_gone_while_mercury_runs_are_known_and_a_reopen_on_the_way_is_not() -> None:
    stamp = "2026-11-24 16:44:47.187 [+1034.694s] "
    assert all(mercuryhelper.audio_lost(stamp + line) for line in LOST_LINES)
    assert not any(mercuryhelper.audio_lost(stamp + line) for line in NOT_LOST)
    assert fakemercury.AUDIO_LOST_LINE in LOST_LINES


@pytest.mark.slow("runs made-up Mercury modems on the loopback with real time on the air")
async def test_a_sound_card_gone_while_mercury_runs_ends_the_run_and_is_the_radios_problem_until_it_starts_again(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Mercury keeps trying a card that went, deaf and mute, while the page said connected and beacons
    were counted as sent."""
    m = Mercury(
        tmp_path,
        finder=lambda: fakemercury.program(audio_lost=True),
        # (the radio's problem shows from the end of the run to the start of the next: a back-off
        # wide enough to be seen on a busy runner)
        backoff=Backoff([2.0, 2.0]),
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path),
    )
    m.ports = lambda: []
    await m.start(HF)
    tnc = Tnc(
        f"socket://127.0.0.1:{m.broadcast_port}",
        profile=MERCURY,
        check_sec=0.0,
        backoff=Backoff([0.05, 0.05]),
        fallback_probe=False,
    )
    tnc.modem = m
    await tnc.start()
    try:
        first = m.pid
        await until_started(lambda: m.reason == "sound_card" and m.problem == SOUND_CARD_FAILED)
        assert "lost its sound card" in caplog.text
        seen: set[tuple[str, bool]] = set()
        await until_started(lambda: seen.add((tnc.problem, tnc.usable)) or (SOUND_CARD_FAILED, False) in seen)
        await until_started(lambda: not _alive(first))
        await until_started(lambda: m.starts >= 2)
    finally:
        await tnc.stop()
        await stopped(m)


# ---- the ports across a relaunch (the HF Tnc waits on its given port, so a restarted program is
# where the dead one was), and where the program listens


def test_a_port_whose_last_connection_is_in_time_wait_counts_as_free_as_it_does_for_mercury() -> None:
    """The HF Tnc's line to a Mercury that died leaves the port in TIME_WAIT; a probe that called
    that busy made the relaunch take the next pair, which the Tnc never learnt. Mercury binds with
    SO_REUSEADDR, so the pair is free for it."""
    if sys.platform == "win32":
        pytest.skip(
            "Windows lets a bind through a TIME_WAIT without the option, and the option there means something else"
        )
    with socket.socket() as server:
        # As Mercury's listener does, tcp_interfaces.c; the connections it accepts inherit it, and
        # Linux lets a bind through their TIME_WAIT only then
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port)) as client:
            conn, _ = server.accept()
            # The side that closes first is the one left in TIME_WAIT: the server's, on `port`
            conn.close()
            client.recv(1)
    assert mercuryhelper._free(port), "a port with nothing but a TIME_WAIT on it is free"
    with socket.socket() as holder:
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        holder.bind(("127.0.0.1", port))
        holder.listen()
        assert not mercuryhelper._free(port), "a port something listens on is not"


def test_a_port_another_program_listens_on_in_ipv6_alone_is_not_free_so_our_modem_is_never_taken_for_one_open_to_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The listeners of a started modem are read in both families: a pair chosen beside another
    program's IPv6 listener would make our own modem look as if it listened on the network."""
    if not socket.has_ipv6:
        pytest.skip("no IPv6 here")
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as other:
        other.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        other.bind(("::", 0))
        other.listen()
        port = other.getsockname()[1]
        assert not mercuryhelper._free(port)
        # A system without the kernel's table: the probe of :: says it
        monkeypatch.setattr(childprogram, "PROC_TCP", ())
        assert not mercuryhelper._free(port)
    assert mercuryhelper._free(port)


async def tnc_on(m: Mercury) -> Tnc:
    tnc = Tnc(
        f"socket://127.0.0.1:{m.broadcast_port}",
        profile=MERCURY,
        check_sec=0.0,
        backoff=Backoff([0.05, 0.1]),
        fallback_probe=False,
    )
    tnc.modem = m
    await tnc.start()
    return tnc


async def test_a_program_that_dies_is_started_again_on_the_same_ports_and_the_tnc_that_waited_on_them_connects_again(
    tmp_path: Path,
) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    await until_started(lambda: m.state == "running")
    ports, pid = (m.broadcast_port, m.control_port), m.pid
    tnc = await tnc_on(m)
    try:
        await until_started(lambda: tnc.usable)
        assert m._program._process is not None
        # A sound device unplugged: Mercury is gone without a word
        m._program._process.kill()
        await until_started(lambda: m.state == "waiting" and not tnc.usable)
        assert tnc.state is not Source.State.CONNECTED and "Mercury stopped" in m.problem, (
            "meanwhile the status is the truth: the modem is down and the radio is not connected"
        )
        await until_started(lambda: m.starts == 2 and m.running)
        assert (m.broadcast_port, m.control_port) == ports and m.pid != pid, "the same pair, where the Tnc waits"
        await until_started(lambda: tnc.usable)
        assert tnc.port == f"socket://127.0.0.1:{ports[0]}"
    finally:
        await tnc.stop()
        await stopped(m)


@pytest.mark.slow("runs made-up Mercury modems on the loopback with real time on the air")
async def test_a_pair_taken_while_the_program_was_down_gives_another_and_the_owner_is_told_to_point_the_tnc_at_it(
    tmp_path: Path,
) -> None:
    # The back-off is the time the test has to take the port: a machine that stalls for a second
    # does not end it
    m = Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=Backoff([4.0, 4.0]),
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path),
    )
    m.ports = lambda: []
    told: list[int] = []
    m.ports_changed.connect(lambda: told.append(m.broadcast_port))
    await m.start(HF)
    await until_started(lambda: m.state == "running")
    old = m.broadcast_port
    assert m._program._process is not None
    m._program._process.kill()
    await until_started(lambda: m.state == "waiting")
    # Another program takes the KISS port in the second the back-off waits
    with socket.socket() as holder:
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        holder.bind(("127.0.0.1", old))
        holder.listen()
        try:
            await until_started(lambda: m.starts == 2 and m.running)
            assert m.broadcast_port != old and m.control_port == m.broadcast_port + CONTROL_OFFSET
            assert told == [m.broadcast_port], "told once, after the new pair was chosen"
            assert [c.value for c in m.held() if c.kind == "modem_ports"] == [str(m.broadcast_port)], (
                "the radio holds the new pair in the place of the old"
            )
        finally:
            await stopped(m)


def test_the_listeners_of_the_kernels_table_are_read_by_port_and_the_loopback_ones_are_nobodys_concern() -> None:
    tcp = (
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 0100007F:1FA4 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1 0000000000000000 100 0 0 10 0\n"
        "   1: 00000000:206C 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1 0000000000000000 100 0 0 10 0\n"
        # 8301 ESTABLISHED: not a listener
        "   2: 0100007F:206D 0100007F:B2E4 01 00000000:00000000 00:00000000 00000000  1000        0 1 0000000000000000 100 0 0 10 0\n"
        "   3: 0100007F:1F41 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1 0000000000000000 100 0 0 10 0\n"
    )  # 8001: not asked about
    tcp6 = (
        "  sl  local_address                         remote_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 00000000000000000000000000000000:206D 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1 0000000000000000 100 0 0 10 0\n"
        "   1: 00000000000000000000000001000000:1FA4 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1 0000000000000000 100 0 0 10 0\n"
    )
    found = mercuryhelper._listeners((tcp, tcp6), (8100, 8300, 8301))
    assert found == {
        8100: {"0100007F", "00000000000000000000000001000000"},
        8300: {"00000000"},
        8301: {"00000000000000000000000000000000"},
    }
    foreign = [f"{a}:{p}" for p, s in sorted(found.items()) for a in sorted(s) if a not in mercuryhelper.LOOPBACK_HEX]
    assert foreign == ["00000000:8300", "00000000000000000000000000000000:8301"], (
        "the IPv4 and the IPv6 loopback are ours; INADDR_ANY and :: are the LAN's"
    )
    assert mercuryhelper._listeners((tcp,), ()) == {} and mercuryhelper._listeners((), (8100,)) == {}


async def test_the_fake_program_listens_on_the_loopback_and_one_that_listens_on_the_network_is_ended_and_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "running")
        assert mercuryhelper.foreign_listeners((m.broadcast_port, m.control_port)) == [], (
            "the fake binds 127.0.0.1, as the shipped program does"
        )
    finally:
        await stopped(m)
    # A Mercury that is not the shipped one: INADDR_ANY
    monkeypatch.setattr(mercurymodem, "foreign_listeners", lambda ports: [f"00000000:{p}" for p in ports])
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "waiting")
        pid = m.pid
        assert m.problem == mercurymodem.OPEN_TO_NETWORK and m.starts == 1
        await until_started(lambda: not _alive(pid))
        # The back-off of a program that died is 0.1 s: a relaunch would have come
        await asyncio.sleep(0.5)
        assert m.starts == 1 and m.state == "waiting", "ended, and not started again"
        assert m.describe() == f"Mercury DATAC3: {mercurymodem.OPEN_TO_NETWORK}"
    finally:
        await stopped(m)


# ---- a failed launch that is retried, the ports left alone, the speaker without pipes, the order


async def test_a_launch_that_fails_for_a_reason_that_may_pass_is_tried_again_after_the_back_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        await until_started(lambda: m.running)
        assert m.starts == 1 and len(calls) == 2, "the second try, after the back-off, had its pair"
    finally:
        await stopped(m)


async def test_the_fm_radios_the_gpss_the_skipped_and_another_radios_ports_are_never_chosen_to_key_the_radio(
    tmp_path: Path,
) -> None:
    m = modem(tmp_path)
    m.ports = lambda: [SerialPort("/dev/ttyUSB0", 0x10C4, 0xEA60), SerialPort("/dev/ttyUSB1", 0x10C4, 0xEA60)]
    await m.start(replace(HF, mercury_sound_card="", mercury_keying="", serial_port="/dev/ttyUSB0"))
    try:
        await until_started(lambda: m.running)
        assert m.keying == Keying("rts", "/dev/ttyUSB1"), "the FM radio's port is not the one"
    finally:
        await m.stop()
    await m.start(
        replace(HF, mercury_sound_card="", mercury_keying="", gps_device="/dev/ttyUSB1", serial_skip="/dev/ttyUSB0")
    )
    try:
        await until_started(lambda: m.running)
        assert m.keying == Keying("vox"), "the GPS's port and a skipped port leave no serial port: VOX"
    finally:
        await m.stop()
    assert m.claims is not None
    m.claims.hold(Claim("serial", claim_value("/dev/ttyUSB0"), 3))
    m.claims.hold(Claim("gps", claim_value("/dev/ttyUSB1"), None))
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    try:
        await until_started(lambda: m.running)
        assert m.keying == Keying("vox"), (
            "another radio's port and the port the GPS receiver holds in the station's table leave no serial port: VOX"
        )
    finally:
        await stopped(m)


def test_a_card_a_setting_names_by_its_number_is_held_by_its_name_so_that_another_radio_leaves_it_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A setting that names the card by its number (`plughw:1,0`) or by its name is one claim on one
    card."""
    card1 = tmp_path / "asound" / "card1"
    card1.mkdir(parents=True)
    (card1 / "id").write_text("CODEC\n")
    monkeypatch.setenv("NEOAPRS_ALSA_ROOT", str(tmp_path / "asound"))
    claims = Claims()
    two, five = Mercury(tmp_path, **of_radio(tmp_path, 2, claims)), Mercury(tmp_path, **of_radio(tmp_path, 5, claims))
    assert two._hold_setup("plughw:1,0", None) is None and claims.all() == (
        Claim("sound_card", "plughw:CARD=CODEC,DEV=0", 2),
    )
    cards = [
        SoundCard("plughw:CARD=CODEC,DEV=0", "USB Audio CODEC", True, True, True, "plughw:1,0"),
        SoundCard("plughw:CARD=Device,DEV=0", "USB Audio Device", True, True, False, "plughw:2,0"),
    ]
    assert proposal(cards, [], DEFAULTS, claims=claims, holder=5)[0] != "plughw:CARD=CODEC,DEV=0", (
        "radio 2's card is proposed to no other radio"
    )
    assert five._hold_setup("plughw:CARD=CODEC,DEV=0", None) == Claim("sound_card", "plughw:CARD=CODEC,DEV=0", 2), (
        "the same card by its name is radio 2's"
    )
    assert five._hold_setup("plughw:2,0", None) is None and Claim("sound_card", "plughw:2,0", 5) in claims.all(), (
        "a card ALSA does not know by a name is held as it is named"
    )


def test_the_page_is_proposed_the_card_and_the_keying_the_daemon_would_choose_and_the_ports_of_the_other_radios_key_nothing() -> (
    None
):
    cards = [
        SoundCard("plughw:1,0", "USB AUDIO  CODEC USB Audio", True, True, False),
        SoundCard("plughw:0,0", "HDA Intel PCH", True, True, True),
    ]
    usb = [PortInfo("/dev/ttyUSB0", "CP2102", "USB VID:PID=10C4:EA60", 0x10C4, 0xEA60)]
    assert proposal(cards, usb, DEFAULTS) == ("plughw:1,0", "rts:/dev/ttyUSB0")
    assert proposal(cards, usb, replace(DEFAULTS, serial_port="/dev/ttyUSB0")) == ("plughw:1,0", "vox"), (
        "the FM radio's port keys no HF radio"
    )
    assert proposal(cards[1:], usb, DEFAULTS) == ("plughw:0,0", "vox"), (
        "the system's default device, named, and no radio's sound card to key a line by"
    )
    assert proposal([], usb, DEFAULTS) == ("", "")
    claims = Claims()
    claims.hold(Claim("serial", claim_value("/dev/ttyUSB0"), 1))
    claims.hold(Claim("sound_card", "plughw:1,0", 5))
    assert proposal(cards, usb, DEFAULTS, claims=claims, holder=HF_ID) == ("plughw:0,0", "vox"), (
        "what other radios hold in the station's table is proposed to none: another radio's card, the FM radio's port"
    )
    assert proposal(cards, usb, DEFAULTS, claims=claims, holder=5) == ("plughw:1,0", "vox"), (
        "a radio's own card is its to be proposed"
    )


async def test_the_stale_program_is_ended_before_the_sound_cards_are_listed_and_the_ports_are_chosen_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    real_free, real_stale, real_cards = mercurymodem.free_ports, mercurymodem.end_stale, mercuryhelper.list_sound_cards
    monkeypatch.setattr(mercurymodem, "free_ports", lambda: (order.append("ports"), real_free())[1])
    monkeypatch.setattr(
        mercurymodem,
        "end_stale",
        lambda pid_file, ini, program: (order.append("stale"), real_stale(pid_file, ini, program))[1],
    )
    monkeypatch.setattr(
        mercuryhelper,
        "list_sound_cards",
        lambda command, timeout_sec=15.0: (order.append("cards"), real_cards(command, timeout_sec))[1],
    )
    m = modem(tmp_path)
    await m.start(replace(HF, mercury_sound_card="", mercury_keying=""))
    try:
        await until_started(lambda: m.running)
        assert order == ["stale", "cards", "ports"], (
            "a program left behind holds the ports: ended first; the pair chosen after the seconds mercury -z takes, so that nobody takes it meanwhile"
        )
    finally:
        await stopped(m)


async def test_without_named_pipes_the_speaker_of_the_dummy_hf_radio_is_not_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A Mercury started on the system's default devices for real would play DATAC3 out of the
    speakers' output and open the microphone, which "nothing goes on the air" does not allow (a VOX
    radio on the default output would key)."""
    caplog.set_level(logging.INFO, "neoaprs.mercury")
    monkeypatch.setattr(mercurymodem.SpeakerAudio, "prepare", lambda self: False)
    m = modem(tmp_path)
    await m.start(HF, speaker=True)
    assert m.state == "stopped" and m.starts == 0 and "no named pipes" in caplog.text
    await stopped(m)


@pytest.mark.skipif(
    sys.platform == "win32", reason="the shipped program here is a shell script that stands in for mercury.exe"
)
async def test_the_shipped_program_is_started_with_no_question_asked_of_the_system_and_is_said_to_be_the_shipped_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The Mercury NeoAPRS ships binds the loopback on every system, so it is started at once: no
    PowerShell and no netsh are run for it, whatever the system (the Windows installer's firewall
    rule and the daemon's check of the firewall are gone); the log says the program is the shipped
    one, and that a program named by its path elsewhere is not."""
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
    assert (
        mercuryhelper.is_shipped([str(shipped)])
        and not mercuryhelper.is_shipped([str(tmp_path / "mercury.exe")])
        and not mercuryhelper.is_shipped(fakemercury.program())
    )
    caplog.set_level(logging.INFO, "neoaprs.mercury")
    m = Mercury(
        tmp_path,
        finder=lambda: [str(shipped)],
        backoff=QUICK,
        control_backoff=Backoff([0.05, 0.05]),
        **of_radio(tmp_path),
    )
    m.ports = lambda: []  # (never the operator's serial ports)
    await m.start(HF)
    try:
        await until_started(lambda: m.running)
        assert m.starts == 1 and m.reason == "" and "(not the one NeoAPRS ships)" not in caplog.text
        assert not [call for call in asked if "powershell" in call.lower() or "netsh" in call.lower()], asked
    finally:
        await stopped(m)
    # A program named by its path elsewhere: said not to be the shipped one; what it is said to be
    # is the system's words
    m = Mercury(tmp_path, finder=lambda: [str(tmp_path / "not-there")], backoff=QUICK, **of_radio(tmp_path))
    await m.start(HF)
    assert m.reason == "not_started" and "(not the one NeoAPRS ships)" in caplog.text
    await stopped(m)


def test_a_warning_the_program_repeats_is_in_the_log_the_first_tenth_and_hundredth_time(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.mercury.program")
    program = mercuryhelper.Program(lambda code, lines: None)
    # Each with the time Mercury wrote in front of it, in each of its forms, and none.
    for n in range(250):
        stamp = (
            f"22:16:{n % 60:02d}.{n:03d} [+{n}.003s] ",
            f"2026-11-13 22:16:{n % 60:02d}.{n:03d} [+{n}.003s] ",
            f"2026-11-13 20:16:{n % 60:02d}.{n:03d}Z [+{n}.003s] ",
            "",
        )[n % 4]
        program._tell(stamp + "[WRN] [audio] snd_pcm_readi: Input/output error")
    program._tell("[INF] [engine] Mercury engine initialised")
    said = [r for r in caplog.records if r.name == "neoaprs.mercury.program"]
    assert [r.levelno for r in said if "snd_pcm" in r.getMessage()] == [logging.INFO] * 3, (
        "the 1st, the 10th and the 100th; the 1000th would be next"
    )
    assert "(the 100th time)" in said[2].getMessage() and said[-1].levelno == logging.DEBUG


async def test_a_line_refused_while_mercury_is_starting_says_nothing_in_the_terminal_or_the_log_above_debug_and_is_said_once_the_start_time_is_over(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    m = modem(tmp_path, program=False)
    m._set("starting", "")
    tnc = Tnc(
        f"socket://127.0.0.1:{free_ports(18200, 5)[0]}",
        profile=MERCURY,
        check_sec=0.0,
        backoff=Backoff([30.0]),
        fallback_probe=False,
    )
    tnc.modem = m
    caplog.set_level(logging.DEBUG)
    await tnc.start()
    try:
        assert tnc.state is Source.State.WAITING and tnc.problem == f"waiting for {m.describe()}"
        assert not any("trying again" in line for line in tnc.lines) and not [
            r for r in caplog.records if r.levelno >= logging.WARNING and "trying again" in r.getMessage()
        ]
        m._starting_since -= modemstate.START_SEC + 1
        assert not m.starting()
        await tnc.start()
        assert any("trying again in 30 s" in line for line in tnc.lines) and any(
            r.levelno == logging.WARNING and "trying again" in r.getMessage() for r in caplog.records
        ), "a modem that is still not there after its start time is a fault"
    finally:
        await tnc.stop()


def test_the_sound_cards_mercury_lists_are_read_as_utf_8_whatever_the_locale() -> None:
    """Windows' locale (cp1252) made 'MicrÃ³fono (Logi C525 HD WebCam)' of a support report."""
    script = (
        "import sys; sys.stdout.buffer.write(\"capture devices:\\ndevice: name: 'Micrófono (Logi C525 HD WebCam)'"
        "  id: '{0.0.1.00000000}.{b97fd3c9}'\\n\".encode('utf-8'))"
    )
    assert [c.name for c in list_sound_cards([sys.executable, "-c", script])] == ["Micrófono (Logi C525 HD WebCam)"]


async def test_on_windows_mercurys_own_log_goes_into_the_radios_folder_not_the_install_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An install for all users cannot write its own folder, where Mercury logs without -L."""
    m = modem(tmp_path)
    started: list[list[str]] = []
    monkeypatch.setattr(mercurymodem, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(m._program, "start", lambda argv, cwd, pid_file=None: started.append(argv))
    try:
        await m.start(HF)
        await until_started(lambda: started)
        assert started[0][-2:] == ["-L", str(m.home / mercurymodem.ENGINE_LOG)]
    finally:
        await stopped(m)


def test_a_program_on_a_sound_servers_device_runs_on_the_systems_alsa_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The system's plug-in of the sound server is built for the system's libasound (Fedora's needs
    ALSA_1.2.15, newer than the shipped one, measured): such a run takes the system's library and its
    configuration, the shipped one stays for a card."""
    program = tmp_path / "mercury" / "mercury"
    (tmp_path / "mercury" / "share" / "alsa").mkdir(parents=True)
    program.write_text("")
    (tmp_path / "mercury" / "share" / "alsa" / "alsa.conf").write_text("")
    system = soundserver.SystemAlsa(tmp_path / "lib64", tmp_path / "share" / "alsa.conf")
    monkeypatch.setattr(soundserver, "system_alsa", lambda: system)
    env = environment([str(program)], system_sound=True)
    # (one file: openSUSE's ALSA reads no list of them; ours includes the system's alsa.conf first)
    assert env["LD_LIBRARY_PATH"] == str(system.lib) and env["ALSA_CONFIG_PATH"] == str(soundserver.CONF)
    card = environment([str(program)])
    assert "LD_LIBRARY_PATH" not in card and card["ALSA_CONFIG_PATH"] == str(
        tmp_path / "mercury" / "share" / "alsa" / "alsa.conf"
    )
    monkeypatch.setattr(soundserver, "system_alsa", lambda: None)
    assert "LD_LIBRARY_PATH" not in environment([str(program)], system_sound=True), "none found: the shipped one"
