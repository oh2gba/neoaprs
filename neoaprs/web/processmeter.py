"""What the daemon costs the machine, for the status: its CPU share since the previous sample, its resident memory. Standard library only (`os.times` for the CPU; for the memory `/proc/self/statm` on Linux, `resource` on macOS, the working set on Windows: `neoaprs/web/winmemory.py`).

`cpu_percent` is a pure function of two samples; `ProcessMeter` takes them."""
import os
import sys
import time
from collections.abc import Callable
from typing import NamedTuple

from .winmemory import working_set_mb

MIN_SPAN_SEC = 1.0                 # a sample closer to the previous one than this repeats the last share: a span of a few ticks of the clock says nothing
_MB = 1024 * 1024


class Sample(NamedTuple):
    at: float                      # a monotonic clock, in seconds
    cpu_sec: float                 # the process's user and system time so far


def cpu_percent(before: Sample, after: Sample) -> float:
    """The CPU time used between two samples as a share of the wall time between them, in percent of one core, to a tenth; 0 for a span that is none."""
    wall = after.at - before.at
    if wall <= 0:
        return 0.0
    return round(max(0.0, 100.0 * (after.cpu_sec - before.cpu_sec) / wall), 1)


def cpu_seconds() -> float:
    """User and system time of this process so far."""
    t = os.times()
    return t.user + t.system


def resident_mb() -> float | None:
    """The resident set of this process in megabytes, to a tenth; None where the system does not say (the status shows none)."""
    if sys.platform == "win32":
        return working_set_mb()
    else:
        try:
            if sys.platform == "darwin":
                import resource
                return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / _MB, 1)     # (bytes on macOS, and the peak: there is no cheaper reading of the current one)
            with open("/proc/self/statm", encoding="ascii") as f:
                return round(int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / _MB, 1)
        except (OSError, ValueError, IndexError):
            return None


class ProcessMeter:
    def __init__(self, now: Callable[[], float] = time.monotonic, cpu: Callable[[], float] = cpu_seconds, rss: Callable[[], float | None] = resident_mb) -> None:
        self._now, self._cpu, self._rss = now, cpu, rss
        self._last = Sample(now(), cpu())
        self._percent = 0.0

    def sample(self) -> tuple[float, float | None]:
        """The CPU share since the previous sample (or since the start, for the first) and the resident memory in megabytes (None when the system does not say). Two samples less than `MIN_SPAN_SEC` apart share one reading."""
        now = Sample(self._now(), self._cpu())
        if now.at - self._last.at >= MIN_SPAN_SEC:
            self._percent, self._last = cpu_percent(self._last, now), now
        return self._percent, self._rss()
