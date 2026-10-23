"""The pseudo-terminal of `neoaprs replay --pty` (neoaprs/cli/replaypty.py) in the test's own process: what the other end writes is shown while the replay waits, a frame is dropped where nobody reads, and the replay
ends with Ctrl-C. A whole replay on a pseudo-terminal, read by a port, is in tests/test_replay.py and tests/test_scripts.py."""
import os
from collections.abc import Iterator

import pytest

from neoaprs.cli import replaypty
from neoaprs.cli.replaypty import Line, play_on_pty
from tests.support.ptyline import Ptys, posix_only

pytestmark = posix_only


def test_what_the_other_end_writes_is_shown_while_the_replay_waits(ptys: Ptys, capsys: pytest.CaptureFixture[str]) -> None:
    master, path = ptys()
    os.set_blocking(master, False)
    port = os.open(path, os.O_RDWR | os.O_NOCTTY)
    try:
        os.write(port, b"KISS ON\r")
        Line(master).pause(0.3)
    finally:
        os.close(port)
    assert "the daemon wrote 8 bytes: b'KISS ON\\r'" in capsys.readouterr().err


def test_a_frame_goes_to_the_port_that_has_the_line_open(ptys: Ptys, capsys: pytest.CaptureFixture[str]) -> None:
    master, path = ptys()
    os.set_blocking(master, False)
    line = Line(master)
    assert line.is_open()
    port = os.open(path, os.O_RDWR | os.O_NOCTTY)
    try:
        line.send(b"\xc0\x00hi\xc0", 1)
        assert os.read(port, 100) == b"\xc0\x00hi\xc0"
    finally:
        os.close(port)
    assert "frame 1 sent (5 bytes)" in capsys.readouterr().err


@pytest.mark.parametrize("error, told", [(BlockingIOError(), "frame 2 dropped: the pseudo-terminal is full, nobody reads it"), (OSError("Input/output error"), "frame 2 not sent: Input/output error")])
def test_a_frame_that_cannot_be_written_is_told_not_raised(ptys: Ptys, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], error: OSError, told: str) -> None:
    master, _ = ptys()
    line = Line(master)

    def refuse(fd: int, data: bytes) -> int:
        raise error
    monkeypatch.setattr(replaypty.os, "write", refuse)
    line.send(b"x", 2)
    assert told in capsys.readouterr().err


@pytest.fixture
def close_the_masters(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """play_on_pty never closes its pseudo-terminal (the process ends with Ctrl-C): the test does."""
    masters: list[int] = []
    real = os.openpty

    def openpty() -> tuple[int, int]:
        pair = real()
        masters.append(pair[0])
        return pair
    monkeypatch.setattr(os, "openpty", openpty)
    yield
    for master in masters:
        os.close(master)


class FakeLine:
    """The line of a replay that nobody reads: it writes down the frames and ends the replay (Ctrl-C) after so many pauses."""

    made: "FakeLine"

    def __init__(self, master: int, pauses: int = 4) -> None:
        self.sent: list[tuple[bytes, int]] = []
        self.pauses: list[float] = []
        self.stop_after = pauses
        FakeLine.made = self

    def send(self, frame: bytes, number: int) -> None:
        self.sent.append((frame, number))

    def pause(self, seconds: float) -> None:
        self.pauses.append(seconds)
        if len(self.pauses) >= self.stop_after:
            raise KeyboardInterrupt


def test_the_file_is_played_once_and_the_replay_waits_for_ctrl_c(close_the_masters: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(replaypty, "Line", lambda master: FakeLine(master, pauses=3))
    assert play_on_pty([b"a", b"b"], 0.5, loop=False) == 0
    line = FakeLine.made
    assert line.sent == [(b"a", 1), (b"b", 2)] and line.pauses == [0.5, 0.5, 1.0], "a pause after each frame, then the waiting for Ctrl-C"
    captured = capsys.readouterr()
    assert captured.out.startswith("/dev/pts/") and "the file is played; Ctrl-C ends it" in captured.err and "replay: stopped" in captured.err


def test_a_looping_replay_plays_the_frames_again_and_again(close_the_masters: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(replaypty, "Line", lambda master: FakeLine(master, pauses=5))
    assert play_on_pty([b"a", b"b"], 0.1, loop=True) == 0
    assert FakeLine.made.sent == [(b"a", 1), (b"b", 2), (b"a", 3), (b"b", 4), (b"a", 5)]
    assert "the file is played" not in capsys.readouterr().err
