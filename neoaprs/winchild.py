"""Windows calls for the child programs: a console Ctrl-C to ask one to end, a job that ends them with
the daemon, and a serial keying line dropped after a program that held it is gone.

Each function takes kernel32 as an argument, so that the logic is tested with a fake elsewhere.
"""

import ctypes
import logging
import re
import threading
from typing import Any

log = logging.getLogger("neoaprs.childprogram")

CTRL_C_EVENT = 0
PROCESS_TERMINATE, PROCESS_SET_QUOTA = 0x0001, 0x0100
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
GENERIC_READ, GENERIC_WRITE, OPEN_EXISTING = 0x80000000, 0x40000000, 3
INVALID_HANDLE = -1
CLRRTS, CLRDTR = 4, 6
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
    "SetConsoleCtrlHandler": ([ctypes.c_void_p, _BOOL], _BOOL),
    "CreateJobObjectW": ([ctypes.c_void_p, ctypes.c_wchar_p], _HANDLE),
    "SetInformationJobObject": ([_HANDLE, ctypes.c_int, ctypes.c_void_p, _DWORD], _BOOL),
    "AssignProcessToJobObject": ([_HANDLE, _HANDLE], _BOOL),
    "OpenProcess": ([_DWORD, _BOOL, _DWORD], _HANDLE),
    "CloseHandle": ([_HANDLE], _BOOL),
    "CreateFileW": ([ctypes.c_wchar_p, _DWORD, _DWORD, ctypes.c_void_p, _DWORD, _DWORD, _HANDLE], _HANDLE),
    "EscapeCommFunction": ([_HANDLE, _DWORD], _BOOL),
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

_console = threading.Lock()  # a console is attached to by the whole process
_handler: Any = None  # kept alive: Windows calls it from a thread of its own


def _handler_routine() -> Any:
    """Return a console control handler that says each event was handled."""
    kind = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
    return kind(ctypes.c_int, ctypes.c_uint32)(lambda event: 1)


def _swallow_ctrl_c(k: Any) -> bool:
    """Make this process take no Ctrl-C of a console it attaches to; return whether it is so.

    A handler and not the ignore flag, which every program started later would inherit.
    """
    global _handler
    if _handler is None:
        handler = _handler_routine()
        if not k.SetConsoleCtrlHandler(handler, True):
            return False
        _handler = handler
    return True


def ask_to_end(pid: int, k: Any = None) -> bool:
    """Send Ctrl-C to the console of the program `pid` (its own hidden one); return whether it was sent.

    False when this process has a console of its own: it cannot attach to another.
    """
    k = k if k is not None else kernel32()
    with _console:
        if not k.AttachConsole(pid):
            return False
        try:
            # without the handler the Ctrl-C would end this process too
            return _swallow_ctrl_c(k) and bool(k.GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0))
        finally:
            k.FreeConsole()


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


def drop_line(keying: str, k: Any = None) -> bool:
    """Lower the serial keying line `rts:COM3` or `dtr:COM3`; return whether it was lowered.

    Some serial drivers keep a line where a program that ended left it.
    """
    way, _, device = keying.partition(":")
    match = COM_PORT.match(device.strip())
    if way not in ("rts", "dtr") or match is None:
        return False
    k = k if k is not None else kernel32()
    handle = k.CreateFileW(
        f"\\\\.\\{match.group(1).upper()}", GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None
    )
    if not handle or handle in (INVALID_HANDLE, ctypes.c_void_p(INVALID_HANDLE).value):
        log.info("the keying line %s could not be opened to lower it", keying)
        return False
    try:
        return bool(k.EscapeCommFunction(handle, CLRRTS if way == "rts" else CLRDTR))
    finally:
        k.CloseHandle(handle)
