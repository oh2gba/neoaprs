"""Direwolf as a part of the daemon (neoaprs/direwolfmodem.py, neoaprs/direwolftune.py, neoaprs/direwolfprogram.py), against the made-up Direwolf of tests/support/fakedirewolf.py: the configuration written in the
radio's own folder and the command line, the card, the keying and the KISS port held in the station's table, running once Direwolf says it listens, the keying, the carrier and the level of the packets heard,
the stop by its own clean way (its input closed, then SIGINT, then the kill), a sound card, a keying device or a port that cannot be had (the reason the page puts in its words, and the start again after the
back-off), a program that dies, one that listens on the network, a run of ours left behind, Tune and the keying test as Direwolf's own calibration runs on the same port, the transmit level, the Windows checks of
the WinMM devices and of several CM108 chips, and the sound card as one resource of the station: two radios on two cards side by side, a third and the HF modem refused on a card that is held, with the holder."""
import asyncio
import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs import childprogram, direwolfmodem, direwolfprogram, direwolftune, serialholders, winmm
from neoaprs.claims import Claim, Claims
from neoaprs.coded import CodedError
from neoaprs.direwolf import CONF_FILE, PID_FILE, adevice
from neoaprs.direwolfmodem import KEYING_FAILED, NOT_INSTALLED, OPEN_TO_NETWORK, SEVERAL_CM108, SOUND_CARD_FAILED, SOUND_CARD_NOT_FOUND, DirewolfModem, proposal
from neoaprs.direwolftune import TRANSMITTING
from neoaprs.mercury import Keying, SerialPort, SoundCard
from neoaprs.mercuryclaims import radio_folder
from neoaprs.mercurymodem import Mercury
from neoaprs.radiotype import HF_ID
from neoaprs.serialprobe import PortInfo, claim_value
from neoaprs.source import Backoff
from tests.support import fakedirewolf, fakemercury
from tests.support.env import until, until_started
from tests.support.fakemercury import of_radio
from tests.support.modemports import base_of_this_test, own_ports
from tests.support.radioconfig import with_radio
from tests.test_mercury_modem import HF

QUICK = Backoff([0.1, 0.1])
CARD = "plughw:1,0"                       # what the made-up Mercury lists for `-z` (tests/support/fakemercury.py SOUND_CARDS)
WINMM_NUMBERS_OF = direwolfmodem._numbers_of


def port(device: str) -> str:
    """The value the station's table holds for this port (a COM port's case aside on Windows: `/dev/ttyUSB7` is `/DEV/TTYUSB7` there)."""
    return claim_value(device) or device


@pytest.fixture(autouse=True)
def _winmm_numbers_of_the_made_up_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    """On Windows the modem runs the Windows way, as an operator's does: every made-up card is the second input and output of the made-up Direwolf's WinMM lists, which the machine's own devices never name.
    The finding of the numbers itself is the test of `windows_modem`, on both systems."""
    monkeypatch.setattr(direwolfmodem, "_numbers_of", lambda name: (1, 1))


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """The KISS ports from this test's own base, so that tests side by side never take one port between the probe and the bind (tests/support/modemports.py); the Mercury modem's pairs above them."""
    monkeypatch.setattr(direwolfmodem, "FIRST_PORT", base_of_this_test())
    own_ports(monkeypatch)


def modem(tmp_path: Path, *modes: str, claims: Claims | None = None, holder: int = 3, die_after_sec: float | None = None, level: int | None = None, busy_sec: float | None = None) -> DirewolfModem:
    m = DirewolfModem(radio_folder(tmp_path, holder), finder=lambda: fakedirewolf.program(*modes, die_after_sec=die_after_sec, level=level, busy_sec=busy_sec), backoff=QUICK,
                      claims=claims if claims is not None else Claims(), holder=holder, lister=fakemercury.program)
    m.ports = lambda: []
    return m


async def running(m: DirewolfModem) -> None:
    await until_started(lambda: m.state == "running")


async def kiss_send(port: int, frame: bytes) -> bytes:
    """A frame written to the KISS port as a client does; what comes back."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(frame)
    await writer.drain()
    back = await asyncio.wait_for(reader.read(4096), 10)
    writer.close()
    return back


def _alive(pid: int | None) -> bool:
    """Whether the process of this id still runs (a child that ended and was waited for is gone; on Windows asked of its exit code: os.kill(pid, 0) there is a console's Ctrl+C, not a question)."""
    return pid is not None and not childprogram.gone(pid)


async def test_direwolf_is_started_in_the_radios_folder_with_its_configuration_holds_what_it_runs_on_and_ends_cleanly_when_its_input_closes(tmp_path: Path) -> None:
    claims = Claims()
    m = modem(tmp_path, claims=claims)
    await m.start(CARD, "rts:/dev/ttyUSB7", -6)
    await running(m)
    home = radio_folder(tmp_path, 3)
    assert (home / CONF_FILE).read_text(encoding="utf-8") == (f"# written by NeoAPRS at every start\nADEVICE {adevice(CARD, m._numbers)}\nACHANNELS 1\nCHANNEL 0\nMODEM 1200\nPTT /dev/ttyUSB7 RTS\n"
                                                              f"KISSPORT 0\nKISSPORT {m.kiss_port}\nAGWPORT 0\nDNSSD 0\n")
    assert fakedirewolf.runs(home)[-1][-12:] == ["-c", str(home / CONF_FILE), "-t", "0", "-q", "d", "-a", "60", "-d", "on", "-Q", "-G", "50"][-12:]
    assert set(m.held()) == {Claim("sound_card", CARD, 3), Claim("keying", port("/dev/ttyUSB7"), 3), Claim("modem_ports", str(m.kiss_port), 3)}
    assert (home / PID_FILE).read_text(encoding="ascii") == str(m.pid) and m.describe() == "Direwolf AFSK1200, listening" and m.starts == 1
    pid = m.pid
    await m.stop()
    assert not _alive(pid) and m.state == "stopped" and claims.all() == () and not (home / PID_FILE).exists()


async def test_a_frame_given_to_its_kiss_port_keys_the_radio_and_a_frame_heard_tells_its_level_and_the_carrier(tmp_path: Path) -> None:
    m = modem(tmp_path, level=72)
    told: list[tuple[bool, bool, int | None]] = []
    m.changed.connect(lambda: told.append((m.keyed, m.busy, m.rx_level)))
    await m.start(CARD, "vox", 0)
    await running(m)
    assert m.rx_level is None and m.wire()["rx_level"] is None, "no level before a packet is heard"
    assert await kiss_send(m.kiss_port, b"\xc0\x00frame\xc0") == b"\xc0\x00frame\xc0"
    await until(lambda: m.rx_level == 72 and not m.busy)
    assert (True, False, None) in told and (False, True, None) in told and m.frames_keyed == 1
    wire = m.wire()
    assert (wire["mode"], wire["max_frame"], wire["rx_level"], wire["keying"], wire["sound_card"], wire["scope"], wire["frequencies"]) == ("AFSK1200", None, 72, "vox", CARD, False, [])
    await m.stop()


@pytest.mark.parametrize(("mode", "problem", "reason"), [("--fail-card", SOUND_CARD_FAILED, "sound_card"), ("--fail-keying", KEYING_FAILED, "keying")])
async def test_a_sound_card_or_a_keying_device_that_cannot_be_opened_is_the_reason_the_page_says_and_it_is_started_again(tmp_path: Path, mode: str, problem: str, reason: str) -> None:
    m = modem(tmp_path, mode)
    await m.start(CARD, "rts:/dev/ttyUSB7", 0)
    await until_started(lambda: m.starts >= 2)
    assert (m.state, m.problem, m.reason) == ("waiting", problem, reason) and m.describe() == f"Direwolf AFSK1200: {problem}"
    await m.stop()


async def test_a_kiss_port_taken_by_another_program_gives_another_port_and_the_line_is_pointed_at_it(tmp_path: Path) -> None:
    m = modem(tmp_path, "--port-taken")
    moved: list[int] = []
    m.ports_changed.connect(lambda: moved.append(m.kiss_port))
    blocker = await asyncio.start_server(lambda r, w: None, "127.0.0.1", base_of_this_test())             # (the first port is someone else's)
    try:
        await m.start(CARD, "vox", 0)
        first = m.kiss_port
        await until_started(lambda: m.reason == "no_port")
        await until_started(lambda: m.starts >= 2)
        assert m.kiss_port != base_of_this_test() and first != base_of_this_test(), "the probe passes over the port that is taken"
    finally:
        blocker.close()
        await m.stop()


async def test_a_direwolf_that_dies_is_started_again_after_the_back_off(tmp_path: Path) -> None:
    m = modem(tmp_path, die_after_sec=0.3)
    await m.start(CARD, "vox", 0)
    await running(m)
    port = m.kiss_port
    await until_started(lambda: m.reason == "stopped")
    await until_started(lambda: m.starts >= 2)
    assert m.kiss_port == port, "the port is kept for the program started in the place of the one that died"
    await m.stop()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no SIGINT to send: the tree is ended there")
@pytest.mark.parametrize("modes", [("--ignore-stdin",), ("--ignore-stdin", "--ignore-sigint")])
async def test_a_direwolf_that_does_not_end_at_the_end_of_its_input_is_sent_sigint_and_then_killed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, modes: tuple[str, ...]) -> None:
    monkeypatch.setattr("neoaprs.direwolfprogram.STOP_WAIT_SEC", 0.3)
    m = modem(tmp_path, *modes)
    await m.start(CARD, "vox", 0)
    await running(m)
    pid = m.pid
    await m.stop()
    assert not _alive(pid) and m.state == "stopped"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the kernel's table of sockets is Linux's")
async def test_a_direwolf_that_listens_on_the_network_is_ended_and_not_run_again(tmp_path: Path) -> None:
    m = modem(tmp_path, "--listen-any")
    await m.start(CARD, "vox", 0)
    await until_started(lambda: m.reason == "network")
    await asyncio.sleep(0.4)
    assert (m.state, m.problem, m.starts) == ("waiting", OPEN_TO_NETWORK, 1)
    await m.stop()


def _left_running(conf: Path, cwd: Path) -> "subprocess.Popen[str]":
    """A Direwolf (the made-up one, "direwolf" in its command line as the real one has) of the configuration `conf`, keyed by its calibration run, up and with its SIGINT handler."""
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text("ADEVICE x\nKISSPORT 0\n", encoding="utf-8")
    left = subprocess.Popen([*fakedirewolf.program("--ignore-stdin"), "-x", "p", "-c", str(conf)], cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert left.stdout is not None
    left.stdout.readline()                                            # (its banner: it is up, its SIGINT handler with it)
    return left


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="a process's command line is read from /proc")
async def test_a_direwolf_of_ours_left_behind_by_an_earlier_daemon_is_ended_before_the_start_and_an_operators_own_is_left_alone(tmp_path: Path) -> None:
    home = radio_folder(tmp_path, 3)
    own = await asyncio.to_thread(_left_running, tmp_path / "own" / CONF_FILE, tmp_path / "own")       # (the operator's own Direwolf, whose process id a pid file of ours left by a crash came to name)
    ours = await asyncio.to_thread(_left_running, home / CONF_FILE, home)
    try:
        (home / PID_FILE).write_text(str(own.pid), encoding="ascii")
        m = modem(tmp_path)
        await m.start(CARD, "vox", 0)
        await running(m)
        await m.stop()
        assert own.poll() is None, "a Direwolf of another configuration is not ours: it is not interrupted"
        (home / PID_FILE).write_text(str(ours.pid), encoding="ascii")
        await m.start(CARD, "vox", 0)
        await running(m)
        assert await asyncio.to_thread(ours.wait, 10) == 0, "ours (`-c` names the radio's configuration) is ended by SIGINT, its clean end"
        await m.stop()
    finally:
        for left in (own, ours):
            if left.poll() is None:
                left.kill()
                left.wait()


def test_the_shipped_program_works_in_its_own_folder_and_only_a_run_of_ours_is_taken_for_one(tmp_path: Path) -> None:
    home, shipped = tmp_path / "radios" / "3", tmp_path / "tools" / "direwolf" / "direwolf"
    assert direwolfprogram.working_folder([str(shipped)], home) == shipped.parent, "its data files are found there before a system Direwolf's"
    assert direwolfprogram.working_folder(fakedirewolf.program(), home) == home, "the tests' fake (an interpreter and a module) works in the radio's folder"
    assert not direwolfprogram.is_ours(os.getpid(), home / CONF_FILE), "a process whose command line names no configuration of the radio's"
    assert direwolfprogram.is_shipped_image(str(direwolfprogram.expected_program(tmp_path / "tools")), tmp_path / "tools"), "Windows: the shipped program file, by its full path"
    assert not direwolfprogram.is_shipped_image(r"C:\Program Files\direwolf\direwolf.exe", tmp_path / "tools") and not direwolfprogram.is_shipped_image(None)


NO_SUCH_PID = 2**22 + 777                 # (above Linux's largest process id: no /proc entry, so the Windows questions are the ones asked)


@pytest.mark.parametrize(("running", "image", "made_ago_sec", "ended"), [
    (True, "shipped", 5.0, True),
    (True, "shipped", -60.0, False),                                   # another radio's Direwolf that got the id after the file was written (a reboot)
    (True, "shipped", None, False),                                    # a time that cannot be read ends nothing
    (True, r"C:\Program Files\direwolf\direwolf.exe", 5.0, False),     # the operator's own Direwolf
    (False, "shipped", 5.0, False),
])
def test_on_windows_a_run_left_behind_is_ended_only_while_its_id_is_still_the_shipped_direwolf_made_before_its_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, running: bool, image: str,
                                                                                                                      made_ago_sec: float | None, ended: bool) -> None:
    shipped = direwolfprogram.expected_program(tmp_path / "tools")
    pid_file, written = radio_folder(tmp_path, 3) / PID_FILE, 1_800_000_000.0
    pid_file.parent.mkdir(parents=True)
    pid_file.write_text(str(NO_SUCH_PID), encoding="ascii")
    os.utime(pid_file, (written, written))
    kills: list[tuple[int, int]] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(direwolfprogram, "expected_program", lambda tools=None: shipped)
    monkeypatch.setattr(childprogram, "_running_windows", lambda pid: running and not kills)
    monkeypatch.setattr(childprogram, "_windows_image", lambda pid: str(shipped) if image == "shipped" else image)
    monkeypatch.setattr(childprogram, "windows_created", lambda pid: None if made_ago_sec is None else written - made_ago_sec)
    monkeypatch.setattr(os, "kill", lambda pid, sig: kills.append((pid, sig)))
    assert direwolfprogram.end_stale(pid_file) is ended and not pid_file.exists(), "the file is consumed whatever it names"
    assert kills == ([(NO_SUCH_PID, signal.SIGTERM)] if ended else [])


async def test_a_run_that_ends_by_itself_leaves_no_process_id_for_the_next_start_to_end(tmp_path: Path) -> None:
    """The system may give the id to another program (another radio's Direwolf) before the run is started again after the back-off: the file goes with the run."""
    home = radio_folder(tmp_path, 3)
    home.mkdir(parents=True)
    (home / CONF_FILE).write_text("ADEVICE x\nKISSPORT 0\n", encoding="utf-8")
    ended: list[int | None] = []
    program = direwolfprogram.Program(lambda code, lines: ended.append(code))
    program.start([*fakedirewolf.program(die_after_sec=0.2), "-x", "p", "-c", str(home / CONF_FILE)], home, home / PID_FILE)
    assert (home / PID_FILE).read_text(encoding="ascii") == str(program.pid)
    await until_started(lambda: ended == [3])
    assert not (home / PID_FILE).exists()
    await asyncio.to_thread(program.stop)


@pytest.mark.skipif(sys.platform == "win32", reason="the program stands in as a shell script")
async def test_a_program_that_is_one_file_is_run_in_its_own_folder(tmp_path: Path) -> None:
    tools = tmp_path / "tools" / "direwolf"
    tools.mkdir(parents=True)
    script = tools / "direwolf"
    script.write_text(f"#!/bin/sh\nexec {shlex.join(fakedirewolf.program())} \"$@\"\n", encoding="utf-8")
    script.chmod(0o755)
    m = modem(tmp_path)
    m._finder = lambda: [str(script)]
    await m.start(CARD, "vox", 0)
    await running(m)
    assert len(fakedirewolf.runs(tools)) == 1 and fakedirewolf.runs(radio_folder(tmp_path, 3)) == [], "the made-up Direwolf writes its runs where it works"
    await m.stop()


async def test_no_program_in_the_installation_is_said_and_left(tmp_path: Path) -> None:
    m = DirewolfModem(radio_folder(tmp_path, 3), finder=lambda: None, backoff=QUICK, claims=Claims(), holder=3, lister=fakemercury.program)
    await m.start(CARD, "vox", 0)
    assert (m.state, m.problem, m.reason) == ("waiting", NOT_INSTALLED, "not_installed")
    with pytest.raises(CodedError) as refused:
        await m.tune()
    assert refused.value.code == "hf.not_running"
    await m.stop()


# ---- Tune and the keying test

async def test_tune_stops_the_radios_direwolf_runs_the_alternating_tones_holds_the_frames_and_starts_it_again_on_its_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(direwolftune, "TUNE_SEC", 0.6)
    m = modem(tmp_path)
    again: list[int] = []
    m.ports_changed.connect(lambda: again.append(m.kiss_port))
    await m.start(CARD, "rts:/dev/ttyUSB7", -6)
    await running(m)
    port, home = m.kiss_port, radio_folder(tmp_path, 3)
    await m.tune()
    assert m.test == "tune" and m.hold() == TRANSMITTING and m.wire()["keyed"] and m.describe() == "Direwolf AFSK1200, tuning"
    await until_started(lambda: m.keyed)
    assert fakedirewolf.runs(home)[-1][-4:] == ["-G", "50", "-x", "a"]
    await until_started(lambda: not m.test and m.state == "running" and len(again) == 2)
    assert m.kiss_port == port and again == [port, port] and m.hold() == "" and len(fakedirewolf.runs(home)) == 3 and "-x" not in fakedirewolf.runs(home)[-1], "the radio's Direwolf again, on the same port, and the line told at once (as at the first start)"
    await m.stop()


async def test_the_keying_test_keys_by_ptt_alone_or_by_the_mark_tone_on_vox_and_tune_can_be_ended_early(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(direwolftune, "KEY_TEST_SEC", 0.3)
    home = radio_folder(tmp_path, 3)
    for keying, flag in (("rts:/dev/ttyUSB7", "p"), ("vox", "m")):
        each = modem(tmp_path)
        await each.start(CARD, keying, 0)
        await running(each)
        await each.key_test()
        assert each.test == "key"
        await until_started(lambda flag=flag: ["-x", flag] in [run[-2:] for run in fakedirewolf.runs(home)])
        await until_started(lambda each=each: not each.test and each.state == "running")
        await each.stop()
    m = modem(tmp_path)
    await m.start(CARD, "vox", 0)
    await running(m)
    await m.tune()
    await m.tune_stop()
    assert m.test == "" and not m.keyed
    await running(m)
    await m.stop()


async def test_a_change_of_the_transmit_level_starts_direwolf_again_with_it(tmp_path: Path) -> None:
    m = modem(tmp_path)
    await m.start(CARD, "vox", 0)
    await running(m)
    m.set_tx_gain(-6)
    await until_started(lambda: fakedirewolf.runs(radio_folder(tmp_path, 3))[-1][-2:] == ["-G", "50"])
    await running(m)
    assert m.tx_gain_db == -6 and m.starts == 1, "no restart of the radio: the modem's own"
    m.set_tx_gain(-6)
    await asyncio.sleep(0.2)
    assert len(fakedirewolf.runs(radio_folder(tmp_path, 3))) == 2, "the same level again starts nothing"
    await m.stop()


# ---- Windows

WINMM = (list(fakedirewolf.WINMM_INPUTS), list(fakedirewolf.WINMM_OUTPUTS))
WINDOWS_CARD = "{0.0.1.00000000}.{2301}|{0.0.0.00000000}.{ca03}"


def windows_modem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *modes: str, devices: tuple[list[str], list[str]] = WINMM) -> DirewolfModem:
    """A modem that does what it does on Windows: the WinMM numbers of the card, its name from the HF modem's list, and `cm108` held for the station."""
    monkeypatch.setattr(winmm, "devices", lambda: devices)
    monkeypatch.setattr(direwolfmodem, "_numbers_of", WINMM_NUMBERS_OF)
    m = modem(tmp_path, *modes)
    m.windows = True
    monkeypatch.setattr(m, "_cards", lambda: [SoundCard(WINDOWS_CARD, "USB Audio CODEC", True, True)])
    return m


async def test_on_windows_the_cards_winmm_numbers_are_written_and_a_direwolf_that_stars_another_device_is_ended_before_its_port_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m = windows_modem(tmp_path, monkeypatch)
    await m.start(WINDOWS_CARD, "cm108", 0)
    await running(m)
    assert "ADEVICE 1 1\n" in (radio_folder(tmp_path, 3) / CONF_FILE).read_text(encoding="utf-8") and Claim("keying", "cm108", 3) in m.held(), "one CM108 radio at a time on Windows"
    await m.stop()
    wrong = windows_modem(tmp_path, monkeypatch, "--wrong-star")
    await wrong.start(WINDOWS_CARD, "vox", 0)
    await until_started(lambda: wrong.reason == "sound_card")
    assert wrong.problem == SOUND_CARD_NOT_FOUND
    await wrong.stop()


async def test_on_windows_a_card_that_is_not_one_input_and_one_output_starts_nothing_and_several_cm108_chips_end_direwolf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = windows_modem(tmp_path, monkeypatch, devices=(WINMM[0], WINMM[1][:1]))
    await missing.start(WINDOWS_CARD, "vox", 0)
    assert (missing.state, missing.reason, missing.starts, fakedirewolf.runs(radio_folder(tmp_path, 3))) == ("waiting", "sound_card", 0, [])
    await missing.stop()
    several = windows_modem(tmp_path, monkeypatch, "--several-cm108")
    await several.start(WINDOWS_CARD, "cm108", 0)
    await until_started(lambda: several.reason == "keying")
    assert several.problem == SEVERAL_CM108
    await several.stop()


# ---- the sound card, one resource of the station

async def test_two_sound_card_radios_run_side_by_side_on_two_cards_and_a_third_on_a_held_card_waits_with_the_holder_named(tmp_path: Path) -> None:
    claims = Claims()
    a, b, c = modem(tmp_path, claims=claims, holder=3), modem(tmp_path, claims=claims, holder=4), modem(tmp_path, claims=claims, holder=5)
    await a.start(CARD, "vox", 0)
    await b.start("plughw:CARD=Device,DEV=0", "cm108", 0)
    await running(a)
    await running(b)
    assert a.kiss_port != b.kiss_port and {x.holder for x in claims.all()} == {3, 4}
    await c.start(CARD, "vox", 0)
    assert (c.state, c.reason, c.problem) == ("waiting", "not_started", f"the sound card {CARD} is held by radio 3") and c.starts == 0
    for m in (a, b, c):
        await m.stop()


async def test_an_fm_sound_card_radio_and_the_hf_modem_on_one_card_the_second_is_refused_with_the_holders_name(tmp_path: Path) -> None:
    claims = Claims()
    hf = Mercury(tmp_path, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 2, claims))
    hf.ports = lambda: []
    await hf.start(with_radio(HF, HF_ID, sound_card=CARD, keying="vox"))
    await until_started(lambda: Claim("sound_card", CARD, 2) in claims.all())
    fm = modem(tmp_path, claims=claims, holder=3)
    await fm.start(CARD, "vox", 0)
    assert (fm.state, fm.problem) == ("waiting", f"the sound card {CARD} is held by radio 2")
    await fm.stop()
    await hf.stop()
    fm = modem(tmp_path, claims=claims, holder=3)
    await fm.start(CARD, "vox", 0)
    await running(fm)
    hf2 = Mercury(tmp_path, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]), **of_radio(tmp_path, 2, claims))
    hf2.ports = lambda: []
    await hf2.start(with_radio(HF, HF_ID, sound_card=CARD, keying="vox"))
    assert hf2.state == "waiting" and hf2.problem == f"the sound card {CARD} is held by radio 3", "the other way round too"
    await hf2.stop()
    await fm.stop()


async def test_the_daemons_own_choice_leaves_out_a_card_another_holds_and_proposes_an_aiocs_pin(tmp_path: Path) -> None:
    claims = Claims()
    claims.hold(Claim("serial", port("/dev/ttyUSB0"), 1))
    m = modem(tmp_path, claims=claims)
    cards = [SoundCard("plughw:CARD=AIOC,DEV=0", "All-In-One-Cable", True, True), SoundCard("plughw:CARD=PCH,DEV=0", "HDA Intel PCH", True, True, True)]
    ports = [PortInfo("/dev/ttyUSB0", "CP2102", "", 0x10C4, 0xEA60)]
    assert proposal(cards, ports, claims=claims, holder=3) == ("plughw:CARD=AIOC,DEV=0", "cm108"), "the AIOC by its pin; the Digirig's port is radio 1's"
    claims.hold(Claim("sound_card", "plughw:CARD=AIOC,DEV=0", 4))
    assert proposal(cards, ports, claims=claims, holder=3)[0] == "plughw:CARD=PCH,DEV=0", "a card another holds is not proposed"
    assert proposal([], ports, claims=claims, holder=3) == ("", "")
    m.ports = lambda: [SerialPort("/dev/ttyUSB3", 0x10C4, 0xEA60)]
    await m.start("", "", 0)
    await running(m)
    assert m.keying == Keying("rts", "/dev/ttyUSB3") and Claim("keying", port("/dev/ttyUSB3"), 3) in claims.all(), "the daemon's own keying: the Digirig's line, held"
    await m.stop()


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT")
async def test_the_program_is_ended_by_its_input_closing_not_by_a_signal(tmp_path: Path) -> None:
    """The clean end is the end of the input (Direwolf's -Q): the fake says QRT and exits 0 at once, before any signal is sent."""
    m = modem(tmp_path)
    await m.start(CARD, "vox", 0)
    await running(m)
    process = m._program._process
    assert process is not None
    await m.stop()
    assert process.returncode == 0, "exit 0 from the cleanup, not -SIGINT"
    assert signal.SIGINT.value != -process.returncode


# ---- what a review found

@pytest.mark.parametrize("mode", ["--cm108-unknown", "--hidraw-denied"])
async def test_a_cm108_pin_that_cannot_be_keyed_is_the_reason_keying_not_a_radio_that_says_it_sends(tmp_path: Path, mode: str) -> None:
    """`PTT CM108` with no chip on the card leaves Direwolf running unkeyed (config.c:2185), and a HID it cannot open says so at each key, after `PTT 0 = 1` (cm108.c:1013): either is the radio waiting."""
    m = modem(tmp_path, mode)
    await m.start(CARD, "cm108", 0)
    if mode == "--hidraw-denied":
        await running(m)
        await kiss_send(m.kiss_port, b"\xc0\x00frame\xc0")
    await until_started(lambda: m.reason == "keying")
    assert (m.state, m.problem, m.keyed) == ("waiting", KEYING_FAILED, False)
    await m.stop()


@pytest.mark.parametrize("then", ["stop", "start"])
async def test_a_radio_stopped_or_started_again_while_tune_stops_its_direwolf_gets_no_calibration_run(tmp_path: Path, then: str) -> None:
    m = modem(tmp_path)
    await m.start(CARD, "vox", 0)
    await running(m)
    tune = asyncio.create_task(m.tune())
    await asyncio.sleep(0)                                              # (Tune is stopping the radio's Direwolf, in its thread)
    if then == "stop":
        await m.stop()
    else:
        await m.start(CARD, "vox", 0)
    await asyncio.gather(tune, return_exceptions=True)
    await asyncio.sleep(0.5)
    home = radio_folder(tmp_path, 3)
    assert not any("-x" in run for run in fakedirewolf.runs(home)), "no calibration run after the radio was stopped or started again: it would key the radio beside the radio's own run"
    if then == "stop":
        assert (m.state, m.test, m.pid) == ("stopped", "", None)
    else:
        await running(m)
        assert m.test == "" and _alive(m.pid) and len(fakedirewolf.runs(home)) == 2, "the radio's own run alone"
    await m.stop()


@pytest.mark.expects_errors
async def test_a_second_run_started_while_one_is_on_ends_that_one_first(tmp_path: Path) -> None:
    home = radio_folder(tmp_path, 3)
    home.mkdir(parents=True)
    (home / CONF_FILE).write_text("ADEVICE x\nKISSPORT 0\n", encoding="utf-8")
    program = direwolfprogram.Program(lambda code, lines: None)
    program.start([*fakedirewolf.program(), "-x", "p", "-c", str(home / CONF_FILE)], home)
    first = program.pid
    await until_started(lambda: len(fakedirewolf.runs(home)) == 1)
    program.start([*fakedirewolf.program(), "-x", "p", "-c", str(home / CONF_FILE)], home)
    assert not _alive_child(first) and program.running, "the first run is ended: none is ever left beside a new one"
    await asyncio.to_thread(program.stop)


def _alive_child(pid: int | None) -> bool:
    """Whether the process of this id still runs (a child that ended and was waited for is gone, and one that ended and was not, a zombie, is gone too)."""
    return _alive(pid)


async def test_a_frame_direwolf_still_holds_goes_out_before_tune_takes_the_radio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(direwolftune, "TUNE_SEC", 0.3)
    m = modem(tmp_path, busy_sec=0.6)                                   # (the channel is busy: the frame waits in Direwolf before it is keyed)
    await m.start(CARD, "vox", 0)
    await running(m)
    reader, writer = await asyncio.open_connection("127.0.0.1", m.kiss_port)
    writer.write(b"\xc0\x00frame\xc0")
    await writer.drain()
    await until(lambda: m._handed == 1)
    await m.tune()
    assert await asyncio.wait_for(reader.read(4096), 10) == b"\xc0\x00frame\xc0", "the frame went out before the radio's Direwolf was stopped for the tones"
    writer.close()
    await until_started(lambda: not m.test and m.state == "running")
    await m.stop()


async def test_a_new_transmit_level_during_the_keying_test_leaves_it_its_one_second(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(direwolftune, "KEY_TEST_SEC", 0.3)
    monkeypatch.setattr(direwolftune, "TUNE_SEC", 30.0)
    m = modem(tmp_path)
    await m.start(CARD, "rts:/dev/ttyUSB7", 0)
    await running(m)
    await m.key_test()
    m.set_tx_gain(-6)
    await until_started(lambda: not m.test and m.state == "running" and len(fakedirewolf.runs(radio_folder(tmp_path, 3))) == 3)
    runs = fakedirewolf.runs(radio_folder(tmp_path, 3))
    assert [run[-2:] for run in runs if "-x" in run] == [["-x", "p"]] and runs[-1][-2:] == ["-G", "50"], "one keying test, its own length; the radio's Direwolf after it with the new level"
    await m.stop()


async def test_no_sound_card_named_and_none_of_the_radios_listed_waits_for_one_and_starts_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m = modem(tmp_path)
    monkeypatch.setattr(m, "_cards", lambda: [SoundCard("plughw:CARD=PCH,DEV=0", "HDA Intel PCH", True, True, True)])
    await m.start("", "", 0)
    assert (m.state, m.reason, m.problem, m.starts) == ("waiting", "sound_card", direwolfmodem.NO_SOUND_CARD, 0) and fakedirewolf.runs(radio_folder(tmp_path, 3)) == [], "never the computer's speakers"
    monkeypatch.setattr(m, "_cards", lambda: [])
    await m.start("", "", 0)
    assert (m.state, m.reason) == ("waiting", "sound_card") and fakedirewolf.runs(radio_folder(tmp_path, 3)) == [], "no card listed at all"
    await m.stop()
    assert m.claims is not None and m.claims.hold(Claim("sound_card", CARD, 2)) is None
    monkeypatch.setattr(m, "_cards", lambda: [SoundCard(CARD, "USB Audio CODEC", True, True, True)])
    await m.start("", "", 0)
    assert (m.state, m.problem) == ("waiting", f"the sound card {CARD} is held by radio 2"), "the radio's one card is the HF modem's: said with its holder, not as no card"
    await m.stop()


async def test_the_daemons_own_keying_is_the_port_of_the_cards_interface(tmp_path: Path) -> None:
    m = modem(tmp_path)
    m.ports = lambda: [SerialPort("/dev/ttyUSB3", 0x10C4, 0xEA60), SerialPort("/dev/ttyUSB4", 0x10C4, 0xEA60)]
    m.beside = lambda card, devices: ["/dev/ttyUSB4"] if card == CARD else []
    await m.start(CARD, "", 0)
    await running(m)
    assert m.keying == Keying("rts", "/dev/ttyUSB4"), "two Digirigs: the one whose card this is"
    await m.stop()
    cards = [SoundCard("plughw:CARD=AIOC,DEV=0", "All-In-One-Cable", True, True)]
    ftdi = [PortInfo("/dev/ttyUSB1", "FT232R", "", 0x0403, 0x6001)]
    assert proposal(cards, ftdi, holder=3, beside=lambda card, devices: None) == ("plughw:CARD=AIOC,DEV=0", "cm108"), "an AIOC beside an FTDI cable keys by its pin"


async def test_a_port_left_out_in_another_spelling_of_it_as_on_windows_keys_no_sound_card_radio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The ports left out are as the station's table compares them (mercurymodem.left_out: `COM3`), the ports the system lists too: on Windows `com3` and `\\\\.\\COM3` are that one port."""
    monkeypatch.setattr(serialholders, "_on_windows", lambda: True)
    for listed in ("com3", "\\\\.\\COM3"):
        m = modem(tmp_path)
        m.ports, m.beside = (lambda listed=listed: [SerialPort(listed, 0x10C4, 0xEA60)]), (lambda card, devices: None)
        await m.start(CARD, "", 0, leave=("COM3",))
        await running(m)
        assert m.keying == Keying("vox"), (listed, m.keying)
        await m.stop()
        cards, ports = [SoundCard(CARD, "USB Audio CODEC", True, True)], [PortInfo(listed, "CP2102", "", 0x10C4, 0xEA60)]
        assert proposal(cards, ports, ("COM3",), holder=3, beside=lambda card, devices: None) == (CARD, "vox"), "the page's proposal leaves it out alike"
        assert proposal(cards, ports, (), holder=3, beside=lambda card, devices: None) == (CARD, f"rts:{listed}"), "and keys by it when no radio names it"
