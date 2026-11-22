"""The pause between our own frames on a radio, and the burst of what a radio sends again, when the
clock is set back."""
from datetime import timedelta
from types import SimpleNamespace

from neoaprs.services.pace import Pace
from neoaprs.services.passlimits import Burst
from neoaprs.services.sender import Sender
from tests.support.clock import FixedClock


def step_back_an_hour_then_ten_minutes_on(clock: FixedClock) -> None:
    clock.set(clock() - timedelta(hours=1) + timedelta(minutes=10))


def test_a_clock_set_back_does_not_hold_the_next_attempt_of_a_message() -> None:
    clock = FixedClock()
    pace = Pace(clock, 10.0)
    pace.stamp(1)
    assert pace.too_soon(1)
    step_back_an_hour_then_ten_minutes_on(clock)
    assert not pace.too_soon(1)


def test_a_clock_set_back_does_not_hold_the_next_object_or_bulletin() -> None:
    clock = FixedClock()
    sender = Sender(lambda: None, lambda: None, clock, spacing_sec=10.0)        # type: ignore[arg-type]
    radio = SimpleNamespace(id=1)
    sender._last[1] = clock()
    assert sender.too_soon(radio)                                              # type: ignore[arg-type]
    step_back_an_hour_then_ten_minutes_on(clock)
    assert not sender.too_soon(radio)                                          # type: ignore[arg-type]


def test_a_clock_set_back_does_not_keep_a_full_burst_shut() -> None:
    clock = FixedClock()
    burst = Burst(4, 10.0)
    for _ in range(4):
        burst.take(1, clock())
    assert burst.full(1, clock())
    step_back_an_hour_then_ten_minutes_on(clock)
    assert not burst.full(1, clock())
