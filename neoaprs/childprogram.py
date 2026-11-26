"""A child program the daemon runs for a radio (the Mercury modem, Direwolf).

Starts it, logs its output, stops it, and ends a run left behind by a crashed daemon.
Subclasses supply the name, the warnings, the handling of a line and how it is asked to end.
"""

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

from . import winchild
from .childenv import child_environment, windows_program
from .clock import Clock, utcnow
from .source import os_error_text

log = logging.getLogger("neoaprs.childprogram")

STOP_WAIT_SEC = 5.0
LAST_LINES = 8  # kept for the log line written at the end
STARTUP_LINES = 30  # the first lines of a run are always logged
SAID_MAX = 1000  # distinct warnings counted at once
QUIET_SEC = 60.0  # a repeated warning not seen for this long has stopped

Command = list[str]
HIDDEN_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: no console window; 0 elsewhere


def program_file(name: str, system: str | None = None) -> str:
    return f"{name}.exe" if (system or sys.platform).startswith("win") else name


def found(program: Path) -> Command | None:
    return [str(program)] if program.is_file() and os.access(program, os.X_OK) else None


def runs_shipped(command: Command, program: Path) -> bool:
    """Return whether the command is the file `program` itself, not a stand-in interpreter."""
    return len(command) == 1 and Path(command[0]).resolve() == program.resolve()


def environment(command: Command) -> dict[str, str]:
    """Return the reduced environment, plus ALSA_CONFIG_PATH if an alsa.conf is shipped."""
    env = child_environment()
    conf = Path(command[0]).resolve().parent / "share" / "alsa" / "alsa.conf"
    if len(command) == 1 and conf.is_file():
        env["ALSA_CONFIG_PATH"] = str(conf)
    return env


# ---- where a program listens

# 127.0.0.1 and ::1 as /proc/net/tcp and tcp6 write them (hex, kernel byte order).
LOOPBACK_HEX = ("0100007F", "00000000000000000000000001000000")
PROC_TCP = ("/proc/net/tcp", "/proc/net/tcp6")


def _listeners(tables: Sequence[str], ports: Iterable[int]) -> dict[int, set[str]]:
    """Return the LISTEN addresses (kernel hex) on `ports`, per port."""
    wanted = set(ports)
    found: dict[int, set[str]] = {}
    for text in tables:
        for line in text.splitlines()[1:]:
            fields = line.split()
            if len(fields) < 4 or fields[3] != "0A":  # 0A is LISTEN
                continue
            address, _, port = fields[1].rpartition(":")
            if int(port, 16) in wanted:
                found.setdefault(int(port, 16), set()).add(address)
    return found


def foreign_listeners(ports: Iterable[int]) -> list[str]:
    """Return the listeners on `ports` outside the loopback, as `address:port` in kernel hex."""
    return [
        f"{address}:{port}"
        for port, addresses in sorted(_listeners(_tables(), ports).items())
        for address in sorted(addresses)
        if address not in LOOPBACK_HEX
    ]


def listened(ports: Iterable[int]) -> set[int]:
    """Return the ports among `ports` with a listener on any address; empty without the table."""
    return set(_listeners(_tables(), ports))


def _tables() -> list[str]:
    tables: list[str] = []
    for name in PROC_TCP:
        try:
            tables.append(Path(name).read_text(encoding="ascii"))
        except OSError:
            continue
    return tables


# ---- a run left behind

FILETIME_1970 = 116444736000000000  # 1970 in Windows' FILETIME, 100 ns since 1601
# A process made this long after the pid file was written still counts (clocks differ).
MADE_SLACK_SEC = 10.0
GONE_POLL_SEC = 0.05


def _asked_of_windows_process[T](pid: int, ask: Callable[[Any, Any, Any], T], unknown: T) -> T:
    """Return `ask(ctypes, kernel32, handle)`, or `unknown` if the process cannot be opened."""
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined, unused-ignore]
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return unknown
    try:
        return ask(ctypes, kernel32, handle)
    finally:
        kernel32.CloseHandle(handle)


def _running_windows(pid: int) -> bool:
    def still_active(ctypes: Any, kernel32: Any, handle: Any) -> bool:
        code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259

    return _asked_of_windows_process(pid, still_active, False)


def _windows_image(pid: int) -> str | None:
    def image(ctypes: Any, kernel32: Any, handle: Any) -> str | None:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        return (
            str(buffer.value[: size.value])
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
            else None
        )

    return _asked_of_windows_process(pid, image, None)


def windows_created(pid: int) -> float | None:
    def created(ctypes: Any, kernel32: Any, handle: Any) -> float | None:
        made, ended, kernel, user = (ctypes.c_ulonglong() for _ in range(4))
        if not kernel32.GetProcessTimes(
            handle, ctypes.byref(made), ctypes.byref(ended), ctypes.byref(kernel), ctypes.byref(user)
        ):
            return None
        return float((made.value - FILETIME_1970) / 1e7)

    return _asked_of_windows_process(pid, created, None)


def made_before(created: float | None, written: float) -> bool:
    """Return whether a process created at `created` can be the one a file written at `written` names.

    Windows reuses process ids.
    """
    return created is not None and created <= written + MADE_SLACK_SEC


def gone(pid: int) -> bool:
    """Return whether the process has ended (a POSIX zombie counts)."""
    if sys.platform == "win32":
        return not _running_windows(pid)
    else:
        return _ended_posix(pid)


def _ended_posix(pid: int) -> bool:
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        try:
            return stat.read_text(encoding="ascii", errors="replace").rpartition(")")[2].split()[0] in ("Z", "X")
        except (OSError, IndexError):  # it vanished between the two checks
            return True
    try:
        os.kill(pid, 0)  # without /proc: signal 0 only tests that the process exists
        return False
    except ProcessLookupError:
        return True
    except OSError:  # exists, but belongs to another user
        return False


def image_is(image: str | None, file: str) -> bool:
    """Return whether the Windows path names the program `file`, ignoring case; False if unknown."""
    return image is not None and image.replace("\\", "/").rsplit("/", 1)[-1].lower() == file.lower()


def end_stale(
    pid_file: Path,
    ours: Callable[[int, float], bool],
    what: str,
    ask: signal.Signals = signal.SIGTERM,
    wait_sec: float = 0.0,
) -> bool:
    """End a run left by an earlier daemon, whose id is in `pid_file`; return whether one was ended.

    The process is sent `ask` if `ours(pid, written)` holds. The file is always consumed.
    """
    try:
        text, written = pid_file.read_text(encoding="ascii"), pid_file.stat().st_mtime
    except OSError:
        return False
    try:
        pid_file.unlink(missing_ok=True)
    except OSError as e:
        logging.getLogger(f"neoaprs.{what.lower()}").warning(
            "the file of a %s left behind, %s, could not be removed: %s", what, pid_file, os_error_text(e)
        )
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
    logging.getLogger(f"neoaprs.{what.lower()}").warning(
        "a %s left behind by an earlier run (process %d) was ended", what, pid
    )
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline and not gone(pid):
        time.sleep(GONE_POLL_SEC)
    return True


# ---- the run


def end_tree(process: subprocess.Popen[str], wait_sec: float) -> None:
    """Windows: end the process and its children with `taskkill /T /F` (a launcher leaves a child)."""
    try:
        subprocess.run(
            [windows_program("taskkill.exe"), "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            timeout=wait_sec,
            check=False,
            creationflags=HIDDEN_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log.debug("taskkill could not end the tree of process %d: %s", process.pid, e)
    try:
        process.wait(wait_sec)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def waited(process: subprocess.Popen[str], seconds: float) -> bool:
    try:
        process.wait(seconds)
    except subprocess.TimeoutExpired:
        return False
    return True


def _unlink_own(pid_file: Path, pid: int) -> None:
    """Remove the pid file only while it still names this process (a relaunch may have rewritten it)."""
    try:
        if pid_file.read_text(encoding="ascii").strip() == str(pid):
            pid_file.unlink(missing_ok=True)
    except OSError:
        pass


class Program:
    """One run of a program; a subclass sets `name` and implements `_heard` and `_end`."""

    name = "program"

    def __init__(
        self,
        on_ended: Callable[[int | None, list[str]], None],
        owner_log: logging.Logger,
        program_log: logging.Logger,
        *,
        stdin_pipe: bool = False,
    ) -> None:
        self._on_ended = on_ended
        self._log, self._program_log = owner_log, program_log
        self._stdin_pipe = stdin_pipe  # the program ends when its stdin closes (Direwolf -Q)
        self._process: subprocess.Popen[str] | None = None
        self._stopping: subprocess.Popen[str] | None = None
        self._pid_file: Path | None = None
        self.last_lines: deque[str] = deque(maxlen=LAST_LINES)
        # Per distinct warning: [count, monotonic time of the latest, its wall time] (a stuck sound
        # device repeats one line endlessly).
        self._said: dict[str, list[Any]] = {}
        self._looked_at = 0.0  # monotonic time of the latest look for warnings that stopped
        self.clock: Clock = utcnow
        self.lines_read = 0  # written by the reader thread only

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    def start(self, argv: Command, cwd: Path, pid_file: Path | None = None) -> None:
        """Start the program and its reader thread; raise OSError if it cannot be started.

        A run still going is ended first.
        """
        loop = asyncio.get_running_loop()
        if self.running:
            self._log.error(
                "%s was started while a run of it was still on (process %s): that run is ended first",
                self.name,
                self.pid,
            )
            self.stop()
        self._process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if self._stdin_pipe else subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment(argv),
            creationflags=HIDDEN_WINDOW,
        )
        if sys.platform == "win32" and not winchild.tie_to_daemon(self._process.pid):
            self._log.info("%s (process %d) is not tied to the daemon's life", self.name, self._process.pid)
        self._pid_file = pid_file
        self.lines_read = 0
        if pid_file is not None:
            try:
                pid_file.write_text(str(self._process.pid), encoding="ascii")
            except OSError as e:
                self._log.debug("the %s pid file could not be written: %s", self.name, e)
        self._log.info("%s started (process %d): %s", self.name, self._process.pid, " ".join(argv))
        threading.Thread(
            target=self._read, args=(self._process, loop, pid_file), name=f"{self.name.lower()}-output", daemon=True
        ).start()

    def _read(
        self, process: subprocess.Popen[str], loop: asyncio.AbstractEventLoop, pid_file: Path | None = None
    ) -> None:
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.rstrip()
            if line:
                if not self._unlogged(line):
                    self.last_lines.append(line)
                    self._tell(line)
                if self._process is process:
                    self._heard(line, loop)
        self._stopped_warnings(None)
        code = process.wait()
        if pid_file is not None:
            _unlink_own(pid_file, process.pid)
        if self._process is process:
            loop.call_soon_threadsafe(self._on_ended, code, list(self.last_lines))

    def _heard(self, line: str, loop: asyncio.AbstractEventLoop) -> None:
        """Handle a line on the reader thread; reach the loop with `call_soon_threadsafe`."""

    def _unlogged(self, line: str) -> bool:
        """Return whether the line is kept out of the log and the last lines."""
        return False

    def _warning(self, line: str) -> str | None:
        """Return the key a warning line is counted by, or None."""
        return None

    def _tell(self, line: str) -> None:
        """Log a line: INFO for the first STARTUP_LINES, then DEBUG; a repeated warning is thinned.

        A warning is logged the 1st, 10th, 100th, 1000th... time, and once more when it stops."""
        self.lines_read += 1
        now = time.monotonic()
        if now - self._looked_at >= 1.0:
            self._stopped_warnings(now)
        said = self._warning(line)
        if said is None:
            self._program_log.log(logging.INFO if self.lines_read <= STARTUP_LINES else logging.DEBUG, "%s", line)
            return
        entry = self._said.get(said)
        if entry is None:
            if len(self._said) >= SAID_MAX:
                self._stopped_warnings(None)
            entry = self._said[said] = [0, now, None]
        entry[0] += 1
        entry[1], entry[2] = now, self.clock()
        count = entry[0]
        if count == 10 ** (len(str(count)) - 1):
            self._program_log.info("%s%s", line, f" (the {count}th time)" if count > 1 else "")

    def _stopped_warnings(self, now: float | None) -> None:
        """Log once each repeated warning not seen for QUIET_SEC (all when `now` is None) and forget it."""
        if now is not None:
            self._looked_at = now
        for key, (count, last, at) in list(self._said.items()):
            if now is None or now - last >= QUIET_SEC:
                del self._said[key]
                if count != 10 ** (len(str(count)) - 1):  # (a power of ten was logged with its count)
                    self._program_log.info("%s: came %d times, the last at %s", key, count, f"{at:%Y-%m-%d %H:%M:%S}Z")

    def _end(self, process: subprocess.Popen[str]) -> None:
        """End the process in the program's own way, blocking."""
        raise NotImplementedError

    def stop(self) -> None:
        """End the program with `_end`, remove its pid file and block until it is gone."""
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
        """POSIX: send `sig` and return whether the process ended within `wait_sec`."""
        try:
            process.send_signal(sig)
        except OSError:
            return process.poll() is not None
        return waited(process, wait_sec)

    def kill(self, process: subprocess.Popen[str]) -> None:
        process.kill()
        process.wait()

    def close_input(self, process: subprocess.Popen[str]) -> None:
        """Close the program's standard input (Direwolf with -Q exits on it)."""
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
