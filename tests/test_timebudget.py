"""The suite's time (tests/support/timebudget.py): the sum against the budget, the tests slow without a
reason, and a marker without one refused."""

from types import SimpleNamespace
from typing import Any

import pytest

from tests.support import timebudget


def report(test: str, seconds: float, when: str = "call", *marks: str) -> Any:
    return SimpleNamespace(nodeid=test, duration=seconds, when=when, keywords={test: 1, **{m: 1 for m in marks}})


def clock(*reports: Any) -> timebudget.Clock:
    made = timebudget.Clock()
    for each in reports:
        made.add(each)
    return made


class Lines:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write_line(self, line: str) -> None:
        self.lines.append(line)


def test_every_phase_counts_to_the_sum_and_a_slow_call_without_a_marker_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NEOAPRS_TEST_BUDGET_SEC", raising=False)
    run = clock(
        report("t::a", 1.0, "setup"),
        report("t::a", 3.0),
        report("t::b", 4.0, "call", "slow"),
        report("t::c", 9.0, "call", "nightly"),
        report("t::d", 0.5),
    )
    assert run.total == 17.5 and run.unmarked_over(timebudget.SLOW_SEC) == [("t::a", 3.0)]
    assert timebudget.kept(run), "no budget, nothing fails"
    said = Lines()
    timebudget.summary(run, 1234, said)  # type: ignore[arg-type]
    assert said.lines == [
        "random order: seed 1234 (again: --randomly-seed=1234, or NEOAPRS_TEST_SEED=1234 for scripts/check)",
        "the tests took 18 s in sum",
        "over 2 s without a reason (mark it slow or nightly): 3.0s t::a",
    ]


def test_with_a_budget_a_run_over_it_or_with_a_test_far_too_slow_and_unmarked_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEOAPRS_TEST_BUDGET_SEC", "20")
    assert timebudget.kept(clock(report("t::a", 4.9), report("t::b", 15.0, "call", "slow")))
    over = clock(report("t::a", 21.0, "call", "slow"))
    assert not timebudget.kept(over)
    said = Lines()
    timebudget.summary(over, None, said)  # type: ignore[arg-type]
    assert said.lines[-1] == "OVER THE BUDGET: 21 s of tests, budget 20 s (tests/README.md, Time)"
    slow = clock(report("t::a", 5.5))
    assert not timebudget.kept(slow), "past 5 s a test must say why"
    monkeypatch.setenv("NEOAPRS_TEST_BUDGET_SEC", "0")
    assert timebudget.kept(over) and timebudget.kept(slow), "0 is no budget"


@pytest.mark.parametrize("mark", [pytest.mark.slow, pytest.mark.nightly])
def test_a_marker_needs_a_reason_of_a_few_words(mark: Any) -> None:
    def item(*args: object, **kwargs: object) -> Any:
        marker = mark(*args, **kwargs).mark
        return SimpleNamespace(nodeid="t::x", iter_markers=lambda name: [marker] if name == marker.name else [])

    timebudget.check_reasons([item("starts the daemon as a process"), item(reason="six radios for a day")])
    for bad in (item(), item("slow"), item(3)):
        with pytest.raises(pytest.UsageError, match="needs a reason"):
            timebudget.check_reasons([bad])
