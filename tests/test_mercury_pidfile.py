"""The file with the id of the Mercury the daemon started (`mercury.pid`) and stopping that Mercury
(neoaprs/mercuryhelper.py, mercurystale.py): a clean stop leaves no file; a start ends only the
radio's own.
"""

import asyncio
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import childprogram, direwolf, direwolfprogram, mercuryhelper, mercurystale
from neoaprs.config import DEFAULTS, Config
from neoaprs.mercuryclaims import end_left_behind
from neoaprs.mercuryhelper import Program
from neoaprs.childprogram import made_before
from neoaprs.mercurystale import end_stale, runs_with, same_program
from neoaprs.mercurymodem import PID_FILE, Mercury
from neoaprs.source import Backoff
from tests.support import fakemercury
from tests.support.env import until_started
from tests.support.fakemercury import of_radio
from tests.support.modemports import own_ports

HF: Config = replace(
    DEFAULTS,
    hf_enabled=True,
    fm_enabled=False,
    mercury_keying="rts:/dev/ttyUSB0",
    mercury_sound_card="plughw:1,0",
    station_call="OH2GBA",
)
QUICK = Backoff([0.1, 0.1])


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test asks the modem for free ports from a base of its own (tests/support/modemports.py):
    no other test running beside it is handed its ports."""
    own_ports(monkeypatch)


def modem(tmp_path: Path, radio: bool = True) -> Mercury:
    m = Mercury(
        tmp_path,
        finder=fakemercury.program,
        backoff=QUICK,
        control_backoff=Backoff([0.05, 0.05]),
        **(of_radio(tmp_path) if radio else {}),
    )
    m.ports = lambda: []  # (never the operator's serial ports)
    return m


# ---- the file of a clean stop


@pytest.mark.parametrize("radio", [True, False], ids=["radio", "folderless"])
async def test_a_clean_stop_removes_the_pid_file_that_the_start_wrote(tmp_path: Path, radio: bool) -> None:
    """The file is for a daemon that crashed; a clean stop leaves none, so that no later start looks
    at an id that something else may have by then."""
    m = modem(tmp_path, radio)
    await m.start(HF)
    pid_file = (tmp_path / "radios" / "2" if radio else tmp_path) / PID_FILE
    assert m.pid is not None and pid_file.read_text(encoding="ascii") == str(m.pid), (
        "the radio's own file in its folder; today's modem's in the data folder"
    )
    assert not radio or not (tmp_path / PID_FILE).exists()
    await m.stop()
    assert not pid_file.exists() and pid_file.parent.is_dir(), "the file goes, the folder stays"


# ---- which process is a Mercury

SHIPPED = r"C:\Program Files\NeoAPRS\bin\mercury\mercury.exe"


def test_a_process_is_this_radios_mercury_by_its_configuration_and_on_windows_by_its_program_file() -> None:
    ini = Path("/data/radios/5/mercury.ini")
    assert runs_with(["/opt/neoaprs/mercury/mercury", "-C", str(ini), "-m", "1"], ini)
    assert runs_with(["python", "fakemercury.py", "-C", "/data/radios/5/../5/mercury.ini"], ini), (
        "the same file, resolved"
    )
    assert not runs_with(["/opt/neoaprs/mercury/mercury", "-C", "/data/radios/2/mercury.ini"], ini), (
        "another radio's Mercury"
    )
    assert (
        not runs_with(["tail", "-f", "/home/op/mercury/mercury.ini"], ini)
        and not runs_with(["mercury", str(ini)], ini)
        and not runs_with(["mercury", "-C"], ini)
    ), "the word is not enough"
    assert same_program(SHIPPED.upper(), [SHIPPED]) and same_program(SHIPPED.replace("\\", "/"), [SHIPPED])
    assert not same_program(r"C:\Users\op\mercury\mercury.exe", [SHIPPED]), (
        "the operator's own Mercury is not the radio's"
    )
    assert (
        not same_program(r"C:\Windows\explorer.exe", [SHIPPED])
        and not same_program(None, [SHIPPED])
        and not same_program("", [SHIPPED])
    )
    assert (
        made_before(100.0, 100.0)
        and made_before(95.0, 100.0)
        and not made_before(100.0 + 3600, 100.0)
        and not made_before(None, 100.0)
    )


def _no_such_process() -> int:
    pid = 2**22 + 12345
    if Path(f"/proc/{pid}").exists():
        pytest.skip("this machine has a process of the id the test needs to be none")
    return pid


def test_on_a_system_without_proc_the_radios_mercury_is_known_by_the_command_line_ps_gives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """macOS has no /proc: a leftover Mercury is found by its command line, or it would hold the
    sound card."""
    if sys.platform == "win32":
        pytest.skip("Windows asks the process's program file instead")
    pid, ini = _no_such_process(), Path("/Users/op/Library/Application Support/NeoAPRS/radios/5/mercury.ini")
    commands = {pid: f"/Applications/NeoAPRS.app/Contents/Resources/mercury/mercury -C {ini} -m 1 -b 8100 -p 8300"}
    monkeypatch.setattr(mercurystale, "_ps_command", commands.get)
    assert mercurystale._is_mercury(pid, ini, ["mercury"], 0.0), "the path with its space, whole"
    assert not mercurystale._is_mercury(pid, ini.parent.parent / "2" / "mercury.ini", ["mercury"], 0.0), (
        "another radio's Mercury"
    )
    assert not mercurystale._is_mercury(pid + 1, ini, ["mercury"], 0.0), "a process ps does not know"
    commands[pid] = f"/usr/bin/less {ini}"
    assert not mercurystale._is_mercury(pid, ini, ["mercury"], 0.0), "the file's name is not enough"


def _windows_with(
    monkeypatch: pytest.MonkeyPatch, image: str | None, made: float | None = 0.0
) -> list[tuple[int, int]]:
    """A Windows on which the id from the file is a running process with this program file, made at
    `made` (seconds since 1970); the kills that were asked for are returned in the list (and none
    may be real)."""
    kills: list[tuple[int, int]] = []

    def kill(pid: int, sig: int) -> None:
        kills.append((pid, sig))

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(mercurystale, "_running_windows", lambda pid: not kills)
    monkeypatch.setattr(childprogram, "_running_windows", lambda pid: not kills)
    monkeypatch.setattr(mercurystale, "_windows_image", lambda pid: image)
    monkeypatch.setattr(mercurystale, "windows_created", lambda pid: made)
    monkeypatch.setattr(mercurystale.os, "kill", kill)
    return kills


@pytest.mark.skipif(sys.platform == "win32", reason="the test stands in for Windows on a machine that has /proc")
def test_a_process_that_is_not_the_radios_mercury_is_left_alone_and_the_file_is_consumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _no_such_process()
    # A program that is something else, a Mercury that is not the radio's, one whose file cannot be
    # read
    for image in (r"C:\Windows\explorer.exe", r"C:\Users\op\mercury\mercury.exe", None):
        pid_file = tmp_path / "mercury.pid"
        pid_file.write_text(str(pid), encoding="ascii")
        kills = _windows_with(monkeypatch, image)
        assert end_stale(pid_file, tmp_path / "mercury.ini", [SHIPPED]) is False
        assert kills == [] and not pid_file.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="the test stands in for Windows on a machine that has /proc")
def test_a_mercury_made_after_its_file_was_written_is_another_radios_after_a_reboot_and_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both radios' files survive a power cut; the id in radio 5's may be given to radio 2's fresh
    Mercury, the same program file: it was made after radio 5's file was written."""
    pid = _no_such_process()
    pid_file = tmp_path / "mercury.pid"
    pid_file.write_text(str(pid), encoding="ascii")
    kills = _windows_with(monkeypatch, SHIPPED, made=pid_file.stat().st_mtime + 3600)
    assert end_stale(pid_file, tmp_path / "mercury.ini", [SHIPPED]) is False
    assert kills == [] and not pid_file.exists()
    pid_file.write_text(str(pid), encoding="ascii")
    kills = _windows_with(monkeypatch, SHIPPED, made=None)
    assert end_stale(pid_file, tmp_path / "mercury.ini", [SHIPPED]) is False and kills == [], (
        "a time that cannot be read ends nothing"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="the test stands in for Windows on a machine that has /proc")
def test_the_radios_own_mercury_made_before_its_file_was_written_is_ended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _no_such_process()
    pid_file = tmp_path / "mercury.pid"
    pid_file.write_text(str(pid), encoding="ascii")
    kills = _windows_with(monkeypatch, SHIPPED, made=pid_file.stat().st_mtime - 0.5)
    assert end_stale(pid_file, tmp_path / "mercury.ini", [SHIPPED]) is True
    assert [k[0] for k in kills] == [pid] and not pid_file.exists()


def _sleeper(tmp_path: Path, *args: str, term_sec: float = 0.0) -> "subprocess.Popen[bytes]":
    """A process that runs for a minute with these arguments after its own code, and takes
    `term_sec` to end when it is asked to."""
    ready = tmp_path / f"ready-{len(list(tmp_path.iterdir()))}"
    code = f"import signal, sys, time\ndef term(*_):\n    time.sleep({term_sec})\n    sys.exit(0)\nsignal.signal(signal.SIGTERM, term)\nopen({str(ready)!r}, 'w').write('up')\ntime.sleep(600)\n"
    process = subprocess.Popen([sys.executable, "-c", code, *args])
    deadline = time.monotonic() + 30
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    return process


@pytest.mark.skipif(sys.platform == "win32", reason="the command line of another process is read from /proc")
def test_a_process_with_mercury_in_its_command_line_is_ended_only_when_it_runs_with_the_radios_configuration(
    tmp_path: Path,
) -> None:
    ini = tmp_path / "radios" / "5" / "mercury.ini"
    other = _sleeper(tmp_path, "/home/op/notes/mercury-log.txt", "-C", str(tmp_path / "radios" / "2" / "mercury.ini"))
    ours = _sleeper(tmp_path, "-C", str(ini), "mercury")
    try:
        pid_file = tmp_path / "mercury.pid"
        pid_file.write_text(str(other.pid), encoding="ascii")
        assert (
            end_stale(pid_file, ini, fakemercury.program()) is False and other.poll() is None and not pid_file.exists()
        ), "the operator's process, and another radio's Mercury, are left alone"
        pid_file.write_text(str(ours.pid), encoding="ascii")
        assert end_stale(pid_file, ini, fakemercury.program()) is True and ours.wait(10) == 0
    finally:
        for process in (other, ours):
            process.kill()
            process.wait()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no signal handlers: a terminate there is the hard end")
def test_a_mercury_left_behind_has_ended_when_end_stale_returns(tmp_path: Path) -> None:
    """The start that follows opens the same sound card: a Mercury that takes a moment to end (it
    drops the transmitter first) has let go of it by then."""
    ini = tmp_path / "mercury.ini"
    slow = _sleeper(tmp_path, "-C", str(ini), term_sec=0.5)
    try:
        pid_file = tmp_path / "mercury.pid"
        pid_file.write_text(str(slow.pid), encoding="ascii")
        assert end_stale(pid_file, ini, fakemercury.program()) is True
        assert mercurystale.gone(slow.pid), (
            "ended (a zombie of the test's own child holds nothing), not still dropping its transmitter"
        )
    finally:
        slow.kill()
        slow.wait()


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="the command line is read from /proc, and the rights of a folder on POSIX, which root ignores",
)
def test_a_file_that_cannot_be_removed_does_not_stop_the_daemons_start_and_its_mercury_is_still_ended(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """end_left_behind runs in the daemon's start: a pid file that cannot be removed (a folder that
    cannot be written; on Windows one a virus scanner holds) is a line in the log, not a daemon that
    does not start."""
    folder = tmp_path / "radios" / "5"
    folder.mkdir(parents=True)
    ours = _sleeper(tmp_path, "-C", str(folder / "mercury.ini"))
    (folder / PID_FILE).write_text(str(ours.pid), encoding="ascii")
    folder.chmod(0o555)
    try:
        end_left_behind(tmp_path)
        assert ours.wait(10) == 0 and (folder / PID_FILE).exists(), (
            "the check went on: the Mercury was ended, the file stays"
        )
        assert any("could not be removed" in r.getMessage() for r in caplog.records)
    finally:
        folder.chmod(0o755)
        ours.kill()
        ours.wait()


# ---- the file a later run wrote


@pytest.mark.skipif(sys.platform == "win32", reason="the test's program is asked to end by a signal")
async def test_a_stop_that_ends_after_the_next_run_wrote_the_file_leaves_that_runs_file(tmp_path: Path) -> None:
    """A stop in a thread (the sound card's error) can take longer than the back-off: the relaunch
    has written its own id in the file meanwhile, and the stop must not remove it."""
    pid_file = tmp_path / PID_FILE
    program = Program(lambda exit_code, lines: None)
    program.start([sys.executable, "-c", "import time; time.sleep(600)"], tmp_path, pid_file)
    pid_file.write_text("424242", encoding="ascii")  # (the next run's)
    await asyncio.to_thread(program.stop)
    assert pid_file.read_text(encoding="ascii") == "424242"
    program.start([sys.executable, "-c", "import time; time.sleep(600)"], tmp_path, pid_file)
    await asyncio.to_thread(program.stop)
    assert not pid_file.exists(), "its own file goes with it"


# ---- the second request to end


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no signal handlers: a terminate there is the hard end")
async def test_a_program_that_does_not_end_at_the_first_request_is_asked_a_second_time_before_it_is_killed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mercury drops the transmitter on a second SIGTERM; a kill would leave a GPIO pin or a serial
    line keyed."""
    monkeypatch.setattr(mercuryhelper, "STOP_WAIT_SEC", 0.2)
    count = tmp_path / "terms"
    ready = tmp_path / "ready"
    code = (
        "import signal, sys, time\n"
        f"count, ready = {str(count)!r}, {str(ready)!r}\n"
        "def term(*_):\n"
        "    open(count, 'a').write('x')\n"
        "    if len(open(count).read()) >= 2:\n"
        "        sys.exit(0)\n"
        "signal.signal(signal.SIGTERM, term)\n"
        "open(ready, 'w').write('up')\n"
        "time.sleep(600)\n"
    )
    program = Program(lambda exit_code, lines: None)
    program.start([sys.executable, "-c", code], tmp_path, tmp_path / PID_FILE)
    process = program._process
    assert process is not None
    # The handler is in place when the file is there
    await until_started(ready.exists)
    await asyncio.to_thread(program.stop)
    assert process.returncode == 0, "ended by the second request, not killed"
    assert count.read_text() == "xx"
    assert not (tmp_path / PID_FILE).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="the command line of another process is read from /proc")
def test_a_sound_card_radios_direwolf_and_an_hf_radios_mercury_left_behind_side_by_side_each_end_only_their_own(
    tmp_path: Path,
) -> None:
    """Radio 3 a Sound card radio, radio 5 an HF one, both left running by a daemon that did not
    stop cleanly: the daemon's start ends radio 5's Mercury and leaves the Direwolf, which radio 3's
    start ends; a file that names the other program's process (an id the system gave again) ends
    nothing."""
    wolf_home, mercury_home = tmp_path / "radios" / "3", tmp_path / "radios" / "5"
    wolf_home.mkdir(parents=True)
    mercury_home.mkdir(parents=True)
    wolf = _sleeper(tmp_path, "-c", str(wolf_home / direwolf.CONF_FILE), "-Q")
    mercury = _sleeper(tmp_path, "-C", str(mercury_home / "mercury.ini"))
    try:
        (mercury_home / PID_FILE).write_text(str(wolf.pid), encoding="ascii")
        (wolf_home / direwolf.PID_FILE).write_text(str(mercury.pid), encoding="ascii")
        end_left_behind(tmp_path)
        assert direwolfprogram.end_stale(wolf_home / direwolf.PID_FILE) is False and (wolf.poll(), mercury.poll()) == (
            None,
            None,
        ), "neither file names its own program's process: nothing is ended"
        (mercury_home / PID_FILE).write_text(str(mercury.pid), encoding="ascii")
        (wolf_home / direwolf.PID_FILE).write_text(str(wolf.pid), encoding="ascii")
        end_left_behind(tmp_path)
        assert mercury.wait(10) == 0 and wolf.poll() is None and (wolf_home / direwolf.PID_FILE).exists(), (
            "the daemon's start ends the Mercury of ours, and no Direwolf"
        )
        assert (
            direwolfprogram.end_stale(wolf_home / direwolf.PID_FILE) is True
            and wolf.wait(10) is not None
            and not (wolf_home / direwolf.PID_FILE).exists()
        ), "radio 3's start ends its own"
    finally:
        for process in (wolf, mercury):
            process.kill()
            process.wait()
