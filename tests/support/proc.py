"""Ending a program the tests started, the way its system ends one: SIGTERM or SIGINT on POSIX; on Windows Ctrl+Break, which only reaches a child that was started in a process group of its own
(`creationflags=NEW_GROUP`; `terminate()` there is a kill, and the exit code of a killed program is not 0)."""
import signal
import subprocess
import sys

WINDOWS = sys.platform == "win32"
NEW_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
STOP_PATIENCE_SEC = 60.0    # the longest a test waits for a program it asked to end (a daemon closing its radios, a replay), on a machine busy with the whole suite: a limit, not how long it takes


def send(proc: "subprocess.Popen[str]", sig: int) -> None:
    """`sig` on POSIX, Ctrl+Break on Windows."""
    proc.send_signal(signal.CTRL_BREAK_EVENT if WINDOWS else sig)  # type: ignore[attr-defined, unused-ignore]


def stop(proc: "subprocess.Popen[str]") -> None:
    """Asks the program to end, as the service manager does."""
    send(proc, signal.SIGBREAK if WINDOWS else signal.SIGTERM)  # type: ignore[attr-defined, unused-ignore]


def interrupt(proc: "subprocess.Popen[str]") -> None:
    """Asks the program to end, as Ctrl+C does."""
    send(proc, signal.SIGBREAK if WINDOWS else signal.SIGINT)  # type: ignore[attr-defined, unused-ignore]
