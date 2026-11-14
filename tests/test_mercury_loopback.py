"""The Mercury NeoAPRS ships listens on this computer only: the program built by scripts/build-mercury (packaging/mercury/loopback.patch on the pinned source) is started once on its fifo backend, and its four TCP
ports, the KISS broadcast port, the control port and the ARQ data port and the UI interface's, are each bound to 127.0.0.1 and nothing else in the kernel's table of sockets. Mercury has no password on those ports: one that listened on every
interface would let any host on the LAN key the radio past every interlock of the daemon, which is why the daemon too refuses such a program (tests/test_mercury_modem.py). Runs where the built program is (a checkout after
`scripts/build-mercury --install`, the `sim` stage, the release's checks) and is skipped elsewhere; also holds the patch file and the build script to what they say."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from neoaprs.mercuryhelper import LOOPBACK_HEX, _listeners, _free, environment, find, free_ports
from tests.conftest import ROOT

PATCH = ROOT / "packaging" / "mercury" / "loopback.patch"
SCRIPT = ROOT / "scripts" / "build-mercury"


def test_the_patch_binds_both_listeners_to_the_loopback_and_the_build_applies_and_checks_it() -> None:
    text = PATCH.read_text(encoding="utf-8")
    assert text.count("-    local_addr.sin_addr.s_addr = INADDR_ANY;") == 2 and text.count("+    local_addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);") == 2, "the two binds of Mercury 1.9.24, and nothing else"
    assert text.count("--- a/data_interfaces/tcp_interfaces.c") == 1 and "+++ b/data_interfaces/tcp_interfaces.c" in text
    script = SCRIPT.read_text(encoding="utf-8")
    assert "loopback.patch" in script and '"patch", "-p1"' in script and "INADDR_ANY" in script, "applied before the build, and the file checked after it"
    assert "def check_loopback" in script and "/proc/net/tcp" in script, "the built program is started and its ports read from the kernel's table"
    assert "loopback.patch" in script[script.index("SOURCE.txt"):], "the source offer names the change (GPL)"


def test_the_shipped_mercury_listens_on_the_loopback_only(tmp_path: Path) -> None:
    program = find()
    if program is None or sys.platform != "linux" or not Path("/proc/net/tcp").is_file():
        pytest.skip("the built Mercury (scripts/build-mercury --install) and the kernel's table of sockets are needed")
    broadcast, control = free_ports(18500, 40)
    ui = next(port for port in range(17500, 17540) if _free(port))                  # (below the ports of the test workers, which begin at 20000: tests/test_mercury_modem.py)
    ports = (broadcast, control, control + 1, ui)
    capture, playback, ini = tmp_path / "capture", tmp_path / "playback", tmp_path / "mercury.ini"
    os.mkfifo(capture)
    os.mkfifo(playback)
    ini.write_text(f"[store]\nenabled = false\n[main]\nui_enabled = true\nui_port = {ui}\nwaterfall_enabled = false\n", encoding="utf-8")
    argv = [*program, "-C", str(ini), "-m", "1", "-x", "fifo", "-i", str(capture), "-o", str(playback), "-b", str(broadcast), "-p", str(control), "-P", "none"]
    child = subprocess.Popen(argv, cwd=str(tmp_path), env=environment(program), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 30.0
        while True:
            tables = [Path(name).read_text(encoding="ascii") for name in ("/proc/net/tcp", "/proc/net/tcp6") if Path(name).is_file()]
            found = _listeners(tables, ports)
            if set(found) == set(ports) or time.monotonic() > deadline or child.poll() is not None:
                break
            time.sleep(0.2)
    finally:
        child.terminate()
        try:
            child.wait(10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
    assert set(found) == set(ports), f"the program listens on its four ports (the UI interface's included) (found {found}; exit {child.returncode})"
    assert all(addresses == {LOOPBACK_HEX[0]} for addresses in found.values()), f"each on 127.0.0.1 and nowhere else: {found}"
