"""The working set of this process on Windows (the part of its memory that is in RAM, what Task Manager shows as Memory), from `GetProcessMemoryInfo` of psapi through ctypes: no dependency.
Anywhere else, and wherever the call fails, there is no answer (None) and the status shows none."""
import ctypes
import sys
from ctypes import wintypes

_MB = 1024 * 1024


class _Counters(ctypes.Structure):
    """PROCESS_MEMORY_COUNTERS of psapi.h; `cb` is its size, the rest is filled by the call."""
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def working_set_mb() -> float | None:
    """The working set of this process in megabytes, to a tenth; None when this is not Windows or the system does not say."""
    if sys.platform == "win32":
        try:
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            counters = _Counters()
            counters.cb = ctypes.sizeof(_Counters)
            if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                return round(float(counters.WorkingSetSize) / _MB, 1)
        except (OSError, AttributeError):
            pass
    return None
