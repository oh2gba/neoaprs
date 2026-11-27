"""Windows calls for the child programs: a Ctrl-Break, sent by a disposable asker, to ask one to end, a job
that ends them with the daemon, and a serial keying line lowered after a program that held it had to be killed.

Each function takes kernel32 as an argument, so that the logic is tested with a fake elsewhere.
"""

import ctypes
import logging
import re
import subprocess
import sys
import threading
from collections.abc import Callable
from typing import Any

log = logging.getLogger("neoaprs.childprogram")

CTRL_C_EVENT, CTRL_BREAK_EVENT = 0, 1
PROCESS_TERMINATE, PROCESS_SET_QUOTA = 0x0001, 0x0100
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
# The whole lowering of a keying line; a Bluetooth port can take many seconds to open.
DROP_SEC = 2.0
# A serial keying line on Windows: COM3, or COM12
COM_PORT = re.compile(r"^(?:\\\\\.\\)?(COM\d+)$", re.IGNORECASE)


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in ("r_ops", "w_ops", "o_ops", "r_bytes", "w_bytes", "o_bytes")]


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("per_process_user_time", ctypes.c_int64),
        ("per_job_user_time", ctypes.c_int64),
        ("limit_flags", ctypes.c_uint32),
        ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t),
        ("active_process_limit", ctypes.c_uint32),
        ("affinity", ctypes.c_size_t),
        ("priority_class", ctypes.c_uint32),
        ("scheduling_class", ctypes.c_uint32),
    ]


class ExtendedLimits(ctypes.Structure):
    """JOBOBJECT_EXTENDED_LIMIT_INFORMATION."""

    _fields_ = [
        ("basic", BasicLimits),
        ("io", IoCounters),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


_BOOL, _DWORD, _HANDLE = ctypes.c_int, ctypes.c_uint32, ctypes.c_void_p
# the kernel32 calls made here: argument types and result type
CALLS: dict[str, tuple[list[Any], Any]] = {
    "AttachConsole": ([_DWORD], _BOOL),
    "FreeConsole": ([], _BOOL),
    "GenerateConsoleCtrlEvent": ([_DWORD, _DWORD], _BOOL),
    "CreateJobObjectW": ([ctypes.c_void_p, ctypes.c_wchar_p], _HANDLE),
    "SetInformationJobObject": ([_HANDLE, ctypes.c_int, ctypes.c_void_p, _DWORD], _BOOL),
    "AssignProcessToJobObject": ([_HANDLE, _HANDLE], _BOOL),
    "OpenProcess": ([_DWORD, _BOOL, _DWORD], _HANDLE),
    "CloseHandle": ([_HANDLE], _BOOL),
}


def kernel32() -> Any:
    """Return kernel32 with the argument types of CALLS; raise OSError where there is none."""
    if not hasattr(ctypes, "WinDLL"):
        raise OSError("kernel32 is Windows only")
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    for name, (argtypes, restype) in CALLS.items():
        function = getattr(k, name)
        function.argtypes, function.restype = argtypes, restype
    return k


# ---- asking a program to end

Steps = list[dict[str, Any]]
# How long the asker has to say it sent the event (a few calls, but a process start on a slow machine).
ASKER_SEC = 2.0
# The asker's exit codes (neoaprs/winask.py)
SENT, BAD_ARGUMENT, ATTACH_FAILED, EVENT_FAILED = 0, 2, 3, 4
ASKER_FLAG = "--winask"  # the frozen programs' entry starts the asker on this first argument


def _last_error() -> int:
    return int(getattr(ctypes, "get_last_error", lambda: 0)())


def _step(steps: Steps | None, k: Any, name: str, *args: Any) -> Any:
    """Call kernel32's `name`; note the call, its result and GetLastError in `steps` and the log."""
    result = getattr(k, name)(*args)
    error = _last_error() if not result else 0
    log.debug("console ask: %s%s returned %s (error %d)", name, args, result, error)
    if steps is not None:
        steps.append(
            {
                "call": name,
                "args": [a if isinstance(a, int) else str(a) for a in args],
                "result": result,
                "error": error,
            }
        )
    return result


def send_event(pid: int, event: int, group: int, k: Any = None, steps: Steps | None = None) -> int:
    """Send a console event to `group` on the console of the program `pid`; return an asker exit code.

    For the disposable asker only: it lets go of whatever console it has, which a daemon never may.
    """
    k = k if k is not None else kernel32()
    _step(steps, k, "FreeConsole")  # (fails harmlessly when there is none)
    if not _step(steps, k, "AttachConsole", pid):
        return ATTACH_FAILED
    try:
        return SENT if _step(steps, k, "GenerateConsoleCtrlEvent", event, group) else EVENT_FAILED
    finally:
        _step(steps, k, "FreeConsole")


def asker_argv(pid: int, frozen: bool | None = None, executable: str | None = None) -> list[str]:
    """Return the command line of the asker for the program `pid`.

    A frozen build has no `-m`: its own program (neoaprsw.exe, neoaprs.exe) takes ASKER_FLAG first.
    """
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    program = executable or sys.executable
    return [program, ASKER_FLAG, str(pid)] if frozen else [program, "-m", "neoaprs.winask", str(pid)]


def ask_to_end(pid: int, run: Callable[..., Any] | None = None) -> bool:
    """Ask the program `pid` to end: Ctrl-Break to its own process group, sent by a disposable asker so
    that this process never touches its own console; return whether the asker sent it.

    The program was started with CREATE_NEW_PROCESS_GROUP and a console of its own (childprogram.py).
    """
    try:
        done = (run or subprocess.run)(
            asker_argv(pid),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=ASKER_SEC,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log.info("the program %d was not asked to end: the asker did not run (%s)", pid, e)
        return False
    log.debug(
        "console ask for %d: exit %s, %s", pid, done.returncode, (done.stdout or b"").decode("utf-8", "replace").strip()
    )
    return bool(done.returncode == SENT)


# ---- the children's lives tied to the daemon's

_job: int | None = None  # made once; its handle closes when the daemon ends, however it ends
_job_lock = threading.Lock()


def new_job(k: Any) -> int | None:
    """Return a job that ends its processes when its last handle closes; None if it cannot be made."""
    job = k.CreateJobObjectW(None, None)
    if not job:
        return None
    limits = ExtendedLimits()
    limits.basic.limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k.SetInformationJobObject(
        job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)
    ):
        k.CloseHandle(job)
        return None
    return int(job)


def tie_to_daemon(pid: int, k: Any = None) -> bool:
    """Put the process into the daemon's job, so that it ends with the daemon; return whether it is in."""
    global _job
    k = k if k is not None else kernel32()
    with _job_lock:
        if _job is None:
            _job = new_job(k)
        job = _job
    if job is None:
        return False
    process = k.OpenProcess(PROCESS_TERMINATE | PROCESS_SET_QUOTA, False, pid)
    if not process:
        return False
    try:
        return bool(k.AssignProcessToJobObject(job, process))
    finally:
        k.CloseHandle(process)


# ---- the keying line


def _unopened_port() -> Any:
    import serial  # type: ignore[import-untyped]

    return serial.Serial()


def drop_line(keying: str, port: Callable[[], Any] | None = None, wait_sec: float = DROP_SEC) -> bool:
    """Lower the serial keying line of `rts:COM3` or `dtr:COM3`; return whether it was done in `wait_sec`.

    For a program that was killed: some drivers keep a line where it left it. Blocks up to `wait_sec`.
    """
    way, _, device = keying.partition(":")
    match = COM_PORT.match(device.strip())
    if way not in ("rts", "dtr") or match is None:
        return False
    done, lowered = threading.Event(), [False]

    def lower() -> None:
        try:
            # pyserial sets the lines of a port that is not open yet at its open (SetCommState with
            # RTS_CONTROL_DISABLE and DTR_CONTROL_DISABLE), so the port is opened with both low
            ser = (port or _unopened_port)()
            ser.rts, ser.dtr = False, False
            ser.port = match.group(1).upper()
            ser.open()
            ser.close()
            lowered[0] = True
        except Exception as e:  # the port is gone, held or refuses: nothing more can be done
            log.info("the keying line %s could not be lowered: %s", keying, e)
        finally:
            done.set()

    threading.Thread(target=lower, name="neoaprs-keying-line", daemon=True).start()
    if not done.wait(wait_sec):
        log.info("the keying line %s did not open in %g s: it is left as the driver has it", keying, wait_sec)
    return lowered[0]
