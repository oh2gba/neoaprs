"""The packets of the last hour of a station (neoaprs/hourcount.py): counted for each minute, they
leave the hour as it moves on."""

from datetime import timedelta

from neoaprs.clock import utc
from neoaprs.hourcount import HourCount
from neoaprs.station import Station
from neoaprs.stationnotes import expire_hours

T0 = utc(2026, 10, 21, 12, 0, 30)


def test_packets_count_until_an_hour_has_passed() -> None:
    hour = HourCount()
    hour.note(T0)
    hour.note(T0 + timedelta(seconds=10))
    hour.note(T0 + timedelta(minutes=10))
    assert hour.count(T0 + timedelta(minutes=10)) == 3
    assert hour.count(T0 + timedelta(minutes=59)) == 3
    # (the minute of the first two is an hour old when its minute 60 begins)
    assert hour.count(T0 + timedelta(minutes=60)) == 1
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
    assert (
        hour.total == 2 and hour.count(T0 + timedelta(minutes=64)) == 2 and hour.count(T0 + timedelta(minutes=66)) == 0
    )


def test_a_busy_station_costs_at_most_an_hours_worth_of_minutes() -> None:
    hour = HourCount()
    for second in range(0, 3 * 3600, 2):
        hour.note(T0 + timedelta(seconds=second))
        hour.expire(T0 + timedelta(seconds=second))
    assert len(hour._minutes) <= 61 and hour.total <= 61 * 30


def test_over_a_day_a_stations_counts_of_the_internet_and_of_gateways_stay_within_the_hour() -> None:
    """A station heard every 10 minutes through APRS-IS and through an iGate for a day keeps an hour of
    minutes in each of its counts, as the daemon's minute expiry runs (stationnotes.expire_hours)."""
    station = Station("OH2ABC", first_heard=T0, last_heard=T0)
    changed: list[str] = []
    for step in range(24 * 60):
        now = T0 + timedelta(minutes=step)
        if step % 10 == 0:
            for count in (station.hour, station.hour_is if step % 20 == 0 else station.hour_gated):
                count.note(now)
        expire_hours([station], now, lambda s: changed.append(s.call))
    for count in (station.hour, station.hour_is, station.hour_gated):
        assert len(count._minutes) <= 6, "an hour of minutes, not a day of them"
