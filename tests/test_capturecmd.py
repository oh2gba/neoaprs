"""`neoaprs capture` (neoaprs/cli/capturecmd.py) in the test's own process, on a fake radio: choosing the port to listen to, a port that goes away while it is recorded, a port that cannot be opened (and no file
left behind), and Ctrl-C. A whole run as a process, with the frames counted, is test_capture_records_a_tcp_tnc_into_a_file in tests/test_cli.py."""
import asyncio
from pathlib import Path

import pytest

from neoaprs import ax25, kiss
from neoaprs.cli import capturecmd
from tests.support.env import until
from tests.support.fakeradio import FakeRadio


def frame_bytes() -> bytes:
    return kiss.encode(ax25.encode(ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("OH2RDG"), (), info=b">on the air")))


@pytest.fixture
async def radio() -> FakeRadio:
    r = FakeRadio()
    await r.start()
    yield r
    await r.aclose()


# ---- which port

async def test_with_no_usb_serial_port_here_the_command_says_to_name_one(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(capturecmd, "can_search", lambda: False)
    assert await capturecmd.find_port(9600) is None
    assert "give the port with --port" in capsys.readouterr().err


async def test_the_first_port_that_delivers_a_kiss_frame_is_the_one(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(capturecmd, "can_search", lambda: True)
    monkeypatch.setattr(capturecmd, "searchable_ports", lambda pattern: (["/dev/ttyUSB7"], {"/dev/ttyACM9": "a board, not a radio"}))
    asked: list[tuple[list[str], int, float]] = []

    async def probe(paths: list[str], baud: int, seconds: float, accept: object) -> str:
        asked.append((paths, baud, seconds))
        assert callable(accept) and accept(frame_bytes()) and not accept(b"noise"), "a complete KISS frame is what a radio on that port would say"
        return paths[0]
    monkeypatch.setattr(capturecmd, "probe", probe)
    assert await capturecmd.find_port(1200) == "/dev/ttyUSB7"
    assert asked == [(["/dev/ttyUSB7"], 1200, capturecmd.PROBE_SECONDS)]
    err = capsys.readouterr().err
    assert "skipping /dev/ttyACM9: a board, not a radio" in err and "listening for a KISS frame on /dev/ttyUSB7" in err


async def test_when_no_port_delivers_a_frame_the_command_says_so_and_suggests_port(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(capturecmd, "can_search", lambda: True)
    monkeypatch.setattr(capturecmd, "searchable_ports", lambda pattern: (["/dev/ttyUSB7"], {}))

    async def probe(*args: object) -> None:
        return None
    monkeypatch.setattr(capturecmd, "probe", probe)
    args = capturecmd.parse(["out.bin"])
    assert await capturecmd.run(args) == 1
    assert "no port delivered a KISS frame" in capsys.readouterr().err


# ---- the recording

async def test_a_port_that_goes_away_ends_the_recording_with_exit_1_and_keeps_what_came(radio: FakeRadio, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out.bin"
    recording = asyncio.ensure_future(capturecmd.record(radio.url, 9600, 30.0, str(out)))
    await radio.connected()
    radio.feed(frame_bytes())
    await until(lambda: out.exists() and out.stat().st_size >= len(frame_bytes()), 10)   # (a busy Windows runner can be slow)
    radio.drop()
    assert await asyncio.wait_for(recording, 10) == 1
    assert out.read_bytes() == frame_bytes()
    err = capsys.readouterr().err
    assert "the port went away" in err and "1 KISS frames" in err and "frame 1: port 0 command 0" in err


async def test_a_port_that_cannot_be_opened_is_told_and_leaves_no_file(radio: FakeRadio, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    radio.refuse()
    out = tmp_path / "out.bin"
    assert await capturecmd.record(radio.url, 9600, 1.0, str(out)) == 1
    assert not out.exists() and capsys.readouterr().err.startswith("capture: ")


async def test_a_recording_that_runs_its_time_out_is_a_success(radio: FakeRadio, tmp_path: Path) -> None:
    out = tmp_path / "out.bin"
    recording = asyncio.ensure_future(capturecmd.record(radio.url, 9600, 2.0, str(out)))     # (time for a busy Windows runner to pass the bytes on)
    await radio.connected()
    radio.feed(b"\x00partial")
    assert await asyncio.wait_for(recording, 10) == 0
    assert out.read_bytes() == b"\x00partial"


def test_ctrl_c_ends_the_command_with_the_bytes_that_came_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def interrupted(coroutine: object) -> int:
        coroutine.close()
        raise KeyboardInterrupt
    monkeypatch.setattr(asyncio, "run", interrupted)
    assert capturecmd.main([str(tmp_path / "out.bin"), "--port", "socket://127.0.0.1:9"]) == 0
    assert f"what came is in {tmp_path / 'out.bin'}" in capsys.readouterr().err
