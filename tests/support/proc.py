"""End a program the tests started the way its system ends one: SIGTERM or SIGINT on POSIX,
Ctrl+Break on Windows (which only reaches a child started in its own process group).
"""

import os
import signal
import subprocess
import sys

WINDOWS = sys.platform == "win32"
NEW_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
# The longest a test waits for a program it asked to end (a daemon closing its radios, a replay), on
# a machine busy with the whole suite: a limit, not how long it takes
STOP_PATIENCE_SEC = 60.0


def send(proc: "subprocess.Popen[str]", sig: int) -> None:
    """`sig` on POSIX, Ctrl+Break on Windows."""
    proc.send_signal(signal.CTRL_BREAK_EVENT if WINDOWS else sig)  # type: ignore[attr-defined, unused-ignore]


def stop(proc: "subprocess.Popen[str]") -> None:
    """Asks the program to end, as the service manager does."""
    send(proc, signal.SIGBREAK if WINDOWS else signal.SIGTERM)  # type: ignore[attr-defined, unused-ignore]


def interrupt(proc: "subprocess.Popen[str]") -> None:
    """Asks the program to end, as Ctrl+C does."""
    send(proc, signal.SIGBREAK if WINDOWS else signal.SIGINT)  # type: ignore[attr-defined, unused-ignore]


def process_alive(pid: int) -> bool:
    """Whether the process `pid`, which need not be a child of the test, still runs (a zombie does not)."""
    if WINDOWS:
        import ctypes

        windows: object = ctypes
        k = windows.WinDLL("kernel32")  # type: ignore[attr-defined]
        k.OpenProcess.restype = ctypes.c_void_p
        handle = k.OpenProcess(0x00100000, 0, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return bool(k.WaitForSingleObject(ctypes.c_void_p(handle), 0) == 0x102)  # WAIT_TIMEOUT: still running
        finally:
            k.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat = f"/proc/{pid}/stat"
    if os.path.exists(stat):
        with open(stat, encoding="ascii", errors="replace") as f:
            return f.read().rsplit(")", 1)[-1].split()[0] != "Z"
    return True
