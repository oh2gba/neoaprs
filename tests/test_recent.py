"""The keys seen lately (neoaprs/recent.py): a window, and a table that stays bounded whether keys are asked after or only noted."""
from datetime import UTC, datetime, timedelta

from neoaprs.recent import Recent

START = datetime(2026, 11, 19, tzinfo=UTC)


def test_a_key_is_recent_within_the_window_and_not_after_it() -> None:
    table: Recent[str] = Recent(30)
    table.note("a", START)
    assert table.lately("a", START + timedelta(seconds=29)) and not table.lately("a", START + timedelta(seconds=30))
    assert not table.lately("b", START)


def test_seen_says_whether_the_key_was_noted_and_keeps_the_window_open_with_each_copy() -> None:
    table: Recent[str] = Recent(30)
    assert [table.seen("a", START + timedelta(seconds=n * 20)) for n in range(3)] == [False, True, True]


def test_a_table_that_is_only_noted_stays_within_its_bound() -> None:
    table: Recent[int] = Recent(30, keep_max=10)
    for n in range(500):
        table.note(n, START + timedelta(seconds=n * 31))
    assert len(table) <= 11


def test_what_is_older_than_the_window_is_dropped_once_the_table_is_past_its_bound_and_what_is_not_stays() -> None:
    table: Recent[int] = Recent(30, keep_max=3)
    for n in range(4):
        table.note(n, START)
    table.note(9, START + timedelta(seconds=40))
    assert len(table) == 1 and table.lately(9, START + timedelta(seconds=41))


def test_a_step_of_the_clock_backwards_does_not_make_the_first_copy_a_duplicate() -> None:
    table: Recent[str] = Recent(30)
    assert not table.seen("a", START + timedelta(hours=1))
    assert not table.seen("a", START)
    assert table.seen("a", START + timedelta(seconds=5))
