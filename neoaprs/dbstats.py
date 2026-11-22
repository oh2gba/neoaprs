"""What the database thread measures: queue wait, run time, event-loop delivery delay and counts."""

import threading
from collections import deque

WINDOW = 4096  # measurements kept per series for the percentiles


def percentile(sorted_values: list[float], p: float) -> float:
    """Return the nearest-rank percentile of an ascending list; 0.0 if empty."""
    if not sorted_values:
        return 0.0
    return sorted_values[max(0, min(len(sorted_values) - 1, int(p / 100.0 * len(sorted_values) + 0.5) - 1))]


class Series:
    """The last WINDOW measurements of one thing (seconds) and its total."""

    def __init__(self) -> None:
        self.values: deque[float] = deque(maxlen=WINDOW)
        self.count = 0
        self.total = 0.0

    def add(self, seconds: float) -> None:
        self.values.append(seconds)
        self.count += 1
        self.total += seconds

    def summary(self) -> dict[str, float]:
        ordered = sorted(self.values)
        return {
            "n": float(self.count),
            "mean_ms": 1000.0 * self.total / self.count if self.count else 0.0,
            "p50_ms": 1000.0 * percentile(ordered, 50),
            "p99_ms": 1000.0 * percentile(ordered, 99),
            "max_ms": 1000.0 * (ordered[-1] if ordered else 0.0),
        }


class DbStats:
    """Statistics written by the database thread, the submitting thread and the event loop; one
    lock covers all."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.wait = Series()  # queued -> started
        self.run = Series()  # started -> finished, the commit included
        self.delivery = Series()  # answer posted -> loop took it
        self.counts: dict[str, int] = dict.fromkeys(
            (
                "reads",
                "writes",
                "maintenance",
                "appends",
                "batches",
                "errors",
                "withdrawn",
                "cut",
                "poisoned",
                "retried",
                "dropped",
                "lost",
                "slow",
            ),
            0,
        )
        self.max_depth = 0

    def count(self, name: str, n: int = 1) -> int:
        with self._lock:
            self.counts[name] += n
            return self.counts[name]

    def depth(self, depth: int) -> None:
        with self._lock:
            self.max_depth = max(self.max_depth, depth)

    def done(self, kind: str, waited: float, ran: float, failed: bool, n: int = 1) -> None:
        with self._lock:
            self.wait.add(waited)
            self.run.add(ran)
            self.counts[kind] += n
            if failed:
                self.counts["errors"] += 1

    def delivered(self, seconds: float) -> None:
        with self._lock:
            self.delivery.add(seconds)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "queue_wait": self.wait.summary(),
                "run": self.run.summary(),
                "loop_delivery": self.delivery.summary(),
                "max_depth": self.max_depth,
                **self.counts,
            }
