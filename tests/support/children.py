"""The processes a test starts, so that none outlives its test or the run.

On Linux they are found under this process through the kernel's list of each task's children
(/proc/PID/task/TID/children); elsewhere `descendants` finds none. A stand-in program calls
`end_with_the_run` and ends by itself once the test process that started the run is gone.
"""

import os
import signal
import sys
import threading
import time
from collections.abc import Iterable
from pathlib import Path

RUN_PID = "NEOAPRS_TEST_RUN_PID"
PROC = Path("/proc")
# What a process the test started may take to end once the test is over
END_SEC = 2.0


def supported() -> bool:
    return sys.platform.startswith("linux") and (PROC / "self" / "task").is_dir()


def _children(pid: int) -> set[int]:
    found: set[int] = set()
    try:
        tasks = list((PROC / str(pid) / "task").iterdir())
    except OSError:
        return found
    for task in tasks:
        try:
            found |= {int(child) for child in (task / "children").read_text().split()}
        except (OSError, ValueError):
            pass
    return found


def _state(pid: int) -> str:
    """The process's state letter (Z for one that ended and was not reaped yet); empty when gone."""
    try:
        stat = (PROC / str(pid) / "stat").read_text()
    except OSError:
        return ""
    return stat.rpartition(")")[2].split()[0] if ")" in stat else ""


def descendants(pid: int | None = None, beside: Iterable[int] = ()) -> set[int]:
    """Every live process under `pid` (this one), children of children included, but for those in
    `beside` and everything under them."""
    if not supported():
        return set()
    skip = set(beside)
    seen: set[int] = set()
    todo = [os.getpid() if pid is None else pid]
    while todo:
        for child in _children(todo.pop()):
            if child not in seen and child not in skip:
                seen.add(child)
                todo.append(child)
    return {p for p in seen if _state(p) not in ("", "Z")}


def command_of(pid: int) -> str:
    try:
        return (PROC / str(pid) / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()[:200]
    except OSError:
        return "?"


def left_since(before: set[int], seconds: float = END_SEC) -> set[int]:
    """The processes started since `before` that are still running after `seconds`. What runs under a
    process of `before` (a browser or a daemon of a wider fixture) is that process's own, and ends with it."""
    deadline = time.monotonic() + seconds
    while True:
        left = descendants(beside=before)
        if not left or time.monotonic() >= deadline:
            return left
        time.sleep(0.05)


def end(pids: Iterable[int]) -> None:
    """Kill them. Not reaped here: the Popen of a child reaps it (an unreaped one is a zombie, no process)."""
    for pid in pids:
        try:
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        except OSError:
            pass


def _run_is_over(pid: int) -> None:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32")
        handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return
        kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)  # INFINITE
    else:
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            except OSError:
                pass
            time.sleep(0.5)


def end_with_the_run() -> None:
    """In a stand-in program: end it at once when the test process of the run that started it is gone."""
    try:
        pid = int(os.environ.get(RUN_PID, ""))
    except ValueError:
        return

    def watch() -> None:
        _run_is_over(pid)
        os._exit(0)

    threading.Thread(target=watch, name="neoaprs-test-run-watch", daemon=True).start()
