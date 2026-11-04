"""The file that holds the id of the Mercury the daemon started (`mercury.pid`) and the stopping of that Mercury (neoaprs/mercuryhelper.py): a clean stop leaves no file behind, the next start ends a process of the file's
id only when it is a Mercury (on Windows, which reuses ids and has no /proc, by the name of its program file), and a Mercury that does not end at the first request is asked a second time, as its own handling of a second
SIGTERM drops the transmitter, before it is killed."""
import asyncio
import random
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import mercuryhelper, mercurymodem
from neoaprs.config import DEFAULTS, Config
from neoaprs.mercury import BROADCAST_PORT
from neoaprs.mercuryhelper import PORT_TRIES, Program, end_stale, free_ports, image_is_mercury
from neoaprs.mercurymodem import PID_FILE, Mercury
from neoaprs.source import Backoff
from tests.support import fakemercury
from tests.support.env import until

HF: Config = replace(DEFAULTS, hf_enabled=True, fm_enabled=False, mercury_keying="rts:/dev/ttyUSB0", mercury_sound_card="plughw:1,0", station_call="OH2GBA")
QUICK = Backoff([0.1, 0.1])


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test asks for free ports from a base of its own, so that two tests running side by side (pytest-xdist) do not both find 8100 free between the probe and the bind."""
    base = random.randrange(20000, 40000, 500)             # (every port of the pair, and the UI port 2000 above, stays under 49152: Windows hands out and reserves the ports above it, and a base there found no free pair on CI's Windows runner)
    monkeypatch.setattr(mercurymodem, "free_ports", lambda first=BROADCAST_PORT, tries=PORT_TRIES: free_ports(base, tries))


def modem(tmp_path: Path) -> Mercury:
    m = Mercury(tmp_path, finder=fakemercury.program, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []                                                  # (never the operator's serial ports)
    return m


# ---- the file of a clean stop

async def test_a_clean_stop_removes_the_pid_file_that_the_start_wrote(tmp_path: Path) -> None:
    """The file is for a daemon that crashed; a clean stop leaves none, so that no later start looks at an id that something else may have by then."""
    m = modem(tmp_path)
    await m.start(HF)
    pid_file = tmp_path / PID_FILE
    assert m.pid is not None and pid_file.read_text(encoding="ascii") == str(m.pid)
    await m.stop()
    assert not pid_file.exists()


# ---- which process is a Mercury

def test_a_process_is_a_mercury_on_windows_when_its_program_file_is_mercury_exe_and_not_when_it_is_another_or_unknown() -> None:
    assert image_is_mercury(r"C:\Users\john\AppData\Local\Programs\NeoAPRS\bin\mercury\MERCURY.EXE")
    assert image_is_mercury("C:/Program Files/NeoAPRS/mercury/mercury.exe")
    assert not image_is_mercury(r"C:\Windows\explorer.exe")
    assert not image_is_mercury(r"C:\Users\mercury\notmercury.exe")
    assert not image_is_mercury(r"C:\mercury.exe\other.exe")
    assert not image_is_mercury("")
    assert not image_is_mercury(None)


def _no_such_process() -> int:
    pid = 2**22 + 12345
    if Path(f"/proc/{pid}").exists():
        pytest.skip("this machine has a process of the id the test needs to be none")
    return pid


def _windows_with(monkeypatch: pytest.MonkeyPatch, image: str | None) -> list[tuple[int, int]]:
    """A Windows on which the id from the file is a running process with this program file; the kills that were asked for are returned in the list (and none may be real)."""
    kills: list[tuple[int, int]] = []

    def kill(pid: int, sig: int) -> None:
        kills.append((pid, sig))

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(mercuryhelper, "_running_windows", lambda pid: True)
    monkeypatch.setattr(mercuryhelper, "_windows_image", lambda pid: image)
    monkeypatch.setattr(mercuryhelper.os, "kill", kill)
    return kills


@pytest.mark.skipif(sys.platform == "win32", reason="the test stands in for Windows on a machine that has /proc")
def test_a_process_that_is_not_a_mercury_is_left_alone_and_the_file_is_consumed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = _no_such_process()
    for image in (r"C:\Windows\explorer.exe", None):                      # (a program that is something else, and one whose file cannot be read)
        pid_file = tmp_path / "mercury.pid"
        pid_file.write_text(str(pid), encoding="ascii")
        kills = _windows_with(monkeypatch, image)
        assert end_stale(pid_file) is False
        assert kills == [] and not pid_file.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="the test stands in for Windows on a machine that has /proc")
def test_a_process_whose_program_file_is_mercury_exe_is_ended(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = _no_such_process()
    pid_file = tmp_path / "mercury.pid"
    pid_file.write_text(str(pid), encoding="ascii")
    kills = _windows_with(monkeypatch, r"C:\Program Files\NeoAPRS\bin\mercury\mercury.exe")
    assert end_stale(pid_file) is True
    assert [k[0] for k in kills] == [pid] and not pid_file.exists()


# ---- the second request to end

@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no signal handlers: a terminate there is the hard end")
async def test_a_program_that_does_not_end_at_the_first_request_is_asked_a_second_time_before_it_is_killed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mercury drops the transmitter on a second SIGTERM; a kill would leave a GPIO pin or a serial line keyed."""
    monkeypatch.setattr(mercuryhelper, "STOP_WAIT_SEC", 0.2)
    count = tmp_path / "terms"
    ready = tmp_path / "ready"
    code = ("import signal, sys, time\n"
            f"count, ready = {str(count)!r}, {str(ready)!r}\n"
            "def term(*_):\n"
            "    open(count, 'a').write('x')\n"
            "    if len(open(count).read()) >= 2:\n"
            "        sys.exit(0)\n"
            "signal.signal(signal.SIGTERM, term)\n"
            "open(ready, 'w').write('up')\n"
            "time.sleep(60)\n")
    program = Program(lambda exit_code, lines: None)
    program.start([sys.executable, "-c", code], tmp_path, tmp_path / PID_FILE)
    process = program._process
    assert process is not None
    await until(ready.exists)                                             # (the handler is in place when the file is there)
    await asyncio.to_thread(program.stop)
    assert process.returncode == 0, "ended by the second request, not killed"
    assert count.read_text() == "xx"
    assert not (tmp_path / PID_FILE).exists()
