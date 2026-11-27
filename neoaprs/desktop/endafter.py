"""The desktop app's watchdog of its own end: when Quit is decided the app starts this as a small hidden
process of its own program, which ends the app if it has not ended by itself within the bound. It works
when no thread of the app can run any more (a toolkit or WebView2 holding the main thread and the GIL).
"""

import ctypes
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

log = logging.getLogger("neoaprs.desktop")

FLAG = "--end-after"  # the frozen programs' entry starts the watchdog on this first argument
# exit codes of the watchdog
ENDED, ENDED_BY_US, BAD_ARGUMENT, NOT_PARENT, CANNOT_OPEN = 0, 1, 2, 3, 4
# the exit code a process ended by the watchdog gets on Windows
END_CODE = 0x4E45
# how long after Quit the watchdog ends the app: past the shells' own ends (webshell.LEAVE_SEC and its exit)
END_SEC = 8.0
# how often the watchdog on POSIX looks whether its parent has ended
POLL_SEC = 0.1
SYNCHRONIZE, PROCESS_TERMINATE, PROCESS_QUERY_LIMITED_INFORMATION = 0x00100000, 0x0001, 0x1000
WAIT_OBJECT_0, WAIT_TIMEOUT = 0, 0x102
ERROR_INVALID_PARAMETER = 87

_started = threading.Lock()  # one watchdog for a process, however often Quit is decided


def argv_for(pid: int, seconds: float, frozen: bool | None = None, executable: str | None = None) -> list[str]:
    """Return the watchdog's command line for the process `pid`: a frozen build's own program takes FLAG first.

    From a checkout it is this file run isolated by the base interpreter, never a venv's python.exe: on Windows
    that is a launcher, and the watchdog would be the launcher's child, not this process's."""
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    tail = [str(pid), f"{seconds:g}"]
    if frozen:
        return [executable or sys.executable, FLAG, *tail]
    base = executable or getattr(sys, "_base_executable", "") or sys.executable
    return [base, "-I", os.path.abspath(__file__), *tail]


def watch(seconds: float, popen: Callable[..., Any] = subprocess.Popen) -> bool:
    """Start the watchdog of this process once: it ends this process `seconds` from now unless it has ended.

    Return whether one runs now; a watchdog that cannot start is logged and the in-process end stays."""
    if not _started.acquire(blocking=False):
        return True
    try:
        popen(
            argv_for(os.getpid(), seconds),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            start_new_session=sys.platform != "win32",
        )
    except OSError as e:
        log.warning("the app's end could not be watched from outside (%s)", e)
        _started.release()
        return False
    log.info("the app ends within %g s, whatever its window does", seconds)
    return True


def _kernel32() -> Any:
    windows: Any = ctypes  # WinDLL is Windows only
    k = windows.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    k.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    k.WaitForSingleObject.restype = ctypes.c_uint32
    k.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    k.TerminateProcess.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    k.CloseHandle.argtypes = (ctypes.c_void_p,)
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.GetProcessTimes.argtypes = (ctypes.c_void_p, *([ctypes.POINTER(ctypes.c_uint64)] * 4))
    return k


def _started_at(k: Any, handle: Any) -> int:
    """When the process of `handle` started, in 100 ns since 1601; 0 if it cannot be told."""
    created, other = ctypes.c_uint64(), ctypes.c_uint64()
    ok = k.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(other), ctypes.byref(other), ctypes.byref(other))
    return created.value if ok else 0


def end_now(code: int) -> None:
    """End this process at once. On Windows by TerminateProcess, not ExitProcess (os._exit): ExitProcess runs
    the libraries' detach under the loader lock, which a WebView2 or .NET thread in its start can hold for ever."""
    if sys.platform == "win32":
        k = _kernel32()
        k.TerminateProcess(k.GetCurrentProcess(), code)
    os._exit(code)


def _windows_end(pid: int, seconds: float) -> int:
    k = _kernel32()
    handle = k.OpenProcess(SYNCHRONIZE | PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
    if not handle:  # ERROR_INVALID_PARAMETER: no such process, it has ended already
        return ENDED if ctypes.get_last_error() == ERROR_INVALID_PARAMETER else CANNOT_OPEN  # type: ignore[attr-defined,unused-ignore]
    try:
        if _started_at(k, handle) > _started_at(k, k.GetCurrentProcess()):
            return ENDED  # a newer process under the ended parent's id: it is never touched
        if k.WaitForSingleObject(handle, int(seconds * 1000)) != WAIT_TIMEOUT:
            return ENDED
        k.TerminateProcess(handle, END_CODE)
        return ENDED_BY_US
    finally:
        k.CloseHandle(handle)


def _posix_end(pid: int, seconds: float, clock: Callable[[], float] = time.monotonic) -> int:
    deadline = clock() + seconds
    while os.getppid() == pid:  # an ended parent leaves its children to another: its pid is not looked at again
        if clock() >= deadline:
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))  # (POSIX only: Windows ends by handle)
            return ENDED_BY_US
        time.sleep(POLL_SEC)
    return ENDED


OUTCOMES = {
    ENDED: "it ended by itself",
    ENDED_BY_US: "it did not end: ended it",
    BAD_ARGUMENT: "refused: the arguments are not PID SECONDS",
    NOT_PARENT: "refused: that process is not this one's parent",
    CANNOT_OPEN: "the process could not be opened",
}


def main(argv: list[str]) -> int:
    """`PID SECONDS`: wait up to SECONDS for the process PID, this process's parent, to end, else end it.

    Says what came of it on one line of stderr (nowhere when the app started it, a test reads it)."""
    code = _watch(argv)
    if sys.stderr is not None:
        print(f"end-after {' '.join(argv)}: {OUTCOMES.get(code, '?')} (exit {code})", file=sys.stderr, flush=True)
    return code


def _watch(argv: list[str]) -> int:
    try:
        pid, seconds = int(argv[0]), float(argv[1])
    except (IndexError, ValueError):
        return BAD_ARGUMENT
    if len(argv) != 2 or pid <= 0 or not 0 <= seconds <= 3600:
        return BAD_ARGUMENT
    if os.getppid() != pid:
        # only the program that started it: the watchdog cannot be pointed at another. On POSIX a parent that
        # has ended already leaves its children to another, so a pid that is no process is one that ended.
        return ENDED if sys.platform != "win32" and not _exists(pid) else NOT_PARENT
    return _windows_end(pid, seconds) if sys.platform == "win32" else _posix_end(pid, seconds)


def _exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
