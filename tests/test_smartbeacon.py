"""SmartBeaconing (neoaprs/smartbeacon.py): the rate at each speed, the threshold of a turn, and the decision for every branch, with Dire Wolf's numbers (100 km/h, 60 s, 8 km/h, 1800 s, 30 degrees, 15 s, 255)."""
from datetime import timedelta

import pytest

from neoaprs.clock import utc
from neoaprs.smartbeacon import MPH_KMH, Decision, Sent, SmartSettings, decide, heading_change_deg, rate_sec, turn_threshold_deg

S = SmartSettings()
T0 = utc(2026, 10, 25, 12, 0, 0)


def after(seconds: float):                                                  # type: ignore[no-untyped-def]
    return T0 + timedelta(seconds=seconds)


@pytest.mark.parametrize(("speed", "seconds"), [
    (0.0, 1800.0), (4.0, 1800.0), (8.0, 1800.0),                              # at or below the slow speed: the slow rate
    (8.01, pytest.approx(60 * 100 / 8.01)), (9.0, pytest.approx(60 * 100 / 9.0)), (20.0, 300.0), (50.0, 120.0), (80.0, 75.0), (99.9, pytest.approx(60 * 100 / 99.9)),
    (100.0, 60.0), (130.0, 60.0), (300.0, 60.0)])                            # at or above the fast speed: the fast rate
def test_the_rate_is_the_slow_one_up_to_the_slow_speed_the_fast_one_from_the_fast_speed_and_inverse_to_the_speed_between(speed: float, seconds: float) -> None:
    assert rate_sec(S, speed) == seconds


def test_the_rate_follows_the_numbers_it_is_given() -> None:
    mine = SmartSettings(fast_kmh=60, fast_sec=30, slow_kmh=5, slow_sec=600)
    assert [rate_sec(mine, v) for v in (3, 5, 30, 60, 90)] == [600, 600, 60, 30, 30]


@pytest.mark.parametrize(("now", "then", "change"), [(0, 0, 0), (10, 350, 20), (350, 10, 20), (90, 270, 180), (270, 90, 180), (359, 1, 2), (180, 0, 180), (45, 100, 55), (200, 100, 100), (0, 359, 1)])
def test_the_heading_change_is_the_smaller_angle_between_the_courses(now: int, then: int, change: int) -> None:
    assert heading_change_deg(now, then) == change


@pytest.mark.parametrize(("kmh", "degrees"), [
    (10.0, 30 + 255 / (10.0 / MPH_KMH)), (30.0, 30 + 255 / (30.0 / MPH_KMH)), (60.0, 30 + 255 / (60.0 / MPH_KMH)), (100.0, 30 + 255 / (100.0 / MPH_KMH))])
def test_the_turn_threshold_is_the_minimum_plus_the_slope_over_the_speed_in_miles_per_hour(kmh: float, degrees: float) -> None:
    assert turn_threshold_deg(S, kmh) == pytest.approx(degrees)


def test_the_turn_threshold_falls_as_the_station_goes_faster() -> None:
    assert turn_threshold_deg(S, 10.0) == pytest.approx(71.04, abs=0.01)
    assert turn_threshold_deg(S, 100.0) == pytest.approx(30 + 255 / 62.137, abs=0.01)
    assert turn_threshold_deg(S, 10.0) > turn_threshold_deg(S, 50.0) > turn_threshold_deg(S, 100.0) > 30


def test_the_first_fix_is_beaconed_at_once_whatever_the_speed() -> None:
    for speed in (None, 0.0, 5.0, 50.0, 140.0):
        assert decide(S, None, T0, speed, 90) == Decision("start", None)


def test_a_request_is_beaconed_at_once_with_or_without_an_earlier_beacon() -> None:
    last = Sent(T0, 90)
    assert decide(S, last, after(1), 50.0, 90, request=True) == Decision("request", after(120))
    assert decide(S, None, T0, 50.0, 90, request=True) == Decision("request", None)


# ---- the time

@pytest.mark.parametrize(("speed", "gap", "reason"), [
    (0.0, 1799, None), (0.0, 1800, "time"), (0.0, 5000, "time"),                          # standing still: every 30 minutes
    (None, 1799, None), (None, 1800, "time"),                                              # no speed is standing still
    (8.0, 1799, None), (8.0, 1800, "time"),
    (50.0, 119, None), (50.0, 120, "time"),                                                # 50 km/h: every 2 minutes
    (80.0, 74, None), (80.0, 75, "time"),
    (100.0, 59, None), (100.0, 60, "time"), (130.0, 59, None), (130.0, 61, "time")])       # fast: every minute
def test_a_beacon_by_time_when_the_interval_of_the_speed_has_passed(speed: float | None, gap: float, reason: str | None) -> None:
    assert decide(S, Sent(T0, 90), after(gap), speed, 90).reason == reason


@pytest.mark.parametrize(("speed", "due"), [(0.0, 1800), (4.0, 1800), (20.0, 300), (50.0, 120), (100.0, 60)])
def test_the_next_beacon_by_time_is_the_last_one_plus_the_rate_of_the_speed_now(speed: float, due: int) -> None:
    assert decide(S, Sent(T0, 90), after(10), speed, 90).next_due == after(due)


def test_a_station_that_speeds_up_has_its_next_beacon_brought_forward() -> None:
    last = Sent(T0, 90)
    assert decide(S, last, after(10), 5.0, 90).next_due == after(1800)
    assert decide(S, last, after(100), 50.0, 90).next_due == after(120)
    assert decide(S, last, after(121), 50.0, 90).reason == "time", "the slow beacon that was 29 minutes away is due now that it goes 50 km/h"


# ---- corner pegging

def turn(speed: float, change: int, gap: float = 20.0, then: int | None = 90) -> str | None:
    course = None if then is None else (then + change) % 360
    return decide(S, Sent(T0, then), after(gap), speed, course).reason


def test_a_turn_of_more_than_the_threshold_at_speed_is_beaconed() -> None:
    assert turn(60.0, 40) == "turn", "the threshold at 60 km/h is 30 + 6.8 = 36.8 degrees"
    assert turn(60.0, 36) is None
    assert turn(60.0, -40) == "turn" and turn(60.0, 37) == "turn"


def test_a_slower_station_must_turn_more() -> None:
    assert turn(10.0, 60) is None, "the threshold at 10 km/h is 71 degrees"
    assert turn(10.0, 72) == "turn"
    assert turn(100.0, 40) == "turn" and turn(100.0, 34) is None


def test_the_turn_is_the_smaller_angle_across_north() -> None:
    assert decide(S, Sent(T0, 350), after(20), 60.0, 30).reason == "turn", "350 to 30 is 40 degrees"
    assert decide(S, Sent(T0, 350), after(20), 60.0, 10).reason is None, "350 to 10 is 20 degrees"
    assert turn(60.0, 180) == "turn"


def test_a_turn_waits_for_the_least_time_since_the_last_beacon() -> None:
    assert turn(60.0, 90, gap=14.0) is None
    assert turn(60.0, 90, gap=15.0) == "turn"


def test_no_turn_is_beaconed_at_or_below_the_slow_speed() -> None:
    assert turn(8.0, 170) is None and turn(3.0, 170) is None and turn(0.0, 170) is None
    assert turn(8.5, 170) == "turn"


def test_no_turn_without_a_course_now_or_at_the_last_beacon() -> None:
    assert decide(S, Sent(T0, 90), after(20), 60.0, None).reason is None
    assert turn(60.0, 90, then=None) is None


def test_a_turn_is_not_beaconed_while_a_beacon_by_time_is_due_it_is_the_time_that_goes() -> None:
    assert decide(S, Sent(T0, 90), after(130), 50.0, 270).reason == "time"


def test_a_turn_changes_the_baseline_of_the_next_one() -> None:
    """The course of the last beacon is the baseline: the bend that follows the turn is measured from the turn, not from the start."""
    first = decide(S, Sent(T0, 90), after(20), 60.0, 180)
    assert first.reason == "turn"
    assert decide(S, Sent(after(20), 180), after(40), 60.0, 190).reason is None
    assert decide(S, Sent(after(20), 180), after(40), 60.0, 270).reason == "turn"


def test_a_drive_beacons_at_the_corner_and_on_the_straight_and_rarely_when_stopped() -> None:
    """A made-up minute-by-minute drive: stopped, away at 50 km/h, a corner, 100 km/h on the straight, stopped."""
    last: Sent | None = None
    sent: list[tuple[int, str]] = []
    drive = [(0, 0.0, 0)] * 5 + [(t, 50.0, 0) for t in range(5, 130)] + [(t, 40.0, 90) for t in range(130, 140)] + [(t, 100.0, 90) for t in range(140, 260)] + [(t, 0.0, 90) for t in range(260, 600)]
    for second, speed, course in drive:
        decision = decide(S, last, after(second), speed, course)
        if decision.reason is not None:
            last = Sent(after(second), course)
            sent.append((second, decision.reason))
    assert [r for _, r in sent][:3] == ["start", "time", "turn"] and sent[0][0] == 0
    assert sent[1][0] == 120 and sent[2][0] == 135, "the corner at 130 is 10 seconds after the beacon by time: it waits for the 15"
    assert all(b - a >= 15 for (a, _), (b, _) in zip(sent, sent[1:])), "never closer than the turn time"
    assert [s for s, _ in sent if s > 135] == [195, 255], "a minute apart at 100 km/h"
    assert sent[-1][0] == 255, "stopped for 340 seconds after that: nothing, the next is 30 minutes after the last"
