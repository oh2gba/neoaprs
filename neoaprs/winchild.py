"""Windows calls for the child programs: a console Ctrl-C to ask one to end, a job that ends them with
the daemon, and a serial keying line lowered after a program that held it had to be killed.

Each function takes kernel32 as an argument, so that the logic is tested with a fake elsewhere.
"""

import ctypes
import logging
import re
import threading
import time
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
    "GetConsoleWindow": ([], _HANDLE),
    "GetConsoleProcessList": ([ctypes.POINTER(ctypes.c_uint32), _DWORD], _DWORD),
    "GenerateConsoleCtrlEvent": ([_DWORD, _DWORD], _BOOL),
    "SetConsoleCtrlHandler": ([ctypes.c_void_p, _BOOL], _BOOL),
    "CreateJobObjectW": ([ctypes.c_void_p, ctypes.c_wchar_p], _HANDLE),
    "SetInformationJobObject": ([_HANDLE, ctypes.c_int, ctypes.c_void_p, _DWORD], _BOOL),
    "AssignProcessToJobObject": ([_HANDLE, _HANDLE], _BOOL),
    "OpenProcess": ([_DWORD, _BOOL, _DWORD], _HANDLE),
    "CloseHandle": ([_HANDLE], _BOOL),
}


def user32() -> Any:
    """Return user32 with IsWindowVisible typed; raise OSError where there is none."""
    if not hasattr(ctypes, "WinDLL"):
        raise OSError("user32 is Windows only")
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.IsWindowVisible.argtypes, u.IsWindowVisible.restype = [_HANDLE], _BOOL
    return u


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

_console = threading.Lock()  # a console is attached to by the whole process
_handler: Any = None  # kept alive: Windows calls it from a thread of its own


# Ctrl-C and Ctrl-Break that reach this process up to this long after it sent one are its own echo.
ECHO_SEC = 10.0
_asked_at = -ECHO_SEC  # monotonic time of the latest ask


def ours(event: int, now: float | None = None) -> bool:
    """Return whether a console event is the echo of an ask of this process (it is then taken)."""
    at = time.monotonic() if now is None else now
    return event in (CTRL_C_EVENT, CTRL_BREAK_EVENT) and at - _asked_at < ECHO_SEC


def _handler_routine() -> Any:
    """Return a console control handler that takes the echo of an ask and passes every other event on
    (to Python's own, which stops the daemon on a Ctrl-C or Ctrl-Break of its own terminal)."""
    kind = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
    return kind(ctypes.c_int, ctypes.c_uint32)(lambda event: 1 if ours(event) else 0)


def _swallow_ctrl_c(k: Any, steps: "Steps | None" = None) -> bool:
    """Make this process take no Ctrl-C of a console it attaches to; return whether it is so.

    A handler and not the ignore flag, which every program started later would inherit.
    """
    global _handler
    if _handler is None:
        handler = _handler_routine()
        if not _step(steps, k, "SetConsoleCtrlHandler", handler, True):
            return False
        _handler = handler
    return True


Steps = list[dict[str, Any]]


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


PROCESSES_LOOKED_AT = 8  # (GetConsoleProcessList gives the whole count however many fit)


def console_of_own(k: Any, steps: Steps | None = None, u: Any = None) -> tuple[int, bool]:
    """Return how many processes share this process's console (0: it has none) and whether its window shows."""
    count = int(
        _step(steps, k, "GetConsoleProcessList", (ctypes.c_uint32 * PROCESSES_LOOKED_AT)(), PROCESSES_LOOKED_AT)
    )
    if not count:
        return 0, False
    window = _step(steps, k, "GetConsoleWindow")
    return count, bool(window) and bool(_step(steps, u if u is not None else user32(), "IsWindowVisible", window))


def _onto(pid: int, k: Any, steps: Steps | None, u: Any = None) -> bool:
    """Attach to the console of `pid`, letting go of this process's own hidden one first.

    Only a console this process is alone on and whose window does not show is its own (a launcher such as
    a venv's python.exe gives one); one shared with a shell or a terminal, or one that shows, is kept.
    """
    count, visible = console_of_own(k, steps, u)
    if count > 1 or visible:
        if steps is not None:
            steps.append(
                {"note": f"a console shared by {count} processes, visible: {visible}: it is kept, the program is ended"}
            )
        return False
    if count and not _step(steps, k, "FreeConsole"):
        return False
    return bool(_step(steps, k, "AttachConsole", pid))


def _note_ask() -> None:
    global _asked_at
    _asked_at = time.monotonic()


def _leave(k: Any, steps: Steps | None) -> None:
    """Let go of the program's console; the daemon goes on without one (it needs none)."""
    _step(steps, k, "FreeConsole")
    count = int(
        _step(steps, k, "GetConsoleProcessList", (ctypes.c_uint32 * PROCESSES_LOOKED_AT)(), PROCESSES_LOOKED_AT)
    )
    if steps is not None:
        steps.append({"note": f"after: attached to a console: {bool(count)}"})


def ask_to_end(pid: int, k: Any = None, steps: Steps | None = None, u: Any = None) -> bool:
    """Send Ctrl-C to the console of the program `pid` (its own hidden one); return whether it was sent.

    Each call is noted in `steps` and the log. Ctrl-C, not Ctrl-Break: Mercury's Windows build handles
    SIGINT (it unkeys and ends) but not SIGBREAK. The Ctrl-C reaches this process too, where a handler
    that says handled takes it.
    """
    k = k if k is not None else kernel32()
    with _console:
        if not _swallow_ctrl_c(k, steps):
            return False
        if not _onto(pid, k, steps, u):
            return False
        try:
            _note_ask()
            return bool(_step(steps, k, "GenerateConsoleCtrlEvent", CTRL_C_EVENT, 0))
        finally:
            _leave(k, steps)


def break_group(group: int, attach: bool, k: Any = None, steps: Steps | None = None, u: Any = None) -> bool:
    """Send Ctrl-Break to the process group `group` (a child started with CREATE_NEW_PROCESS_GROUP), on its
    console or this process's own; for the Windows tests that find which way reaches a child."""
    k = k if k is not None else kernel32()
    with _console:
        if not _swallow_ctrl_c(k, steps):
            return False
        if attach and not _onto(group, k, steps, u):
            return False
        try:
            _note_ask()
            return bool(_step(steps, k, "GenerateConsoleCtrlEvent", CTRL_BREAK_EVENT, group))
        finally:
            if attach:
                _leave(k, steps)


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
