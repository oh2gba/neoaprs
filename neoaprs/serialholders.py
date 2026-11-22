"""Find which other program has a serial device open (Linux, through /proc).

Elsewhere nobody is known, and opening the port reports it as taken (Windows: access denied).
"""

import os
import stat
import sys

from .serialport import is_url, normalize

PROC = "/proc"
# slave majors of Linux pseudo-terminals
PTY_MAJORS = (136, 143)


def _on_linux() -> bool:
    return sys.platform.startswith("linux")


def _on_windows() -> bool:
    return sys.platform == "win32"


def holders(path: str) -> list[int]:
    """Return the processes other than this one (and its parent) that have the device open.

    Empty off Linux or for a URL. The parent's pseudo-terminal for us (replay --pty) is ours.
    """
    if is_url(path) or not _on_linux():
        return []
    target = os.path.realpath(path)
    ours = {os.getpid(), os.getppid()}
    found: list[int] = []
    try:
        device = os.stat(target)
        pids = sorted(int(name) for name in os.listdir(PROC) if name.isdigit())
    except OSError:
        return []
    for pid in pids:
        if pid not in ours and _has_open(pid, target, device):
            found.append(pid)
    return found


def _has_open(pid: int, target: str, device: os.stat_result) -> bool:
    """Return whether a descriptor of the process is the device (by name, then identity)."""
    fd_dir = f"{PROC}/{pid}/fd"
    try:
        names = os.listdir(fd_dir)
    except OSError:
        return False
    for name in names:
        try:
            if os.readlink(f"{fd_dir}/{name}") == target and _same_device(os.stat(f"{fd_dir}/{name}"), device):
                return True
        except OSError:
            continue
    return False


def _same_device(opened: os.stat_result, device: os.stat_result) -> bool:
    """Return whether an open file is the device, also through another node (a container's /dev).

    A pseudo-terminal is numbered within its devpts, so only the very same node counts.
    """
    if (opened.st_dev, opened.st_ino) == (device.st_dev, device.st_ino):
        return True
    return stat.S_ISCHR(device.st_mode) and opened.st_rdev == device.st_rdev and not _is_pty(device.st_rdev)  # type: ignore[attr-defined, unused-ignore]


def _is_pty(rdev: int) -> bool:
    """Return whether `rdev` is a pseudo-terminal slave, by major number ."""
    return PTY_MAJORS[0] <= (rdev >> 8) & 0xFFF <= PTY_MAJORS[1]


def _process_name(pid: int) -> str:
    try:
        with open(f"{PROC}/{pid}/comm", encoding="utf-8", errors="replace") as f:
            return f.read().strip() or "?"
    except OSError:
        return "?"


def held_by(path: str) -> str:
    """Return "held by NAME (pid N)", comma-joined for several holders, or "" if none is known."""
    pids = holders(path)
    return "held by " + ", ".join(f"{_process_name(pid)} (pid {pid})" for pid in pids) if pids else ""


def port_key(path: str) -> str:
    """Return a key two names of one port share (links resolved, COM upper case, URL lower case)."""
    if is_url(path):
        return normalize(path).lower()
    if _on_windows():
        name = path.strip()
        return name[4:].upper() if name.startswith("\\\\.\\") else name.upper()
    if sys.platform == "darwin" and path.startswith("/dev/tty."):
        # macOS has a call-in and a call-out node per device; the call-out is opened
        path = "/dev/cu." + path.removeprefix("/dev/tty.")
    return os.path.realpath(path)
