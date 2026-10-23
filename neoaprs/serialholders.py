"""Which other program has a serial device open, for the systems that can say: Linux, through /proc. Elsewhere the answer is "nobody known" and the open itself says no when the port is taken (Windows: access denied)."""
import os
import sys

from .serialport import is_url, normalize

PROC = "/proc"


def _on_linux() -> bool:
    return sys.platform.startswith("linux")


def _on_windows() -> bool:
    return sys.platform == "win32"


def holders(path: str) -> list[int]:
    """The processes other than this one that have the device open: `path` is resolved (a link such as /dev/brainbox_2 to /dev/ttyUSB1) and every /proc/PID/fd that can be read is looked through. A process
    that cannot be read is skipped; not on Linux, or for a socket URL, the answer is an empty list. This is the only way to learn of a program that opened the port without a lock (Hamlib's rotctld does).
    The process that started us does not count: a pseudo-terminal it made for us and keeps open (the tests, neoaprs replay --pty) is ours to use, not a competitor's."""
    if is_url(path) or not _on_linux():
        return []
    target = os.path.realpath(path)
    ours = {os.getpid(), os.getppid()}
    found: list[int] = []
    try:
        pids = sorted(int(name) for name in os.listdir(PROC) if name.isdigit())
    except OSError:
        return []
    for pid in pids:
        if pid not in ours and _has_open(pid, target):
            found.append(pid)
    return found


def _has_open(pid: int, target: str) -> bool:
    fd_dir = f"{PROC}/{pid}/fd"
    try:
        names = os.listdir(fd_dir)
    except OSError:
        return False
    for name in names:
        try:
            if os.readlink(f"{fd_dir}/{name}") == target:
                return True
        except OSError:
            continue
    return False


def _process_name(pid: int) -> str:
    try:
        with open(f"{PROC}/{pid}/comm", encoding="utf-8", errors="replace") as f:
            return f.read().strip() or "?"
    except OSError:
        return "?"


def held_by(path: str) -> str:
    """"held by rotctld (pid 300207)" (several holders: joined by commas), or "" when no other process is known to have the device open."""
    pids = holders(path)
    return "held by " + ", ".join(f"{_process_name(pid)} (pid {pid})" for pid in pids) if pids else ""


def port_key(path: str) -> str:
    """What two names of one port have in common, for comparing them: a device file resolved through its links, a COM port in upper case without the `\\\\.\\` prefix, a URL by its `socket://` form, in lower case."""
    if is_url(path):
        return normalize(path).lower()
    if _on_windows():
        name = path.strip()
        return name[4:].upper() if name.startswith("\\\\.\\") else name.upper()
    return os.path.realpath(path)
