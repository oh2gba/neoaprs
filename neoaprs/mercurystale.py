"""A Mercury of ours left behind by a daemon that did not stop cleanly (a crash, a kill, Task Manager, a power cut): it holds the sound card, the keying line and its ports, and nothing ends it when its daemon
dies. Its process id is in `mercury.pid` beside the configuration it was started with (mercuryhelper.Program writes it, a clean stop removes it), and `end_stale` ends the process of that id only when it is
still the radio's own Mercury: on Linux and macOS its command line runs Mercury with the radio's configuration (`-C <radios/<id>/mercury.ini>`), so that the operator's own Mercury, an editor on a file named so and another
radio's Mercury are left alone; on Windows, which reuses ids after a reboot most of all, its program file is the one the radio runs and it was made no later than the file was written. Where that cannot be read,
nothing is ended. mercuryclaims.end_left_behind asks it once at the daemon's start for every radio's file, and each start of a radio's modem asks it for its own."""
import logging
import ntpath
import os
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from .childprogram import _running_windows, _windows_image
from .mercuryhelper import STOP_WAIT_SEC
from .source import os_error_text

log = logging.getLogger("neoaprs.mercury")

MADE_SLACK_SEC = 10.0              # a process made this long after its pid file was written is still the one it names (Windows: the clocks of the file and the process)
STALE_POLL_SEC = 0.05              # how often a Mercury left behind is looked at while it ends
FILETIME_1970 = 116444736000000000  # 1970 in Windows' FILETIME, 100 ns since 1601
PS_TIMEOUT_SEC = 5.0


def runs_with(argv: Sequence[str], ini: Path) -> bool:
    """Whether a command line runs Mercury with this configuration file: `-C` followed by the file (mercury.command writes it so), as it was written or as the same file resolved. The radio's own
    configuration is what makes a process its Mercury, not the word "mercury": an editor on a file of that name, the operator's own Mercury and another radio's are not this radio's."""
    want = os.path.abspath(ini)
    return any(flag == "-C" and (value == str(ini) or os.path.abspath(value) == want) for flag, value in zip(argv, argv[1:]))


def _is_mercury(pid: int, ini: Path, program: Sequence[str], written: float) -> bool:
    """Whether the process of this id is this radio's Mercury. Linux: its command line runs a Mercury with the radio's configuration (`runs_with`: the program's or the module that stands in for it). Windows (which
    reuses process ids, after a reboot most of all, and lets no one read another process's command line simply): it is running, its program file is the one this radio runs (`program`), and it was made no later than
    the file that names it was written (`written`; the file is written just after the program is started), so that another radio's Mercury that got the id after a reboot is not it. os.kill(pid, 0) there is
    TerminateProcess, which would end whatever process has the id before anything is known of it, so the questions are asked of the process's exit code, image path and times. macOS: its command line as `ps`
    gives it holds `-C` and the radio's configuration. Where one cannot be read, the answer is no."""
    cmdline = Path(f"/proc/{pid}/cmdline")
    if cmdline.exists():
        try:
            return runs_with(cmdline.read_bytes().decode("utf-8", "replace").split("\0"), ini)
        except OSError:
            return False
    if sys.platform == "win32":
        return _running_windows(pid) and same_program(_windows_image(pid), program) and made_in_time(_windows_created(pid), written)
    else:                                                          # macOS, and any other system without /proc
        command = _ps_command(pid)
        return command is not None and any(f" -C {path} " in f" {command} " for path in {str(ini), os.path.abspath(ini)})


def _ps_command(pid: int) -> str | None:
    """The command line of the process of this id as `ps` writes it, its arguments joined by spaces (so a path with a space in it is compared whole, not split); None when it cannot be read."""
    try:
        done = subprocess.run(["/bin/ps", "-ww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=PS_TIMEOUT_SEC, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def _windows_created(pid: int) -> float | None:
    """When the Windows process of this id was made, in seconds since 1970 (GetProcessTimes); None when the process cannot be opened or its times cannot be read."""
    import ctypes
    kernel32 = ctypes.windll.kernel32                              # type: ignore[attr-defined, unused-ignore]
    handle = kernel32.OpenProcess(0x1000, False, pid)              # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        times = [ctypes.c_ulonglong() for _ in range(4)]          # FILETIMEs: made, ended, in the kernel, in user mode
        if not kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        return (times[0].value - FILETIME_1970) / 1e7
    finally:
        kernel32.CloseHandle(handle)


def same_program(image: str | None, program: Sequence[str]) -> bool:
    """Whether the program file at this Windows path (either kind of slash, the case aside) is the program this radio runs (`program`, its first word); no when the path is not known: where that cannot be read,
    nothing is ended."""
    return image is not None and bool(program) and _windows_path(image) == _windows_path(program[0])


def _windows_path(path: str) -> str:
    return ntpath.normcase(ntpath.abspath(path.replace("/", "\\")))


def made_in_time(created: float | None, written: float) -> bool:
    """Whether a process made at `created` can be the one a file written at `written` names: made before the file was written (MADE_SLACK_SEC for the clocks of the two); no when the time is not known."""
    return created is not None and created <= written + MADE_SLACK_SEC


def _gone(pid: int) -> bool:
    """Whether the process of this id has ended (a zombie on Linux has: it holds nothing any more)."""
    if sys.platform == "win32":
        return not _running_windows(pid)
    else:
        return _gone_posix(pid)


def _gone_posix(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace").rpartition(")")[2].split()[0] in ("Z", "X")
    except (OSError, IndexError):
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


def end_stale(pid_file: Path, ini: Path, program: Sequence[str]) -> bool:
    """Ends this radio's Mercury that an earlier daemon left running (its id is in the file beside the configuration `ini`, which the program was run with; `program` is what the radio runs), so that it does not
    hold the sound card and the ports, and waits up to STOP_WAIT_SEC for it to go (the start that follows opens the same card); whether one was ended. The file is consumed (one that cannot be removed is a line in
    the log, and the check goes on: the daemon's start never fails on it)."""
    try:
        text, written = pid_file.read_text(encoding="ascii"), pid_file.stat().st_mtime
    except OSError:
        return False
    try:
        pid_file.unlink(missing_ok=True)
    except OSError as e:                                           # (held by a virus scanner, read-only, a folder that cannot be written: the check goes on, the next one asks the same)
        log.warning("the file of a Mercury left behind, %s, could not be removed: %s", pid_file, os_error_text(e))
    try:
        pid = int(text.strip())
    except ValueError:
        return False
    if pid == os.getpid() or pid <= 0 or not _is_mercury(pid, ini, program, written):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    log.warning("a Mercury left behind by an earlier run (process %d) was ended", pid)
    deadline = time.monotonic() + STOP_WAIT_SEC
    while not _gone(pid) and time.monotonic() < deadline:
        time.sleep(STALE_POLL_SEC)
    return True
