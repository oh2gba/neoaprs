"""The Direwolf program as a child of the daemon: where it is, how one run of it is read and how it is stopped (childprogram.py holds what every program the daemon holds shares).

Direwolf is the one NeoAPRS ships (bundled.py says where): the folder `direwolf/` of the shipped programs, with the program, its licences, its two data files and on Linux its own ALSA and udev libraries and the ALSA
configuration, and never one found on the PATH or fetched. It is run in that folder (`working_folder`), so that it reads the device and symbol lists it carries before any a system Direwolf has (deviceid.c:229-243,
symbols.c:267-279).

It is stopped by its own clean way: its standard input is a pipe, and closing it ends the program as a Ctrl-C does (`-Q`, packaging/direwolf/quit.patch: "QRT", every keying output set to 0, a second, exit 0);
then SIGINT on POSIX, the one signal Direwolf cleans up on (direwolf.c:341); then the kill (`taskkill /T /F` on Windows). A daemon that dies closes the pipe too, so its Direwolf unkeys and ends by itself."""
import asyncio
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
from .direwolf import CONF_FILE, is_error, kiss_dump

log = logging.getLogger("neoaprs.direwolf")
direwolf_log = logging.getLogger("neoaprs.direwolf.program")       # what Direwolf itself prints, one line each

NAME = "direwolf"
STOP_WAIT_SEC = 3.0                  # how long Direwolf is given to end after its input closes, and again after SIGINT (its cleanup sleeps one second)


def program_file(system: str | None = None) -> str:
    return f"{NAME}.exe" if (system or sys.platform).startswith("win") else NAME


def expected_program(tools: Path | None = None) -> Path:
    """Where the shipped Direwolf is looked for: `direwolf/direwolf[.exe]` in the folder of the shipped programs."""
    return (tools if tools is not None else tools_dir()) / NAME / program_file()


def find(tools: Path | None = None) -> Command | None:
    """The Direwolf NeoAPRS ships; None when this installation has none (a wheel installed with pip, a Mac: the AppImage, the .deb and the Windows installer carry it)."""
    program = expected_program(tools)
    return [str(program)] if program.is_file() and os.access(program, os.X_OK) else None


def is_shipped(command: Command, tools: Path | None = None) -> bool:
    """Whether the command is the Direwolf NeoAPRS ships (not the tests' fake, an interpreter and a module)."""
    return len(command) == 1 and Path(command[0]).resolve() == expected_program(tools).resolve()


def working_folder(command: Command, home: Path) -> Path:
    """Where a run of the program works: the program's own folder, whose data files it reads before any a system Direwolf has (a command that is an interpreter and a module, the tests' fake, works in the
    radio's folder `home`)."""
    return Path(command[0]).parent if len(command) == 1 else home


def is_ours(pid: int, conf: Path, tools: Path | None = None, written: float | None = None) -> bool:
    """Whether the process of this id is a run of ours for the radio whose configuration is `conf`: on Linux its command line names that configuration after `-c` (an operator's own Direwolf has its own); on
    Windows, where a command line cannot be read, it is running, its program file is the shipped one (an own direwolf.exe is elsewhere) and it was made no later than the pid file that names it was `written`
    (every radio runs that one program file: another radio's Direwolf that got the id later, after a reboot most of all, is not this radio's); elsewhere nothing is known, and nothing is ended."""
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
    """Whether the program file at this Windows path is the Direwolf NeoAPRS ships, the case aside; no when the path is not known."""
    return image is not None and os.path.normcase(os.path.abspath(image)) == os.path.normcase(str(expected_program(tools).resolve()))


def end_stale(pid_file: Path) -> bool:
    """Ends a Direwolf of ours that an earlier daemon left running for this radio (its pid file and its configuration are in the radio's folder) by SIGINT, its clean end (the hard end on Windows), and waits up to
    STOP_WAIT_SEC for it to be gone, so that the start that follows finds its sound card free; whether one was ended."""
    conf = pid_file.parent / CONF_FILE
    return childprogram.end_stale(pid_file, lambda pid, written: is_ours(pid, conf, written=written), "Direwolf", signal.SIGINT if sys.platform != "win32" else signal.SIGTERM, STOP_WAIT_SEC)


class Program(childprogram.Program):
    """One run of Direwolf: started with a pipe as its input, read, every line handed to the loop (`on_line`), and told when it ends."""
    name = "Direwolf"

    def __init__(self, on_ended: Callable[[int | None, list[str]], None], on_line: Callable[[str], None] | None = None) -> None:
        super().__init__(on_ended, log, direwolf_log, stdin_pipe=True)
        self._on_line = on_line

    def _heard(self, line: str, loop: asyncio.AbstractEventLoop) -> None:
        if self._on_line is not None:
            loop.call_soon_threadsafe(self._on_line, line)

    def _warning(self, line: str) -> str | None:
        return line if is_error(line) else None

    def _tell(self, line: str) -> None:
        if not kiss_dump(line):                                      # (the frames of `-d n` are the daemon's to count; the log has the packets already)
            super()._tell(line)

    def _end(self, process: subprocess.Popen[str]) -> None:
        """Its input closed (its own clean end), SIGINT after STOP_WAIT_SEC on POSIX, the kill after another; on Windows the tree ended after the wait."""
        self.close_input(process)
        if childprogram.waited(process, STOP_WAIT_SEC):
            return
        if sys.platform == "win32":
            childprogram.end_tree(process, STOP_WAIT_SEC)
        elif not self.ask(process, signal.SIGINT, STOP_WAIT_SEC):
            self.kill(process)
