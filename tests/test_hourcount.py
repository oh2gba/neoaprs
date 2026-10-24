"""The packets of the last hour of a station (neoaprs/hourcount.py): counted for each minute, they leave the hour as it moves on."""
from datetime import timedelta

from neoaprs.clock import utc
from neoaprs.hourcount import HourCount

T0 = utc(2026, 10, 21, 12, 0, 30)


def test_packets_count_until_an_hour_has_passed() -> None:
    hour = HourCount()
    hour.note(T0)
    hour.note(T0 + timedelta(seconds=10))
    hour.note(T0 + timedelta(minutes=10))
    assert hour.count(T0 + timedelta(minutes=10)) == 3
    assert hour.count(T0 + timedelta(minutes=59)) == 3
    assert hour.count(T0 + timedelta(minutes=60)) == 1             # (the minute of the first two is an hour old when its minute 60 begins)
    assert hour.count(T0 + timedelta(minutes=70)) == 0
    assert hour.total == 0


def test_expire_says_whether_the_count_changed() -> None:
    hour = HourCount()
    hour.note(T0)
    assert hour.expire(T0 + timedelta(minutes=30)) is False and hour.total == 1
    assert hour.expire(T0 + timedelta(minutes=61)) is True and hour.total == 0
    assert hour.expire(T0 + timedelta(minutes=62)) is False


def test_a_late_packet_is_counted_with_the_newest_minute() -> None:
    hour = HourCount()
    hour.note(T0 + timedelta(minutes=5))
    hour.note(T0)
    assert hour.total == 2 and hour.count(T0 + timedelta(minutes=64)) == 2 and hour.count(T0 + timedelta(minutes=66)) == 0


def test_a_busy_station_costs_at_most_an_hours_worth_of_minutes() -> None:
    hour = HourCount()
    for second in range(0, 3 * 3600, 2):
        hour.note(T0 + timedelta(seconds=second))
        hour.expire(T0 + timedelta(seconds=second))
    assert len(hour._minutes) <= 61 and hour.total <= 61 * 30
