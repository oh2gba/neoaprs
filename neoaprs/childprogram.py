"""A program the daemon starts and holds for a radio (the Mercury HF modem, Direwolf): its run, read line by line by a thread into the log, told to the loop when it ends, and stopped by the program's own way; the
environment it runs with; a run of ours that an earlier daemon left behind, ended; and the kernel's table of sockets, which holds a started program to listening on this computer only. The parts that differ from
one program to the other (its name, which of its lines are warnings, what is done with a line, how it is asked to end) are its subclass's: mercuryhelper.Program, direwolfprogram.Program.

A program is started with `subprocess.Popen` and read by a thread, as the serial line is: the daemon's loop may be the one Tornado forces on Windows, which cannot start subprocesses of its own, and what the program
prints goes to the daemon's log, never to the page. A thread waits for it to end and tells the loop with `call_soon_threadsafe`, with the exit code and its last lines, so that the owner can start it again. Its
process id is written beside its configuration and removed again when it ends, so that the next start can end a run of ours left behind by a crash of the daemon (it holds the sound card and the ports)."""
import asyncio
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from .childenv import child_environment, windows_program
from .source import os_error_text

log = logging.getLogger("neoaprs.childprogram")

STOP_WAIT_SEC = 5.0                  # how long a program asked to end is given before it is asked again or killed
LAST_LINES = 8                       # how many of the program's last lines are kept for the log's line when it ends
STARTUP_LINES = 30                   # the first lines of each run are in the log whatever they are (its version, its sound card, its keying); after them only its warnings and errors are
SAID_MAX = 1000                      # distinct warnings of the program counted at once; the count starts over beyond that

Command = list[str]                  # how a program is run: its path, or an interpreter and a module that stands in for it (the tests' fakes)
HIDDEN_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)         # Windows: the program gets no console window of its own; 0 elsewhere


def environment(command: Command) -> dict[str, str]:
    """The environment a program runs with: the daemon's reduced one (childenv.py), and ALSA_CONFIG_PATH pointing at the ALSA configuration shipped beside the program when there is one (Linux: the bundled ALSA library
    would otherwise look for the system's /usr/share/alsa/alsa.conf, which a machine without ALSA installed does not have, and open no sound card)."""
    env = child_environment()
    conf = Path(command[0]).resolve().parent / "share" / "alsa" / "alsa.conf"
    if len(command) == 1 and conf.is_file():
        env["ALSA_CONFIG_PATH"] = str(conf)
    return env


# ---- where a program listens

LOOPBACK_HEX = ("0100007F", "00000000000000000000000001000000")        # 127.0.0.1 and ::1 as /proc/net/tcp and tcp6 write a local address (the kernel's byte order, hex)
PROC_TCP = ("/proc/net/tcp", "/proc/net/tcp6")


def _listeners(tables: Sequence[str], ports: Iterable[int]) -> dict[int, set[str]]:
    """The local addresses, as the kernel writes them, of the sockets in LISTEN on these ports in the texts of /proc/net/tcp and tcp6."""
    wanted = set(ports)
    found: dict[int, set[str]] = {}
    for text in tables:
        for line in text.splitlines()[1:]:
            fields = line.split()
            if len(fields) < 4 or fields[3] != "0A":                                # (0A is LISTEN)
                continue
            address, _, port = fields[1].rpartition(":")
            if int(port, 16) in wanted:
                found.setdefault(int(port, 16), set()).add(address)
    return found


def foreign_listeners(ports: Iterable[int]) -> list[str]:
    """The listeners on these ports that are not on the loopback, as `address:port` in the kernel's hex, from the kernel's table of sockets (Linux: /proc/net/tcp and tcp6); empty where that table is not there
    (Windows, macOS: nothing can be said here; the shipped programs bind the loopback in their source), and empty when every listener is 127.0.0.1 or ::1. Reads two small files: for a thread or a quick call."""
    tables: list[str] = []
    for name in PROC_TCP:
        try:
            tables.append(Path(name).read_text(encoding="ascii"))
        except OSError:
            continue
    return [f"{address}:{port}" for port, addresses in sorted(_listeners(tables, ports).items()) for address in sorted(addresses) if address not in LOOPBACK_HEX]


# ---- a run left behind

FILETIME_1970 = 116444736000000000  # 1970 in Windows' FILETIME, 100 ns since 1601
MADE_SLACK_SEC = 10.0              # a process made this long after its pid file was written is still the one it names (Windows: the clocks of the file and the process)
GONE_POLL_SEC = 0.05               # how often a run left behind is looked at while it ends


def _asked_of_windows_process[T](pid: int, ask: Callable[[Any, Any, Any], T], unknown: T) -> T:
    """`ask(ctypes, kernel32, handle)` of the Windows process of this id, opened for the limited questions (PROCESS_QUERY_LIMITED_INFORMATION); `unknown` when it cannot be opened."""
    import ctypes
    kernel32 = ctypes.windll.kernel32                              # type: ignore[attr-defined, unused-ignore]
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return unknown
    try:
        return ask(ctypes, kernel32, handle)
    finally:
        kernel32.CloseHandle(handle)


def _running_windows(pid: int) -> bool:
    """Whether the Windows process of this id is still running (STILL_ACTIVE as its exit code); a process that ended but whose handle someone still holds is not."""
    def still_active(ctypes: Any, kernel32: Any, handle: Any) -> bool:
        code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    return _asked_of_windows_process(pid, still_active, False)


def _windows_image(pid: int) -> str | None:
    """The full path of the program file of the Windows process of this id; None when the process cannot be opened or the path cannot be read."""
    def image(ctypes: Any, kernel32: Any, handle: Any) -> str | None:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        return str(buffer.value[:size.value]) if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) else None
    return _asked_of_windows_process(pid, image, None)


def windows_created(pid: int) -> float | None:
    """When the Windows process of this id was made, in seconds since 1970 (GetProcessTimes); None when the process cannot be opened or its times cannot be read."""
    def created(ctypes: Any, kernel32: Any, handle: Any) -> float | None:
        made, ended, kernel, user = (ctypes.c_ulonglong() for _ in range(4))
        if not kernel32.GetProcessTimes(handle, ctypes.byref(made), ctypes.byref(ended), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        return float((made.value - FILETIME_1970) / 1e7)
    return _asked_of_windows_process(pid, created, None)


def made_before(created: float | None, written: float) -> bool:
    """Whether a process made at `created` can be the one a file written at `written` names (it is written just after the start): made no later than that, MADE_SLACK_SEC for the two clocks; no when the time is not
    known. Windows reuses process ids, after a reboot most of all: a process that got the id later is not the one the file names."""
    return created is not None and created <= written + MADE_SLACK_SEC


def gone(pid: int) -> bool:
    """Whether the process of this id has ended: on Windows no longer running; on POSIX not there, or a zombie (it holds nothing any more)."""
    if sys.platform == "win32":
        return not _running_windows(pid)
    else:
        return _ended_posix(pid)


def _ended_posix(pid: int) -> bool:
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        try:
            return stat.read_text(encoding="ascii", errors="replace").rpartition(")")[2].split()[0] in ("Z", "X")
        except (OSError, IndexError):            # (it went between the two looks)
            return True
    try:
        os.kill(pid, 0)                          # (a POSIX system without /proc: signal 0 asks only whether the process is there)
        return False
    except ProcessLookupError:
        return True
    except OSError:                              # (there, and another user's)
        return False


def image_is(image: str | None, file: str) -> bool:
    """Whether the program file at this Windows path (either kind of slash) is `file` (`mercury.exe`), the name case aside; no when the path is not known: where that cannot be read, nothing is ended."""
    return image is not None and image.replace("\\", "/").rsplit("/", 1)[-1].lower() == file.lower()


def end_stale(pid_file: Path, ours: Callable[[int, float], bool], what: str, ask: signal.Signals = signal.SIGTERM, wait_sec: float = 0.0) -> bool:
    """Ends a run of ours that an earlier daemon left running (its id is in the file beside the configuration), so that it does not hold the sound card and the ports: asked with `ask` (the signal the program cleans
    up on) when `ours` says the process of that id, given when the file was written, is still the program; then waited for up to `wait_sec` to be gone (the start that follows opens the same sound card); whether
    one was ended. The file is consumed in any case (one that cannot be removed is a line in the log, and the check goes on: the daemon's start never fails on it)."""
    try:
        text, written = pid_file.read_text(encoding="ascii"), pid_file.stat().st_mtime
    except OSError:
        return False
    try:
        pid_file.unlink(missing_ok=True)
    except OSError as e:                                           # (held by a virus scanner, read-only, a folder that cannot be written: the check goes on, the next one asks the same)
        logging.getLogger(f"neoaprs.{what.lower()}").warning("the file of a %s left behind, %s, could not be removed: %s", what, pid_file, os_error_text(e))
    try:
        pid = int(text.strip())
    except ValueError:
        return False
    if pid == os.getpid() or pid <= 0 or not ours(pid, written):
        return False
    try:
        os.kill(pid, ask)
    except OSError:
        return False
    logging.getLogger(f"neoaprs.{what.lower()}").warning("a %s left behind by an earlier run (process %d) was ended", what, pid)
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline and not gone(pid):
        time.sleep(GONE_POLL_SEC)
    return True


# ---- the run

def end_tree(process: subprocess.Popen[str], wait_sec: float) -> None:
    """Windows: the process and every child of it ended (`taskkill /T /F`, the system's own tool: there is no tree in the Win32 API), then the process waited for; the process alone when taskkill is not there. A program
    started through a launcher (a venv's python.exe, which the tests' fakes run under, starts the interpreter as its child) would otherwise leave the child, and its sockets, alive."""
    try:
        subprocess.run([windows_program("taskkill.exe"), "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=wait_sec, check=False, creationflags=HIDDEN_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.debug("taskkill could not end the tree of process %d: %s", process.pid, e)
    try:
        process.wait(wait_sec)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def waited(process: subprocess.Popen[str], seconds: float) -> bool:
    """Whether the process ended within `seconds`."""
    try:
        process.wait(seconds)
    except subprocess.TimeoutExpired:
        return False
    return True


def _unlink_own(pid_file: Path, pid: int) -> None:
    """The pid file removed while it still names this process: a stop that took long (in a thread, while the relaunch after the back-off went on) leaves the file the next run has written in its place."""
    try:
        if pid_file.read_text(encoding="ascii").strip() == str(pid):
            pid_file.unlink(missing_ok=True)
    except OSError:
        pass


class Program:
    """One run of a program: started, read, and told when it ends. A subclass says what the program is called (`name`), which of its lines are its warnings (`_warning`), what is done with each line on the reader
    thread (`_heard`) and how it is ended (`_end`)."""
    name = "program"

    def __init__(self, on_ended: Callable[[int | None, list[str]], None], owner_log: logging.Logger, program_log: logging.Logger, *, stdin_pipe: bool = False) -> None:
        self._on_ended = on_ended
        self._log, self._program_log = owner_log, program_log
        self._stdin_pipe = stdin_pipe                       # the program ends cleanly when its standard input closes (Direwolf's -Q): it is given a pipe, which the stop closes
        self._process: subprocess.Popen[str] | None = None
        self._stopping: subprocess.Popen[str] | None = None        # the run a stop is ending now (in another thread): a second stop waits for it to be gone
        self._pid_file: Path | None = None
        self.last_lines: deque[str] = deque(maxlen=LAST_LINES)
        self._said: dict[str, int] = {}                     # how many times each distinct warning of the program has come (a stuck sound device says the same line a thousand times a second)
        self.lines_read = 0                                 # how many lines this run has printed (the reader thread's alone)

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    def start(self, argv: Command, cwd: Path, pid_file: Path | None = None) -> None:
        """Starts the program and the thread that reads it; OSError when it cannot be started (not there, not executable, the wrong architecture). A run of it still on is ended first (its owner stops a run
        before it starts another; one left running beside the new would hold the sound card and key the radio with no one to stop it)."""
        loop = asyncio.get_running_loop()
        if self.running:
            self._log.error("%s was started while a run of it was still on (process %s): that run is ended first", self.name, self.pid)
            self.stop()
        self._process = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE if self._stdin_pipe else subprocess.DEVNULL, text=True, encoding="utf-8",
                                         errors="replace", env=environment(argv), creationflags=HIDDEN_WINDOW)
        self._pid_file = pid_file
        self.lines_read = 0
        if pid_file is not None:
            try:
                pid_file.write_text(str(self._process.pid), encoding="ascii")
            except OSError as e:
                self._log.debug("the %s pid file could not be written: %s", self.name, e)
        self._log.info("%s started (process %d): %s", self.name, self._process.pid, " ".join(argv))
        threading.Thread(target=self._read, args=(self._process, loop, pid_file), name=f"{self.name.lower()}-output", daemon=True).start()

    def _read(self, process: subprocess.Popen[str], loop: asyncio.AbstractEventLoop, pid_file: Path | None = None) -> None:
        """Reads the program's lines into the log until it ends, then removes its pid file (while the file still names it: a run that ended by itself leaves no id for the next start to take for its own, which
        the system may have given another program meanwhile) and tells the loop."""
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.rstrip()
            if line:
                self.last_lines.append(line)
                self._tell(line)
                if self._process is process:
                    self._heard(line, loop)
        code = process.wait()
        if pid_file is not None:
            _unlink_own(pid_file, process.pid)
        if self._process is process:
            loop.call_soon_threadsafe(self._on_ended, code, list(self.last_lines))

    def _heard(self, line: str, loop: asyncio.AbstractEventLoop) -> None:
        """A line of this run, on the reader thread: what the subclass does with it (tells the loop with `call_soon_threadsafe`); nothing here."""

    def _warning(self, line: str) -> str | None:
        """The words a warning or an error of the program is counted by (the same warning again is the same words); None for any other line."""
        return None

    def _tell(self, line: str) -> None:
        """One line of the program into the log: its warnings and errors at INFO the first, the tenth and every hundredth time the same line comes (a stuck sound device repeats one warning every millisecond, which
        would rotate the log in minutes and bury the day's lines; the count is said with the line); the first STARTUP_LINES lines of a run at INFO whatever they say (how it found its sound card and its keying is
        what a person helping from the log needs), everything else at DEBUG."""
        self.lines_read += 1
        said = self._warning(line)
        if said is None:
            self._program_log.log(logging.INFO if self.lines_read <= STARTUP_LINES else logging.DEBUG, "%s", line)
            return
        if len(self._said) >= SAID_MAX:
            self._said.clear()
        count = self._said[said] = self._said.get(said, 0) + 1
        if count in (1, 10) or count % 100 == 0:
            self._program_log.info("%s%s", line, f" (the {count}th time)" if count > 1 else "")

    def _end(self, process: subprocess.Popen[str]) -> None:
        """Ends the running process by the program's own way, waited for in the calling thread."""
        raise NotImplementedError

    def stop(self) -> None:
        """Ends the program (`_end`), and removes the pid file once it has ended, while it still names the stopped run: a clean stop leaves nothing for the next start to look at. Waited for in the calling thread; a stop while another is ending the
        run waits for that run to be gone, so that what it holds (the sound card, the keying) is free when this one returns."""
        process, self._process = self._process, None
        pid_file, self._pid_file = self._pid_file, None
        if process is None:
            if (ending := self._stopping) is not None:
                ending.wait()
            return
        self._stopping = process
        try:
            if process.poll() is not None:
                return
            self._end(process)
            self._log.info("%s stopped (exit %s)", self.name, process.returncode)
        finally:
            self._stopping = None
            if pid_file is not None:
                _unlink_own(pid_file, process.pid)

    def ask(self, process: subprocess.Popen[str], sig: signal.Signals, wait_sec: float) -> bool:
        """POSIX: the process sent `sig`; whether it ended within `wait_sec`."""
        try:
            process.send_signal(sig)
        except OSError:
            return process.poll() is not None
        return waited(process, wait_sec)

    def kill(self, process: subprocess.Popen[str]) -> None:
        process.kill()
        process.wait()

    def close_input(self, process: subprocess.Popen[str]) -> None:
        """The program's standard input closed: one that ends at its end (Direwolf's -Q) cleans up and exits."""
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
