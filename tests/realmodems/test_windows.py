"""Tests for the Windows builds of the two modems on GitHub's Windows runner, which has no sound device:
Direwolf's demodulator built for Windows (atest.exe) decodes the recorded audio of tests/fixtures/audio/,
mercury.exe asked to end the way the daemon asks it (Ctrl-Break to its own process group,
packaging/mercury/sigbreak.patch) shuts down in order instead of being cut off, and it writes its log
lines through a pipe as it runs (flush.patch). NEOAPRS_WINDOWS_MODEMS is the folder that holds
mercury/mercury.exe and direwolf/dev/atest.exe."""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from neoaprs import mercury, winchild
from neoaprs.childprogram import HIDDEN_WINDOW, OWN_GROUP
from neoaprs.mercuryhelper import free_ports
from tests.realmodems.probe import Modem
from tests.support import direwolfaudio

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the Windows job's")

MODEMS = Path(os.environ.get("NEOAPRS_WINDOWS_MODEMS", "."))
MERCURY = MODEMS / "mercury" / "mercury.exe"
ATEST = MODEMS / "direwolf" / "dev" / "atest.exe"
END_SEC = 20.0
# What Mercury's handler of a first signal writes (main.c, handle_termination_signal)
SHUTTING_DOWN = "Signal received, shutting down"


def test_the_programs_are_there() -> None:
    assert MERCURY.is_file() and ATEST.is_file(), f"{MERCURY}, {ATEST}"
    assert mercury.VERSION.encode("ascii") in MERCURY.read_bytes(), f"mercury.exe is Mercury {mercury.VERSION}"


@pytest.mark.parametrize("name", sorted(direwolfaudio.FILES))
def test_direwolf_for_windows_decodes_the_recorded_audio_of_the_frames_we_send(name: str) -> None:
    assert direwolfaudio.decoded(str(ATEST), direwolfaudio.FIXTURES / name) == list(direwolfaudio.FRAMES)


def test_direwolf_for_windows_decodes_as_many_frames_under_rising_noise_as_the_direwolf_that_made_them() -> None:
    got = direwolfaudio.decoded(str(ATEST), direwolfaudio.FIXTURES / direwolfaudio.NOISE_FILE)
    assert len(got) == direwolfaudio.NOISE_DECODED, f"{len(got)} of {direwolfaudio.NOISE_FRAMES} decoded"


async def test_mercury_asked_to_end_by_ctrl_break_while_it_sends_shuts_down_in_order(tmp_path: Path) -> None:
    ports = free_ports(18400)
    ini = tmp_path / "m.ini"
    ini.write_text("[store]\nenabled = false\n", encoding="utf-8")
    argv = [
        str(MERCURY),
        "-C",
        str(ini),
        "-m",
        "1",
        "-x",
        "null",
        "-b",
        str(ports[0]),
        "-p",
        str(ports[1]),
        "-P",
        "none",
    ]
    # as the daemon starts it: a hidden console of its own, in a process group of its own
    modem = Modem("break", argv, tmp_path, dict(os.environ), HIDDEN_WINDOW | OWN_GROUP)
    try:
        await modem.open(*ports)
        modem.send(b"OH2GW>APZNEO:>a frame in flight when the end is asked")
        await modem.until("PTT ON", lambda: bool(modem.seen("ptt", True)), 30.0)
        assert winchild.ask_to_end(modem.process.pid), "the asker sent the Ctrl-Break"
        await modem.until("the end", lambda: modem.process.poll() is not None, END_SEC)
        assert modem.process.returncode == 0, f"ended with {modem.process.returncode:#x}:\n{modem.said()[-2000:]}"
        assert SHUTTING_DOWN in modem.said(), "the handler of Ctrl-C took the Ctrl-Break"
    finally:
        await modem.close()


def test_mercury_writes_its_log_lines_through_a_pipe_as_it_runs_not_when_it_ends(tmp_path: Path) -> None:
    """packaging/mercury/flush.patch: Windows's C runtime buffers a pipe, and Mercury never flushed it."""
    ports = free_ports(18500)
    ini = tmp_path / "m.ini"
    ini.write_text("[store]\nenabled = false\n", encoding="utf-8")
    argv = [str(MERCURY), "-C", str(ini), "-m", "1", "-x", "null", "-b", str(ports[0]), "-p", str(ports[1])]
    child = subprocess.Popen(
        [*argv, "-P", "none"],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=HIDDEN_WINDOW | OWN_GROUP,
    )
    heard: list[tuple[str, bool]] = []

    def read() -> None:
        assert child.stdout is not None
        for raw in child.stdout:
            heard.append((raw.decode("utf-8", errors="replace"), child.poll() is None))

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 60.0
        while not any(f"Mercury {mercury.VERSION} (git" in line for line, _ in heard) and time.monotonic() < deadline:
            time.sleep(0.1)
        running = [alive for line, alive in heard if f"Mercury {mercury.VERSION} (git" in line]
        assert running == [True], f"the start line came while it ran: {heard[:10]}"
    finally:
        child.kill()
        child.wait(20)
        reader.join(10)
