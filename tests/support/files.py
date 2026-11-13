"""The files under tests/fixtures (captured frames and streams of the radio, and the parser's cases), and the reading of a file that a program of the test is writing."""
import asyncio
import time
from collections.abc import Callable
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
WRITTEN_SEC = 60.0          # the longest a test waits for a program to finish a file: a limit, not a measure (a command that PowerShell starts on a busy Windows runner takes over 20 s)


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def whole_lines(text: str) -> bool:
    """A file that has something in it and ends with its last line: what a program that writes lines has finished with."""
    return text.endswith("\n")


def text_if_readable(path: Path) -> str | None:
    """What is in the file now, or None when it is not there or cannot be opened (Windows refuses a file that the program writing it, or moving it into place, still holds: that is a file not ready, not a failure)."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def read_when(path: Path, complete: Callable[[str], bool] = whole_lines, seconds: float = WRITTEN_SEC) -> str:
    """The text of the file once it can be read and `complete` says it holds what the test asserts on. A file that exists is not a file that is written: wait for the content, not for the name."""
    deadline = time.monotonic() + seconds
    while (text := text_if_readable(path)) is None or not complete(text):
        assert time.monotonic() < deadline, f"{path.name} was not written in {seconds:g} s; what it had: {text!r}"
        time.sleep(0.01)
    return text


async def until_written(path: Path, complete: Callable[[str], bool] = whole_lines, seconds: float = WRITTEN_SEC) -> str:
    """`read_when` for a test that runs on the loop: the loop goes on while it waits."""
    deadline = asyncio.get_running_loop().time() + seconds
    while (text := text_if_readable(path)) is None or not complete(text):
        assert asyncio.get_running_loop().time() < deadline, f"{path.name} was not written in {seconds:g} s; what it had: {text!r}"
        await asyncio.sleep(0.01)
    return text
