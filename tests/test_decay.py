"""The schedules of what we send of our own accord (neoaprs/decay.py): the net cycle time of a path,
the decay of an object, the kill and the plans of a bulletin and an announcement."""

import pytest

from neoaprs.decay import (
    KILL_SENDS,
    Plan,
    bulletin_plan,
    bulletin_wait_sec,
    hops,
    kill_wait_sec,
    net_cycle_sec,
    object_wait_sec,
)


@pytest.mark.parametrize(
    "path, count",
    [
        ((), 0),
        (("WIDE1-1",), 1),
        (("WIDE1-1", "WIDE2-1"), 2),
        (("WIDE2-2",), 2),
        (("WIDE3-3",), 3),
        (("OH2RCH-2",), 1),
        (("OH2RCH-2", "OH2RDG", "OH2RCH-1"), 3),
        (("WIDE1-1*", "WIDE2-1"), 2),
        (("TRACE3-3",), 3),
        (("WIDE2-1", "RFONLY"), 1),
        (("NOGATE",), 0),
        (("WIDE1-1", "TCPIP"), 1),
        (("RELAY",), 1),
        (("WIDE2",), 2),
        (("SS3-3",), 3),
        (("HOP7-7",), 7),
        (("FI2-2",), 2),
        (("FI2-2*",), 2),
        (("WIDE1-1", "SS2-2"), 3),
        (("ARISS",), 1),
        (("WIDEX1",), 1),
    ],
)
def test_a_path_asks_for_the_hops_its_calls_and_aliases_have_left(path: tuple[str, ...], count: int) -> None:
    assert hops(path) == count


@pytest.mark.parametrize(
    "path, minutes",
    [
        ((), 10),
        (("WIDE1-1",), 10),
        (("WIDE1-1", "WIDE2-1"), 20),
        (("WIDE2-2",), 20),
        (("WIDE3-3",), 30),
        (("A1", "B2", "C3", "D4"), 30),
        (("SS3-3",), 30),
        (("SS2-2",), 20),
    ],
)
def test_the_net_cycle_time_is_10_minutes_to_one_digipeater_20_to_two_and_30_from_three_on(
    path: tuple[str, ...], minutes: int
) -> None:
    assert net_cycle_sec(path) == minutes * 60


def test_an_object_decays_from_a_minute_by_doubling_up_to_the_net_cycle_time_of_its_path() -> None:
    assert [object_wait_sec(n, ("WIDE2-1",)) for n in range(1, 9)] == [60, 120, 240, 480, 600, 600, 600, 600]
    assert [object_wait_sec(n, ("WIDE1-1", "WIDE2-1")) for n in range(1, 9)] == [
        60,
        120,
        240,
        480,
        960,
        1200,
        1200,
        1200,
    ]
    assert [object_wait_sec(n, ("WIDE3-3",)) for n in range(1, 9)] == [60, 120, 240, 480, 960, 1800, 1800, 1800]
    assert [object_wait_sec(n, (), 1800) for n in range(1, 9)] == [60, 120, 240, 480, 960, 1800, 1800, 1800], (
        "a radio's floor above the net cycle: the decay stays, the repeats keep the floor"
    )
    assert [object_wait_sec(n, ("WIDE3-3",), 600) for n in (1, 6)] == [60, 1800], (
        "a floor below the net cycle changes nothing"
    )


def test_a_kill_is_sent_three_times_a_minute_and_two_apart() -> None:
    assert KILL_SENDS == 3
    assert [kill_wait_sec(n) for n in (1, 2, 3, 4)] == [60, 120, None, None]


BULLETIN, ANNOUNCEMENT = bulletin_plan(False, 4), bulletin_plan(True, 72)


def test_a_bulletin_goes_out_early_twice_more_and_then_every_20_minutes_until_4_hours_after_the_first() -> None:
    times, sent = [0], 1
    while (wait := bulletin_wait_sec(BULLETIN, sent, times[-1])) is not None:
        times.append(times[-1] + wait)
        sent += 1
    assert times[:6] == [0, 120, 360, 1560, 2760, 3960] and times[-1] == 6 * 60 + 11 * 1200 == 13560 and sent == 14
    assert times[-1] <= 4 * 3600 < times[-1] + 1200


def test_an_announcement_goes_out_early_twice_more_and_then_every_hour_until_72_hours_after_the_first() -> None:
    times, sent = [0], 1
    while (wait := bulletin_wait_sec(ANNOUNCEMENT, sent, times[-1])) is not None:
        times.append(times[-1] + wait)
        sent += 1
    assert times[:5] == [0, 120, 360, 3960, 7560] and times[-1] <= 72 * 3600 < times[-1] + 3600 and sent == 3 + 71


def sends(plan: Plan, floor_sec: int = 0) -> int:
    times, sent = [0], 1
    while (wait := bulletin_wait_sec(plan, sent, times[-1], floor_sec)) is not None:
        times.append(times[-1] + wait)
        sent += 1
    assert times[-1] <= plan.lasts
    return sent


@pytest.mark.parametrize(
    ("announcement", "hours", "fm", "slow"),
    [
        (False, 1, 5, 4),
        (False, 2, 8, 6),
        (False, 4, 14, 10),
        (False, 8, 26, 18),
        (False, 12, 38, 26),
        (True, 24, 26, 26),
        (True, 72, 74, 74),
        (True, 168, 170, 170),
    ],
)
def test_each_sent_for_choice_lasts_its_hours_with_its_packets_on_fm_and_on_a_radio_with_a_30_minute_floor(
    announcement: bool, hours: int, fm: int, slow: int
) -> None:
    plan = bulletin_plan(announcement, hours)
    assert plan.lasts == hours * 3600 and plan.every == (3600 if announcement else 1200)
    assert (sends(plan), sends(plan, 1800)) == (fm, slow)
