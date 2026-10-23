"""`neoaprs replay` and `neoaprs db` as processes, and the scripts that wrap them: the replay of the live capture as a TNC on a TCP port fills the database of a daemon that has no radio, and the tool shows what is
in it; the replay on a pseudo-terminal (`--pty`, POSIX only) is the same through a device file."""
import os
import select
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from neoaprs.kiss import KissDecoder
from tests.conftest import ROOT
from tests.support.files import FIXTURES
from tests.support.proc import NEW_GROUP, stop
from tests.support.ptyline import posix_only

CAPTURE = FIXTURES / "kiss" / "thd7-2026-10-21.bin"


def env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in ("NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG")}


def tool(data: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "neoaprs", "db", "--data", str(data), *args], cwd=ROOT, env=env(), capture_output=True, text=True, timeout=60)


def script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    """A wrapper of scripts/ as it is run in a clone, with the test's python for NEOAPRS_PYTHON."""
    return subprocess.run([str(ROOT / "scripts" / name), *args], cwd=ROOT, env={**env(), "NEOAPRS_PYTHON": sys.executable}, capture_output=True, text=True, timeout=60)


def wait_until(condition: object, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():  # type: ignore[operator]
            return
        time.sleep(0.05)
    raise AssertionError("the condition did not come true")


def test_a_replayed_capture_fills_the_database_of_a_daemon_without_a_radio_over_tcp(tmp_path: Path) -> None:
    data = tmp_path / "data"
    for key, value in (("station/call", "OH2GBA"), ("station/lat", "60.17"), ("station/lon", "24.94")):         # (a station that is set up: with no call and position there is no station of ours in the book)
        assert tool(data, "set", key, value).returncode == 0
    replay = subprocess.Popen([sys.executable, "-m", "neoaprs", "replay", str(CAPTURE), "--interval", "0.2"], cwd=ROOT, env=env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    daemon = None
    try:
        assert replay.stdout is not None
        path = replay.stdout.readline().strip()
        assert path.startswith("socket://127.0.0.1:")
        daemon = subprocess.Popen([sys.executable, "-m", "neoaprs", "--data", str(data), "--port", path, "--web-port", "0"], cwd=ROOT, env=env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NEW_GROUP)
        log = data / "neoaprs.log"
        wait_until(lambda: log.exists() and log.read_text(encoding="utf-8").count(" -> position ") >= 4)
        stations = tool(data, "stations")                                          # while the daemon runs (the appends are committed within a second)
        wait_until(lambda: "OH2PU-9" in tool(data, "stations").stdout)
        stations = tool(data, "stations")
        assert stations.returncode == 0, stations.stderr
        for call in ("OH2RDG", "OH2RDK-7", "OH2RDS", "OH2PU-9", "OH2GBA"):
            assert call in stations.stdout
        assert "60.1650 24.9467" in stations.stdout
        packets = tool(data, "packets", "-n", "2")
        lines = packets.stdout.splitlines()
        assert packets.returncode == 0 and len(lines) == 2 and lines[1].endswith("OH2PU-9>APOTC1,OH2RCH-2*:!/0&m]TbwX>z!GQRV D-STAR 144.650MHz -> position 60.1991 24.6501 />" + " QRV D-STAR 144.650MHz")
        assert lines[0] < lines[1] or lines[0][:20] <= lines[1][:20], "the oldest first"
        stop(daemon)
        out, err = daemon.communicate(timeout=10)
        assert daemon.returncode == 0, (out, err)
    finally:
        for proc in (daemon, replay):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.communicate()


@posix_only
def test_the_replay_on_a_pseudo_terminal_ends_on_ctrl_c_and_says_what_it_does(tmp_path: Path) -> None:
    replay = subprocess.Popen([sys.executable, "-m", "neoaprs", "replay", "--pty", str(CAPTURE), "--interval", "0.05", "--loop"], cwd=ROOT, env=env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert replay.stdout is not None
    path = replay.stdout.readline().strip()
    assert path.startswith("/dev/pts/")
    time.sleep(0.3)                                                            # (nothing may be sent before a port opens it: the time is the point)
    port = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)              # a port opens it: until then nothing is sent
    heard = bytearray()
    try:
        deadline = time.monotonic() + 15
        while len(KissDecoder().feed(bytes(heard))) < 9 and time.monotonic() < deadline:      # more than the 4 frames of the file: it loops
            if select.select([port], [], [], 0.1)[0]:
                heard += os.read(port, 4096)
    finally:
        os.close(port)
    frames = KissDecoder().feed(bytes(heard))
    assert len(frames) >= 9 and [f.payload for f in frames[:4]] == [f.payload for f in KissDecoder().feed(CAPTURE.read_bytes())]
    replay.send_signal(signal.SIGINT)
    out, err = replay.communicate(timeout=10)
    assert replay.returncode == 0 and "waiting for a port to open" in err and "a port opened it" in err and "frame 9 sent" in err and "stopped" in err


def test_the_replay_refuses_a_file_that_is_not_there_or_holds_no_frame(tmp_path: Path) -> None:
    (tmp_path / "empty.bin").write_bytes(b"no frames here")
    for name, message in (("nothing.bin", "No such file"), ("empty.bin", "holds no KISS frame")):
        done = subprocess.run([sys.executable, "-m", "neoaprs", "replay", str(tmp_path / name)], cwd=ROOT, env=env(), capture_output=True, text=True, timeout=30)
        assert done.returncode == 1 and message in done.stderr and done.stdout == ""


def test_the_tool_sets_checks_and_reads_the_settings(tmp_path: Path) -> None:
    data = tmp_path / "data"
    assert tool(data, "list").returncode == 1, "reading makes no database"
    assert not data.exists()
    done = tool(data, "set", "station/call", "oh2gba-9")
    assert done.returncode == 0 and done.stdout.strip() == "station/call = OH2GBA-9"
    assert tool(data, "get", "station/call").stdout.strip() == "OH2GBA-9"
    assert tool(data, "get", "web/port").stdout.strip() == "7303"
    listing = tool(data, "list").stdout
    assert any(line.startswith("station/call") and line.endswith("stored") for line in listing.splitlines()) and any(line.startswith("web/port") and line.endswith("default") for line in listing.splitlines())
    bad = tool(data, "set", "web/port", "99999")
    assert bad.returncode == 2 and "web/port" in bad.stderr
    unknown = tool(data, "get", "neoaprs/web/colour")
    assert unknown.returncode == 2 and "no such setting" in unknown.stderr
    assert tool(data, "get", "station/call").stdout.strip() == "OH2GBA-9"
    assert tool(data, "stations").returncode == 0 and tool(data, "packets").stdout == ""


@posix_only      # (shell scripts)
def test_the_wrappers_of_the_scripts_call_the_command_with_the_data_folder_of_their_clone(tmp_path: Path) -> None:
    """The wrappers are run from a copy of scripts/ in a made-up clone, so that the data folder they name is the copy's and never the real clone's."""
    clone = tmp_path / "clone"
    (clone / "scripts").mkdir(parents=True)
    for name in ("neoaprs-db", "replay", "capture"):
        shutil.copy2(ROOT / "scripts" / name, clone / "scripts" / name)
    environment = {**env(), "NEOAPRS_PYTHON": sys.executable, "PYTHONPATH": str(ROOT)}

    def run(name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(clone / "scripts" / name), *args], cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=60)

    helped = run("neoaprs-db", "--help")
    assert helped.returncode == 0 and "neoaprs db" in helped.stdout and "stations" in helped.stdout
    replay = run("replay", "--help")
    assert replay.returncode == 0 and "neoaprs replay" in replay.stdout and "--loop" in replay.stdout
    capture = run("capture", "--help")
    assert capture.returncode == 0 and "neoaprs capture" in capture.stdout and "--seconds" in capture.stdout
    listing = run("neoaprs-db", "list")
    assert listing.returncode == 1 and str(clone / "data") in listing.stderr, "the data folder of the clone the script is in"
    mine = run("neoaprs-db", "--data", str(tmp_path / "mine"), "get", "web/port")
    assert mine.returncode == 1 and str(tmp_path / "mine") in mine.stderr, "a --data of your own wins over the clone's"
    assert run("neoaprs-db", "set", "station/call", "oh2gba").stdout.strip() == "station/call = OH2GBA" and run("neoaprs-db", "get", "station/call").stdout.strip() == "OH2GBA"
    assert (clone / "data" / "neoaprs.sqlite").is_file()
