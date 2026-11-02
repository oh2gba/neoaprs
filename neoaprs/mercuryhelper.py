"""The Mercury program as a child of the daemon: where it is, the ports it is given, how it is started and watched, how it is stopped, and the list of its sound cards.

Mercury is the one NeoAPRS ships (bundled.py says where): the folder `mercury/` of the shipped programs, with the program and what it needs beside it, and never one found on the PATH or fetched, so that the
operator's system is left alone and the Mercury that runs is the one the suite ran against. On Linux the folder carries its own ALSA library and configuration (the operator's machine need not have them), and
the program is told where the configuration is through the one variable ALSA reads, ALSA_CONFIG_PATH.
It is started with `subprocess.Popen` and read by a thread, as the serial line is: the daemon's loop may be the one Tornado forces on Windows, which cannot start subprocesses of its own, and what the program prints goes
to the daemon's log, never to the page. A thread waits for it to end and tells the loop with `call_soon_threadsafe`, with the exit code and its last lines, so that the owner (mercurymodem.py) can start it again. Two
NeoAPRS on one computer, or a Mercury that something else runs, must not fight over the ports: `free_ports` finds the first pair (the broadcast port and the control port 200 above it) that is free, from the defaults
up. A Mercury of ours left behind by a crash of the daemon holds the sound card: its process id is written beside the configuration, and the next start ends a process of that id that is still a Mercury."""
import asyncio
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path

from .bundled import tools_dir
from .childenv import child_environment
from .mercury import BROADCAST_PORT, CONTROL_OFFSET, SoundCard, audio_open_error, parse_sound_cards

log = logging.getLogger("neoaprs.mercury")
mercury_log = logging.getLogger("neoaprs.mercury.program")         # what Mercury itself prints, one line each

NAME = "mercury"
PORT_TRIES = 50                      # how many pairs of ports are tried from the defaults up
LIST_TIMEOUT_SEC = 15.0              # `mercury -z` opens the sound system; a stuck one is given this long
STOP_WAIT_SEC = 5.0                  # how long a terminated Mercury is given to end before it is killed
LAST_LINES = 8                       # how many of the program's last lines are kept for the problem text

Command = list[str]                  # how the program is run: its path, or an interpreter and a module that stands in for it (the tests' fake)
HIDDEN_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)         # Windows: the program gets no console window of its own; 0 elsewhere


def program_file(system: str | None = None) -> str:
    return f"{NAME}.exe" if (system or sys.platform).startswith("win") else NAME


def find(tools: Path | None = None) -> Command | None:
    """The Mercury NeoAPRS ships: `mercury/mercury[.exe]` in the folder of the shipped programs (`tools`, by default this installation's); None when this installation has none (a wheel installed with pip or uv tool: the
    AppImage, the .deb and the Windows installer carry it)."""
    program = (tools if tools is not None else tools_dir()) / NAME / program_file()
    return [str(program)] if program.is_file() and os.access(program, os.X_OK) else None


def environment(command: Command) -> dict[str, str]:
    """The environment the program runs with: the daemon's reduced one (childenv.py), and ALSA_CONFIG_PATH pointing at the ALSA configuration shipped beside the program when there is one (Linux: the bundled ALSA library
    would otherwise look for the system's /usr/share/alsa/alsa.conf, which a machine without ALSA installed does not have, and open no sound card)."""
    env = child_environment()
    conf = Path(command[0]).resolve().parent / "share" / "alsa" / "alsa.conf"
    if len(command) == 1 and conf.is_file():
        env["ALSA_CONFIG_PATH"] = str(conf)
    return env


def _free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def free_ports(first: int = BROADCAST_PORT, tries: int = PORT_TRIES) -> tuple[int, int]:
    """The first broadcast port from `first` up whose control port (CONTROL_OFFSET above it) is free as well, as the pair. Mercury's defaults when they are free, so that a Mercury of ours is where the manuals say;
    the next pair when another program (another NeoAPRS, a Mercury of the operator's own) holds them. OSError when none of `tries` pairs is free."""
    for port in range(first, first + tries):
        if _free(port) and _free(port + CONTROL_OFFSET) and _free(port + CONTROL_OFFSET + 1):          # (the ARQ data port, one above the control port, is Mercury's too)
            return port, port + CONTROL_OFFSET
    raise OSError(f"no free pair of ports from {first} to {first + tries}")


def list_sound_cards(command: Command, timeout_sec: float = LIST_TIMEOUT_SEC) -> list[SoundCard]:
    """The sound cards Mercury lists (`-z`): run in the calling thread (not on the loop). None, with a line in the log, when the program cannot be run or says nothing a list is made of."""
    try:
        done = subprocess.run([*command, "-z"], capture_output=True, text=True, timeout=timeout_sec, env=environment(command), creationflags=HIDDEN_WINDOW, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("mercury -z could not be run: %s", e)
        return []
    cards = parse_sound_cards(done.stdout)
    if not cards:
        log.info("mercury -z listed no sound card (exit %d): %s", done.returncode, (done.stdout or done.stderr).strip()[-300:])
    return cards


# ---- a Mercury left behind

def _is_mercury(pid: int) -> bool:
    """Whether the process of this id is a Mercury (Linux: "mercury" is in its command line, the program's or the module that stands in for it; elsewhere, that it is running). On Windows the question is
    asked of the process's exit code: os.kill(pid, 0) there is TerminateProcess, which would end whatever process has the id before anything is known of it."""
    cmdline = Path(f"/proc/{pid}/cmdline")
    if cmdline.exists():
        try:
            return NAME in cmdline.read_bytes().decode("utf-8", "replace").lower()
        except OSError:
            return False
    if sys.platform == "win32":
        return _running_windows(pid)
    else:                                                           # (a system with neither /proc nor Windows: nothing is known of the process, and nothing is ended)
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return False


def _running_windows(pid: int) -> bool:
    """Whether the Windows process of this id is still running (STILL_ACTIVE as its exit code); a process that ended but whose handle someone still holds is not."""
    import ctypes
    kernel32 = ctypes.windll.kernel32                              # type: ignore[attr-defined, unused-ignore]
    handle = kernel32.OpenProcess(0x1000, False, pid)              # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259                                   # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def end_stale(pid_file: Path) -> bool:
    """Ends a Mercury of ours that an earlier daemon left running (its id is in the file beside the configuration), so that it does not hold the sound card and the ports; whether one was ended."""
    try:
        text = pid_file.read_text(encoding="ascii")
    except OSError:
        return False
    pid_file.unlink(missing_ok=True)
    try:
        pid = int(text.strip())
    except ValueError:
        return False
    if pid == os.getpid() or pid <= 0 or not _is_mercury(pid):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    log.warning("a Mercury left behind by an earlier run (process %d) was ended", pid)
    return True


# ---- the process

class Program:
    """One run of Mercury: started, read, and told when it ends."""

    def __init__(self, on_ended: Callable[[int | None, list[str]], None], on_audio_error: Callable[[str], None] | None = None) -> None:
        self._on_ended = on_ended
        self._on_audio_error = on_audio_error                    # told, on the loop, the line that says the sound card could not be opened (the program runs on without it)
        self._process: subprocess.Popen[str] | None = None
        self.last_lines: deque[str] = deque(maxlen=LAST_LINES)

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    def start(self, argv: Command, cwd: Path, pid_file: Path | None = None) -> None:
        """Starts the program and the thread that reads it; OSError when it cannot be started (not there, not executable, the wrong architecture)."""
        loop = asyncio.get_running_loop()
        self._process = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                         env=environment(argv), creationflags=HIDDEN_WINDOW)
        if pid_file is not None:
            try:
                pid_file.write_text(str(self._process.pid), encoding="ascii")
            except OSError as e:
                log.debug("the Mercury pid file could not be written: %s", e)
        log.info("Mercury started (process %d): %s", self._process.pid, " ".join(argv))
        threading.Thread(target=self._read, args=(self._process, loop), name="mercury-output", daemon=True).start()

    def _read(self, process: subprocess.Popen[str], loop: asyncio.AbstractEventLoop) -> None:
        """Reads the program's lines into the log until it ends, then tells the loop."""
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.rstrip()
            if line:
                self.last_lines.append(line)
                mercury_log.log(logging.INFO if "[WRN]" in line or "[ERR]" in line else logging.DEBUG, "%s", line)
                if self._on_audio_error is not None and self._process is process and audio_open_error(line):
                    loop.call_soon_threadsafe(self._on_audio_error, line)
        code = process.wait()
        if self._process is process:
            loop.call_soon_threadsafe(self._on_ended, code, list(self.last_lines))

    def stop(self) -> None:
        """Ends the program: asked to end, then killed after STOP_WAIT_SEC. Waited for in the calling thread (a few milliseconds for a Mercury that ends as asked)."""
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(STOP_WAIT_SEC)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.info("Mercury stopped (exit %s)", process.returncode)
