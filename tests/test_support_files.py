"""The reading of a file that a program is still writing (tests/support/files.py): a file that is there is not a file that is written, and a file the system refuses to open (Windows, while the writer or the move that
puts it in place holds it) is a file that is not ready."""
import asyncio
import threading
import time
from pathlib import Path

import pytest

from tests.support.env import START_SEC
from tests.support.files import read_when, text_if_readable, until_written, whole_lines


def test_a_file_that_is_missing_or_refused_is_not_ready_and_a_file_is_its_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "out.txt"
    assert text_if_readable(path) is None
    path.write_text("a\n", encoding="utf-8")
    assert text_if_readable(path) == "a\n"

    def refused(self: Path, *args: object, **kwargs: object) -> str:
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(Path, "read_text", refused)
    assert text_if_readable(path) is None


def test_the_text_is_waited_for_until_it_is_whole_and_not_only_until_the_file_is_there(tmp_path: Path) -> None:
    path = tmp_path / "out.txt"
    path.write_text("one\ntw", encoding="utf-8")                          # (there, and not finished)

    def finish() -> None:
        time.sleep(0.1)
        path.write_text("one\ntwo\n", encoding="utf-8")
    writer = threading.Thread(target=finish)
    writer.start()
    try:
        assert read_when(path).splitlines() == ["one", "two"]
    finally:
        writer.join()


def test_a_file_that_is_refused_for_a_while_is_read_when_it_is_let_go(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "out.txt"
    path.write_text("done\n", encoding="utf-8")
    real = Path.read_text
    refusals = [3]

    def sometimes_refused(self: Path, *args: object, **kwargs: object) -> str:
        if refusals[0] > 0:
            refusals[0] -= 1
            raise PermissionError(13, "Permission denied")
        return real(self, *args, **kwargs)                                  # type: ignore[arg-type]
    monkeypatch.setattr(Path, "read_text", sometimes_refused)
    assert read_when(path) == "done\n" and refusals == [0]


async def test_the_loop_goes_on_while_a_file_is_waited_for_and_what_never_comes_fails_with_what_there_was(tmp_path: Path) -> None:
    path = tmp_path / "out.txt"
    ticks = 0

    async def count() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    async def write_later() -> None:
        await asyncio.sleep(0.1)
        path.write_text("x\n", encoding="utf-8")
    counting = asyncio.create_task(count())
    writing = asyncio.create_task(write_later())
    try:
        assert await until_written(path, lambda text: text == "x\n") == "x\n" and ticks > 3
        path.write_text("half", encoding="utf-8")
        with pytest.raises(AssertionError, match="was not written in 0.2 s; what it had: 'half'"):
            await until_written(path, whole_lines, 0.2)
    finally:
        counting.cancel()
        await writing


def test_the_wait_for_a_started_program_is_longer_than_a_busy_runner_needs() -> None:
    assert START_SEC >= 30
