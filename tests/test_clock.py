"""The clock (neoaprs/clock.py): every time is UTC and aware; a clock is a function so that a test can hold it."""
import random
from datetime import UTC, date, datetime, time, timedelta, timezone

import pytest

from neoaprs.clock import at, days, from_unix, from_unix_clamped, from_unix_or_none, hhmm, iso, secs_between, span_text, to_unix, utc, utcnow
from tests.support.clock import FixedClock


def reference(t: datetime | None) -> str | None:
    """iso as the plain conversion and strftime write it."""
    if t is None:
        return None
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_utcnow_is_aware_and_utc() -> None:
    now = utcnow()
    assert now.tzinfo is UTC and abs(secs_between(now, datetime.now(tz=UTC))) < 5


def test_iso_writes_what_the_conversion_and_strftime_write() -> None:
    rng = random.Random(11)
    zones = [UTC, timezone(timedelta(hours=2)), timezone(timedelta(hours=-5, minutes=-30)), timezone(timedelta(0))]
    for _ in range(2000):
        t = from_unix(rng.uniform(-2e9, 4.2e9)).replace(microsecond=rng.choice((0, 1, 999999, rng.randrange(1000000))))
        t = t.astimezone(rng.choice(zones))
        assert iso(t) == reference(t), t
    assert iso(None) is None


def test_iso_at_the_edges() -> None:
    assert iso(utc(2026, 10, 21, 18, 5, 0)) == "2026-10-21T18:05:00Z"
    assert iso(from_unix(0)) == "1970-01-01T00:00:00Z"
    assert iso(datetime(2026, 10, 9, 18, 5, 59, 999999, tzinfo=UTC)) == "2026-10-09T18:05:59Z"      # the fraction is cut, not rounded
    assert iso(datetime(2026, 10, 9, 23, 30, tzinfo=timezone(timedelta(hours=-3)))) == "2026-10-10T02:30:00Z"
    for t in (datetime(5, 1, 1, tzinfo=UTC), datetime(999, 12, 31, 23, 59, 59, tzinfo=UTC), datetime(1000, 1, 1, tzinfo=UTC), datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC)):
        assert iso(t) == reference(t)


def test_unix_seconds_round_trip() -> None:
    t = utc(2026, 10, 21, 12, 30, 15)
    assert to_unix(t) == 1792585815 and from_unix(to_unix(t)) == t


def test_a_number_from_outside_that_is_no_time_is_none_or_clamped() -> None:
    assert from_unix_or_none(float("nan")) is None and from_unix_or_none(float("inf")) is None and from_unix_or_none(1e18) is None
    assert from_unix_or_none(0) == utc(1970, 1, 1)
    assert from_unix_clamped(9 * 10**18).year == 9999 and from_unix_clamped(-9 * 10**18).year == 1
    assert from_unix_clamped(86400) == utc(1970, 1, 2)


@pytest.mark.parametrize("seconds, words", [(-5, "0 min"), (0, "0 min"), (90, "1 min"), (3600, "1 h"), (4800, "1 h 20 min"), (86400, "1 d"), (90000, "1 d 1 h"), (2 * 86400 + 3 * 3600, "2 d 3 h")])
def test_a_duration_in_words(seconds: float, words: str) -> None:
    assert span_text(seconds) == words


def test_the_small_helpers() -> None:
    assert at(date(2026, 10, 21), time(18, 5)) == utc(2026, 10, 21, 18, 5)
    assert secs_between(utc(2026, 10, 21, 12), utc(2026, 10, 21, 12, 1)) == 60.0 and secs_between(utc(2026, 10, 21, 12, 1), utc(2026, 10, 21, 12)) == -60.0
    assert hhmm(datetime(2026, 10, 21, 20, 5, tzinfo=timezone(timedelta(hours=2)))) == "18:05"
    assert days(2) == timedelta(days=2)


def test_the_fixed_clock_stands_still_until_it_is_moved() -> None:
    clock = FixedClock()
    first = clock()
    assert clock() == first
    clock.advance(90)
    assert secs_between(first, clock()) == 90.0
    clock.set(utc(2030, 1, 1))
    assert clock() == utc(2030, 1, 1)
