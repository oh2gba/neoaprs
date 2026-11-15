"""Which other program has a serial device open, for the systems that can say: Linux, through /proc. Elsewhere the answer is "nobody known" and the open itself says no when the port is taken (Windows: access denied)."""
import os
import stat
import sys

from .serialport import is_url, normalize

PROC = "/proc"
PTY_MAJORS = (136, 143)          # the majors of the pseudo-terminals' slaves on Linux (UNIX98_PTY_SLAVE_MAJOR and UNIX98_PTY_MAJOR_COUNT)


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
        device = os.stat(target)
        pids = sorted(int(name) for name in os.listdir(PROC) if name.isdigit())
    except OSError:
        return []
    for pid in pids:
        if pid not in ours and _has_open(pid, target, device):
            found.append(pid)
    return found


def _has_open(pid: int, target: str, device: os.stat_result) -> bool:
    """Whether a descriptor of the process is the device: by its name first, then by what it is (a name is only a name in the process's own /dev)."""
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
    """Whether an open file is the device: the very node, or the same character device through a node of its own (a container's /dev, made with the device's numbers). A pseudo-terminal is numbered within
    its devpts, so /dev/pts/3 of a sandbox, a container or a Flatpak (a devpts of their own) is another terminal by the same name and the same numbers: that one is the very node or none."""
    if (opened.st_dev, opened.st_ino) == (device.st_dev, device.st_ino):
        return True
    return stat.S_ISCHR(device.st_mode) and opened.st_rdev == device.st_rdev and not _is_pty(device.st_rdev)  # type: ignore[attr-defined, unused-ignore]


def _is_pty(rdev: int) -> bool:
    """A pseudo-terminal's slave, by its major (as os.major gives it, which Windows has not: this module is read there too)."""
    return PTY_MAJORS[0] <= (rdev >> 8) & 0xFFF <= PTY_MAJORS[1]


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
    if sys.platform == "darwin" and path.startswith("/dev/tty."):
        path = "/dev/cu." + path.removeprefix("/dev/tty.")                 # (macOS gives one device two nodes: the call-in one and the call-out one, which is the one opened)
    return os.path.realpath(path)
