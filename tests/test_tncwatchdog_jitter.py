"""The keep-alive's quiet period (neoaprs/tncwatchdog.py): TNC_CHECK_SEC and a random part of it more, drawn again at every byte, so that the checks never keep step with a station that beacons at a fixed rate."""
from typing import Any

from neoaprs.policy import TNC_CHECK_JITTER, TNC_CHECK_SEC
from neoaprs.tncwatchdog import Watchdog


async def test_each_quiet_period_is_the_check_time_and_a_random_part_of_it_more() -> None:
    dog = Watchdog(object(), TNC_CHECK_SEC)  # type: ignore[arg-type]  (the Tnc is not needed to start a quiet period)
    periods: set[float] = set()
    for _ in range(50):
        dog.heard()
        assert TNC_CHECK_SEC <= dog.quiet_sec <= TNC_CHECK_SEC * (1 + TNC_CHECK_JITTER)
        periods.add(dog.quiet_sec)
    assert len(periods) > 40, "drawn again for every quiet period"


async def test_a_quiet_period_after_an_open_is_drawn_too_and_none_without_checks() -> None:
    dog: Any = Watchdog(object(), 0.0)  # type: ignore[arg-type]
    dog.opened()
    assert dog.quiet_sec == 0.0
