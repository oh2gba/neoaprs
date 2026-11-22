"""CPU share and resident memory of the daemon, for the status. Standard library only.

Memory comes from `/proc/self/statm` on Linux, `resource` on macOS and winmemory.py on Windows.
"""
import os
import sys
import time
from collections.abc import Callable
from typing import NamedTuple

from .winmemory import working_set_mb

# A sample closer to the previous one than this repeats the last share; a span of a few clock ticks
# is noise.
MIN_SPAN_SEC = 1.0
_MB = 1024 * 1024


class Sample(NamedTuple):
    at: float  # monotonic seconds
    cpu_sec: float  # user plus system time so far


def cpu_percent(before: Sample, after: Sample) -> float:
    """Return CPU time over wall time between two samples, in percent of one core to a tenth."""
    wall = after.at - before.at
    if wall <= 0:
        return 0.0
    return round(max(0.0, 100.0 * (after.cpu_sec - before.cpu_sec) / wall), 1)


def cpu_seconds() -> float:
    t = os.times()
    return t.user + t.system


def resident_mb() -> float | None:
    """Return the resident set in megabytes to a tenth; None where the system does not say."""
    if sys.platform == "win32":
        return working_set_mb()
    else:
        try:
            if sys.platform == "darwin":
                import resource
                # ru_maxrss is in bytes on macOS and is the peak; the current value has no cheap
                # source.
                return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / _MB, 1)
            with open("/proc/self/statm", encoding="ascii") as f:
                return round(int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / _MB, 1)
        except (OSError, ValueError, IndexError, ImportError):  # ImportError: darwin without `resource`
            return None


class ProcessMeter:
    def __init__(self, now: Callable[[], float] = time.monotonic, cpu: Callable[[], float] = cpu_seconds, rss: Callable[[], float | None] = resident_mb) -> None:
        self._now, self._cpu, self._rss = now, cpu, rss
        self._last = Sample(now(), cpu())
        self._percent = 0.0

    def sample(self) -> tuple[float, float | None]:
        """Return (CPU share since the previous sample, resident megabytes or None).

        Samples less than `MIN_SPAN_SEC` apart share one CPU reading.
        """
        now = Sample(self._now(), self._cpu())
        if now.at - self._last.at >= MIN_SPAN_SEC:
            self._percent, self._last = cpu_percent(self._last, now), now
        return self._percent, self._rss()
