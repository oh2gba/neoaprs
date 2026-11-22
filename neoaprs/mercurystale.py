"""End a Mercury left behind by a daemon that did not stop cleanly.

The process id is read from `mercury.pid`; the process is ended only if it is still the radio's own.
"""

import logging
import ntpath
import os
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from .childprogram import GONE_POLL_SEC, _running_windows, _windows_image, gone, made_before, windows_created
from .mercuryhelper import STOP_WAIT_SEC
from .source import os_error_text

log = logging.getLogger("neoaprs.mercury")

PS_TIMEOUT_SEC = 5.0


def runs_with(argv: Sequence[str], ini: Path) -> bool:
    """Return whether the command line has `-C` followed by the configuration file `ini`."""
    want = os.path.abspath(ini)
    return any(
        flag == "-C" and (value == str(ini) or os.path.abspath(value) == want) for flag, value in zip(argv, argv[1:])
    )


def _is_mercury(pid: int, ini: Path, program: Sequence[str], written: float) -> bool:
    """Return whether the process is this radio's Mercury; False if that cannot be read.

    Windows reuses ids, so there the program file and creation time are checked instead.
    """
    cmdline = Path(f"/proc/{pid}/cmdline")
    if cmdline.exists():
        try:
            return runs_with(cmdline.read_bytes().decode("utf-8", "replace").split("\0"), ini)
        except OSError:
            return False
    if sys.platform == "win32":
        return (
            _running_windows(pid)
            and same_program(_windows_image(pid), program)
            and made_before(windows_created(pid), written)
        )
    else:  # macOS, and any other system without /proc
        command = _ps_command(pid)
        return command is not None and any(
            f" -C {path} " in f" {command} " for path in {str(ini), os.path.abspath(ini)}
        )


def _ps_command(pid: int) -> str | None:
    """Return the process's `ps` command line, or None if unreadable."""
    try:
        done = subprocess.run(
            ["/bin/ps", "-ww", "-o", "command=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=PS_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def same_program(image: str | None, program: Sequence[str]) -> bool:
    """Return whether the Windows path is the radio's program; False if it is unknown."""
    return image is not None and bool(program) and _windows_path(image) == _windows_path(program[0])


def _windows_path(path: str) -> str:
    return ntpath.normcase(ntpath.abspath(path.replace("/", "\\")))


def end_stale(pid_file: Path, ini: Path, program: Sequence[str]) -> bool:
    """End this radio's Mercury left running by an earlier daemon; return whether one was ended.

    Waits up to STOP_WAIT_SEC for it to go. The pid file is always consumed."""
    try:
        text, written = pid_file.read_text(encoding="ascii"), pid_file.stat().st_mtime
    except OSError:
        return False
    try:
        pid_file.unlink(missing_ok=True)
    # e.g. held by a virus scanner or read-only; the check goes on
    except OSError as e:
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
    while not gone(pid) and time.monotonic() < deadline:
        time.sleep(GONE_POLL_SEC)
    return True
