"""The suite's time: the sum of every test's time against a budget, and the tests that are slow
without saying why (tests/README.md, "Time").

A test over SLOW_SEC carries `@pytest.mark.slow("why")`, or `@pytest.mark.nightly("why")`, which
leaves it out of the gate and CI for the nightly run. With NEOAPRS_TEST_BUDGET_SEC set (the gate's
stage pytest sets it), a run fails when its tests took longer in sum, or when a test without either
marker took over UNMARKED_FAIL_SEC: SLOW_SEC with room for a busy machine.
"""

import os

import pytest

SLOW_SEC = 2.0
UNMARKED_FAIL_SEC = 5.0
MARKERS = ("slow", "nightly")


class Clock:
    def __init__(self) -> None:
        self.total = 0.0
        self.calls: dict[str, tuple[float, bool]] = {}  # test: its time, and whether it says why

    def add(self, report: pytest.TestReport) -> None:
        self.total += report.duration
        if report.when == "call":
            self.calls[report.nodeid] = (report.duration, any(m in report.keywords for m in MARKERS))

    def unmarked_over(self, seconds: float) -> list[tuple[str, float]]:
        return sorted(
            ((test, took) for test, (took, said) in self.calls.items() if took > seconds and not said),
            key=lambda each: -each[1],
        )


def budget_sec() -> float | None:
    try:
        value = float(os.environ.get("NEOAPRS_TEST_BUDGET_SEC", ""))
    except ValueError:
        return None
    return value if value > 0 else None


def check_reasons(items: list[pytest.Item]) -> None:
    """A slow or nightly marker without its reason is refused at collection."""
    for item in items:
        for name in MARKERS:
            for mark in item.iter_markers(name):
                reason = mark.args[0] if mark.args else mark.kwargs.get("reason", "")
                if not isinstance(reason, str) or len(reason.split()) < 3:
                    raise pytest.UsageError(f"{item.nodeid}: @pytest.mark.{name} needs a reason of a few words")


def kept(clock: Clock) -> bool:
    """Whether the run kept its budget (always, without one)."""
    budget = budget_sec()
    return budget is None or (clock.total <= budget and not clock.unmarked_over(UNMARKED_FAIL_SEC))


def summary(clock: Clock, seed: object, write: "pytest.TerminalReporter") -> None:
    """Write the order's seed, the time of the run and the tests that are slow without a reason."""
    if seed is not None:
        write.write_line(
            f"random order: seed {seed} (again: --randomly-seed={seed}, or NEOAPRS_TEST_SEED={seed} for scripts/check)"
        )
    budget = budget_sec()
    write.write_line(
        f"the tests took {clock.total:.0f} s in sum" + (f", budget {budget:.0f} s" if budget is not None else "")
    )
    for test, took in clock.unmarked_over(SLOW_SEC)[:30]:
        write.write_line(f"over {SLOW_SEC:g} s without a reason (mark it slow or nightly): {took:.1f}s {test}")
    if budget is not None and clock.total > budget:
        write.write_line(
            f"OVER THE BUDGET: {clock.total:.0f} s of tests, budget {budget:.0f} s (tests/README.md, Time)"
        )
    if budget is not None:
        for test, took in clock.unmarked_over(UNMARKED_FAIL_SEC):
            write.write_line(f"TOO SLOW WITHOUT A REASON: {took:.1f}s {test}")
