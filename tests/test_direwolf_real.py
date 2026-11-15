"""The Direwolf that scripts/build-direwolf --install builds into the venv, run by the test itself and never by a daemon, with no sound card: on its UDP audio input with -Q it listens on 127.0.0.1 alone and ends
with "PTT 0 = 0", "QRT" and exit 0 within 3 s of its input closing; on audio read from its standard input (`ADEVICE stdin null`) it decodes the frames its own gen_packets made, as many as its own atest decodes of
them, and hands each to its KISS client. No configuration has a PTT line (`PTT CM108` would walk the HID devices of the machine). Skipped where the venv has no such Direwolf (a checkout that has not built it),
and off Linux (the kernel's table of sockets)."""
import asyncio
import subprocess
import sys
import time
from pathlib import Path

import pytest

from neoaprs import kiss
from neoaprs.bundled import tools_dir
from neoaprs.childprogram import environment

FOLDER = tools_dir() / "direwolf"
PROGRAM = FOLDER / "direwolf"
pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux") or not (PROGRAM.is_file() and (FOLDER / "dev" / "gen_packets").is_file()),
                                reason="the Direwolf that scripts/build-direwolf --install builds, and the kernel's table of sockets, are needed")
LOOPBACK = "0100007F"


def _bound(port: int, tables: tuple[str, ...]) -> set[str]:
    found: set[str] = set()
    for name in tables:
        for line in Path(name).read_text(encoding="ascii").splitlines()[1:]:
            fields = line.split()
            address, _, at = fields[1].rpartition(":")
            if int(at, 16) == port and ("/tcp" not in name or fields[3] == "0A"):
                found.add(address)
    return found


def _conf(folder: Path, adevice: str, port: int) -> Path:
    conf = folder / "direwolf.conf"
    conf.write_text(f"ADEVICE {adevice}\nACHANNELS 1\nCHANNEL 0\nMODEM 1200\nKISSPORT 0\nKISSPORT {port}\nAGWPORT 0\nDNSSD 0\n", encoding="utf-8")
    return conf


def _start(folder: Path, conf: Path, *extra: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen([str(PROGRAM), "-c", str(conf), "-t", "0", "-q", "d", "-d", "o", *extra], cwd=folder, env=environment([str(PROGRAM)]), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def test_closing_its_input_ends_it_cleanly_and_it_listens_on_this_computer_only(tmp_path: Path) -> None:
    udp, port = 17311, 17411
    child = _start(tmp_path, _conf(tmp_path, f"udp:{udp} null", port), "-Q")
    try:
        deadline = time.monotonic() + 30
        while not _bound(port, ("/proc/net/tcp", "/proc/net/tcp6")) and time.monotonic() < deadline and child.poll() is None:
            time.sleep(0.2)
        assert _bound(port, ("/proc/net/tcp", "/proc/net/tcp6")) == {LOOPBACK} and _bound(udp, ("/proc/net/udp", "/proc/net/udp6")) == {LOOPBACK}
        assert child.stdin is not None
        child.stdin.close()
        closed = time.monotonic()
        output = child.communicate(timeout=10)[0].decode("utf-8", "replace")
        assert child.returncode == 0 and "PTT 0 = 0" in output and "QRT" in output and time.monotonic() - closed < 3.0, output
    finally:
        if child.poll() is None:
            child.kill()


async def test_it_decodes_the_frames_of_its_own_gen_packets_and_hands_each_to_its_kiss_client(tmp_path: Path) -> None:
    wav = tmp_path / "sample.wav"
    subprocess.run([str(FOLDER / "dev" / "gen_packets"), "-o", str(wav)], cwd=tmp_path, check=True, capture_output=True, timeout=60)
    counted = subprocess.run([str(FOLDER / "dev" / "atest"), str(wav)], cwd=tmp_path, check=False, capture_output=True, text=True, timeout=60).stdout
    expected = int(next(line.split()[0] for line in counted.splitlines() if "packets decoded" in line))
    assert expected > 0
    port = 17421
    child = _start(tmp_path, _conf(tmp_path, "stdin null", port))
    try:
        assert child.stdout is not None and child.stdin is not None
        while b"Ready to accept KISS TCP client" not in await asyncio.to_thread(child.stdout.readline):
            assert child.poll() is None, "it ended before it listened"
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        await asyncio.to_thread(child.stdin.write, wav.read_bytes()[44:])                  # (the samples, without the WAV header)
        await asyncio.to_thread(child.stdin.flush)
        frames: list[kiss.KissFrame] = []
        decoder = kiss.KissDecoder()
        deadline = asyncio.get_running_loop().time() + 60
        while len(frames) < expected and asyncio.get_running_loop().time() < deadline:
            data = await asyncio.wait_for(reader.read(4096), 60)
            frames += decoder.feed(data)
        writer.close()
        child.stdin.close()
        assert len(frames) == expected and child.wait(10) == 0
    finally:
        if child.poll() is None:
            child.kill()
