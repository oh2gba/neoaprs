"""The Direwolf program as a child of the daemon: where it is, how a run is read and stopped.

Only the shipped Direwolf is used, never one from the PATH, and it runs in its own folder so that
it reads its own device and symbol lists first (deviceid.c:229-243, symbols.c:267-279).
"""
import asyncio
import contextlib
import logging
import os
import signal
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from . import childprogram
from .bundled import tools_dir
from .childprogram import Command
from .direwolf import CONF_FILE, is_error, kiss_dump, level_now_of
from .signal import Signal

log = logging.getLogger("neoaprs.direwolf")
direwolf_log = logging.getLogger("neoaprs.direwolf.program")

NAME = "direwolf"
# Time to end after the input closes, and again after SIGINT (its cleanup sleeps one second).
STOP_WAIT_SEC = 3.0


def program_file(system: str | None = None) -> str:
    return childprogram.program_file(NAME, system)


def expected_program(tools: Path | None = None) -> Path:
    return (tools if tools is not None else tools_dir()) / NAME / program_file()


def find(tools: Path | None = None) -> Command | None:
    """Return the shipped Direwolf, or None if this installation has none."""
    return childprogram.found(expected_program(tools))


def is_shipped(command: Command, tools: Path | None = None) -> bool:
    return childprogram.runs_shipped(command, expected_program(tools))


def working_folder(command: Command, home: Path) -> Path:
    return Path(command[0]).parent if len(command) == 1 else home


def is_ours(pid: int, conf: Path, tools: Path | None = None, written: float | None = None) -> bool:
    """Return True if process `pid` is our Direwolf for `conf`.

    On Windows (no command lines) the image must be the shipped one, started before `written`."""
    cmdline = Path(f"/proc/{pid}/cmdline")
    if cmdline.exists():
        try:
            args = cmdline.read_bytes().decode("utf-8", "replace").split("\0")
        except OSError:
            return False
        return any(flag == "-c" and value in (str(conf), str(conf.resolve())) for flag, value in zip(args, args[1:], strict=False))
    return (sys.platform == "win32" and written is not None and childprogram._running_windows(pid) and is_shipped_image(childprogram._windows_image(pid), tools)
            and childprogram.made_before(childprogram.windows_created(pid), written))


def is_shipped_image(image: str | None, tools: Path | None = None) -> bool:
    return image is not None and os.path.normcase(os.path.abspath(image)) == os.path.normcase(str(expected_program(tools).resolve()))


def end_stale(pid_file: Path) -> bool:
    """End a Direwolf an earlier daemon left running for this radio; return whether one ended."""
    conf = pid_file.parent / CONF_FILE
    return childprogram.end_stale(pid_file, lambda pid, written: is_ours(pid, conf, written=written), "Direwolf", signal.SIGINT if sys.platform != "win32" else signal.SIGTERM, STOP_WAIT_SEC)


class LevelNow:
    """The latest `-R` receive level; None while no run reports one."""

    def __init__(self) -> None:
        self.value: int | None = None
        self.changed: Signal[[int | None]] = Signal("direwolf.level_now")

    def said(self, value: int | None) -> None:
        if value != self.value:
            self.value = value
            self.changed.emit(value)


class Program(childprogram.Program):
    """One run of Direwolf with a pipe as input; level reports go to `level_now`."""
    name = "Direwolf"

    def __init__(self, on_ended: Callable[[int | None, list[str]], None], on_line: Callable[[str], None] | None = None) -> None:
        super().__init__(on_ended, log, direwolf_log, stdin_pipe=True)
        self._on_line = on_line
        self.level_now = LevelNow()

    def _heard(self, line: str, loop: asyncio.AbstractEventLoop) -> None:
        if (level := level_now_of(line)) is not None:
            _on_loop(loop, self.level_now.said, level)
        elif self._on_line is not None:
            loop.call_soon_threadsafe(self._on_line, line)

    def _read(self, process: subprocess.Popen[str], loop: asyncio.AbstractEventLoop, pid_file: Path | None = None) -> None:
        super()._read(process, loop, pid_file)
        # A finished run has no level, but an older run's reader must not clear the current one.
        if self._process in (None, process):
            _on_loop(loop, self.level_now.said, None)

    def _warning(self, line: str) -> str | None:
        return line if is_error(line) else None

    def _unlogged(self, line: str) -> bool:
        # Frame dumps duplicate the packet log; level lines are too frequent.
        return kiss_dump(line) or level_now_of(line) is not None

    def _end(self, process: subprocess.Popen[str]) -> None:
        """Close its input (`-Q`), then SIGINT (direwolf.c:341), then kill."""
        self.close_input(process)
        if childprogram.waited(process, STOP_WAIT_SEC):
            return
        if sys.platform == "win32":
            childprogram.end_tree(process, STOP_WAIT_SEC)
        elif not self.ask(process, signal.SIGINT, STOP_WAIT_SEC):
            self.kill(process)


def _on_loop(loop: asyncio.AbstractEventLoop, call: Callable[[int | None], None], value: int | None) -> None:
    with contextlib.suppress(RuntimeError):
        loop.call_soon_threadsafe(call, value)
