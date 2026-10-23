"""`neoaprs replay` over TCP: a capture played as a KISS TNC on a port of the loopback, read by the real Tnc of the daemon (the kiss profile, `socket://`) in the test, and as a process by a plain socket. The pseudo-terminal
mode and the whole daemon on a replay are in tests/test_scripts.py."""
import asyncio
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from neoaprs import ax25, kiss
from neoaprs.cli import replaycmd
from neoaprs.cli.replaycmd import Replay, frames_of
from neoaprs.packet import Packet
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from tests.conftest import ROOT
from tests.support.env import until
from tests.support.files import FIXTURES
from tests.support.proc import NEW_GROUP, interrupt

CAPTURE = FIXTURES / "kiss" / "thd7-2026-10-21.bin"
FRAMES = frames_of(CAPTURE.read_bytes())
EXPECTED_SOURCES = [f"{a.call}-{a.ssid}" if a.ssid else a.call for a in (ax25.decode(f.payload).source for f in kiss.KissDecoder().feed(CAPTURE.read_bytes()))]


async def start(replay: Replay) -> tuple["asyncio.Task[None]", int]:
    """The replay serving on a free port, and the port."""
    port: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    replay.ready = port.set_result
    task = asyncio.create_task(replay.run())
    return task, await asyncio.wait_for(port, 5)


async def stop(task: "asyncio.Task[None]") -> None:
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


def test_the_frames_are_the_frames_of_the_capture_encoded_again() -> None:
    assert len(FRAMES) == 4
    assert [f.payload for fr in FRAMES for f in kiss.KissDecoder().feed(fr)] == [f.payload for f in kiss.KissDecoder().feed(CAPTURE.read_bytes())]
    assert frames_of(b"no frames here") == []


async def test_a_tnc_that_connects_hears_the_capture_as_packets_one_frame_at_a_time() -> None:
    replay = Replay(FRAMES, interval=0.05, settle_sec=1.0)       # longer than the Tnc's entry into KISS, in which what it hears is thrown away (each frame is sent once)
    task, port = await start(replay)
    tnc = Tnc(f"socket://127.0.0.1:{port}", check_sec=0.0, settle_sec=0.05, backoff=Backoff([0.05, 0.05]), fallback_probe=False)
    heard: list[Packet] = []
    tnc.packet.connect(heard.append)
    try:
        assert replay.sent == 0, "nothing is sent while nobody is connected"
        await tnc.start()
        assert tnc.state is Source.State.CONNECTED, tnc.problem
        await until(lambda: len(heard) == 4)
        assert [p.source for p in heard] == EXPECTED_SOURCES
        assert replay.sent == 4 and len(replay.clients) == 1
    finally:
        await tnc.stop()
        await stop(task)


async def test_nothing_is_sent_until_a_client_is_there_and_the_frames_go_on_for_the_next_one() -> None:
    replay = Replay(FRAMES, interval=0.1, settle_sec=0.0)
    task, port = await start(replay)
    try:
        await asyncio.sleep(0.2)
        assert replay.sent == 0
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        first = await asyncio.wait_for(reader.readexactly(len(FRAMES[0])), 5)
        assert first == FRAMES[0]
        writer.close()
        await writer.wait_closed()
        await until(lambda: not replay.clients)
        await asyncio.sleep(0.3)
        sent = replay.sent
        assert 1 <= sent < 4
        await asyncio.sleep(0.3)
        assert replay.sent == sent, "with nobody connected it waits where it was"
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        again = await asyncio.wait_for(reader.readexactly(len(FRAMES[sent])), 5)
        assert again == FRAMES[sent], "and goes on from there when somebody connects"
        writer.close()
        await writer.wait_closed()
    finally:
        await stop(task)


async def test_with_loop_the_file_starts_again_and_what_the_daemon_writes_is_shown(capsys: pytest.CaptureFixture[str]) -> None:
    replay = Replay(FRAMES, interval=0.01, loop=True, settle_sec=0.0)
    task, port = await start(replay)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        data = b""
        while len(kiss.KissDecoder().feed(data)) < 9:
            data += await asyncio.wait_for(reader.read(4096), 5)
        writer.write(b"\rKISS ON\r")
        await writer.drain()
        shown = ""

        def written() -> bool:
            nonlocal shown
            shown += capsys.readouterr().err
            return "the daemon wrote 9 bytes" in shown

        await until(written)
        writer.close()
        await writer.wait_closed()
    finally:
        await stop(task)


async def test_it_listens_on_the_loopback_only_and_a_port_that_is_taken_is_an_error_of_the_caller() -> None:
    replay = Replay(FRAMES, interval=0.05)
    task, port = await start(replay)
    try:
        sock = replay_socket_name(port)
        assert sock[0] == "127.0.0.1"
        taken = Replay(FRAMES, interval=0.05, port=port)
        with pytest.raises(OSError):
            await asyncio.wait_for(taken.run(), 5)
    finally:
        await stop(task)


def replay_socket_name(port: int) -> tuple[str, int]:
    with socket.create_connection(("127.0.0.1", port)) as c:
        return c.getpeername()[:2]


def test_as_a_process_it_prints_the_address_and_plays_to_a_plain_socket_and_ends_on_ctrl_c() -> None:
    proc = subprocess.Popen([sys.executable, "-m", "neoaprs", "replay", str(CAPTURE), "--interval", "0.05", "--loop"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NEW_GROUP)
    try:
        assert proc.stdout is not None
        address = proc.stdout.readline().strip()
        assert address.startswith("socket://127.0.0.1:")
        port = int(address.rsplit(":", 1)[1])
        data = b""
        deadline = time.monotonic() + 20
        with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
            while len(kiss.KissDecoder().feed(data)) < 9 and time.monotonic() < deadline:
                data += client.recv(4096)
        frames = kiss.KissDecoder().feed(data)
        assert len(frames) >= 9 and [f.payload for f in frames[:4]] == [f.payload for f in kiss.KissDecoder().feed(CAPTURE.read_bytes())]
    finally:
        interrupt(proc)
        try:
            out, err = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise AssertionError(f"the replay did not end 30 s after the interrupt; it said: {proc.communicate()[1]}") from None
    assert proc.returncode == 0 and "waiting for a port to connect" in err and "a port connected" in err and "frame 9 sent" in err and "stopped" in err


def test_the_sample_capture_of_the_package_is_the_capture_of_the_tests_and_is_played_when_no_file_is_named() -> None:
    assert replaycmd.SAMPLE.read_bytes() == CAPTURE.read_bytes(), "neoaprs/samples/thd7.kiss is a copy of tests/fixtures/kiss/thd7-2026-10-21.bin"
    proc = subprocess.Popen([sys.executable, "-m", "neoaprs", "replay", "--interval", "0.05"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NEW_GROUP)
    try:
        assert proc.stdout is not None
        address = proc.stdout.readline().strip()
        assert address.startswith("socket://127.0.0.1:")
        data = b""
        deadline = time.monotonic() + 20
        with socket.create_connection(("127.0.0.1", int(address.rsplit(":", 1)[1])), timeout=5) as client:
            while len(kiss.KissDecoder().feed(data)) < 4 and time.monotonic() < deadline:
                data += client.recv(4096)
        assert [f.payload for f in kiss.KissDecoder().feed(data)] == [f.payload for f in kiss.KissDecoder().feed(CAPTURE.read_bytes())]
    finally:
        interrupt(proc)
        out, err = proc.communicate(timeout=30)
    assert proc.returncode == 0 and "4 frames from" in err and "thd7.kiss" in err


def test_a_file_that_is_not_there_or_holds_no_frame_is_refused(tmp_path: Path) -> None:
    (tmp_path / "empty.bin").write_bytes(b"no frames here")
    assert replaycmd.main([str(tmp_path / "nothing.bin")]) == 1
    assert replaycmd.main([str(tmp_path / "empty.bin")]) == 1


def test_the_parser_takes_the_options_of_the_command() -> None:
    args = replaycmd.parser().parse_args(["capture.bin", "--interval", "0.5", "--loop", "--port", "8001", "--pty"])
    assert (args.file, args.interval, args.loop, args.port, args.pty) == ("capture.bin", 0.5, True, 8001, True)
    defaults = replaycmd.parser().parse_args(["capture.bin"])
    assert (defaults.interval, defaults.loop, defaults.port, defaults.pty) == (2.0, False, 0, False)
