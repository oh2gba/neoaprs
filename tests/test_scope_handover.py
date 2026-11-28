"""The hand-over of the scope to a page (neoaprs/web/scopefeed.py): kept rows first, then later
rows, none twice and none lost; a second page has its own, a leaving page is sent nothing more, and
a page that lags gets no history.
"""

import sys
import time
from collections.abc import Callable
from typing import Any

import pytest

from neoaprs.mercuryscope import ROW_BINS, ScopeHistory, ScopeRow, history_clock, parse_history, parse_row, scope_clock
from neoaprs.web.scopefeed import ScopeFeed
from neoaprs.web.session import Connection


class Modem:
    def __init__(self) -> None:
        self.scope_history = ScopeHistory()


class Page:
    """A page's socket: what it was sent, and something to do while a frame is written (a row that
    arrives meanwhile)."""

    def __init__(self) -> None:
        self.frames: list[bytes] = []
        self.while_writing: Callable[[bytes], None] | None = None
        self.held = 0

    def send_json(self, text: str) -> None: ...

    def send_binary(self, data: bytes) -> None:
        self.frames.append(data)
        if self.while_writing is not None:
            self.while_writing(data)

    def buffered(self) -> int:
        return self.held


class Out:
    def send(self, conn: Connection, message: dict[str, Any]) -> None: ...
    def send_frame(self, conn: Connection, text: str) -> None: ...

    def send_binary(self, conn: Connection, data: bytes) -> None:
        conn.client.send_binary(data)


def row(n: int) -> ScopeRow:
    return ScopeRow(bytes([n]) * ROW_BINS, -40, False)


def setup() -> tuple[Modem, ScopeFeed]:
    modem = Modem()
    return modem, ScopeFeed(modem)  # type: ignore[arg-type]


def page() -> tuple[Page, Connection]:
    client = Page()
    return client, Connection(client, Out())


def make(modem: Modem, feed: ScopeFeed, n: int) -> None:
    """A row as the modem part makes one: kept, then told."""
    feed.row(modem.scope_history.add(row(n), scope_clock()))


def asleep(monkeypatch: pytest.MonkeyPatch, seconds: float) -> None:
    """From now on the machine has slept `seconds`: Linux's boot clock counts them, its monotonic
    clock stood still (on another system nothing is changed)."""
    if sys.platform != "linux":
        return
    real = time.clock_gettime
    monkeypatch.setattr(
        time, "clock_gettime", lambda clock: real(clock) + (seconds if clock == time.CLOCK_BOOTTIME else 0.0)
    )


def seen(client: Page) -> list[int]:
    """The numbers of the rows the page has, in the order it has them, as the page takes them
    (lib/scopememory.ts): a history that has the newest held goes on from it, any other is all the
    page has; then each row."""
    out: list[int] = []
    for frame in client.frames:
        history = parse_history(frame)
        if history is not None:
            numbers = [r.bins[0] for r, _ in history]
            out = out + numbers[numbers.index(out[-1]) + 1 :] if out and out[-1] in numbers else numbers
        elif (live := parse_row(frame)) is not None:
            out.append(live.bins[0])
    return out


def test_a_page_that_begins_to_look_is_sent_the_rows_kept_oldest_first_and_then_every_row_after_them() -> None:
    modem, feed = setup()
    for n in range(1, 6):
        make(modem, feed, n)
    client, conn = page()
    feed.ask(conn, True)
    history = parse_history(client.frames[0])
    assert history is not None and [r.bins[0] for r, _ in history] == [1, 2, 3, 4, 5]
    assert all(history[i][1] >= history[i + 1][1] >= 0 for i in range(4)), "each with its age, the oldest the oldest"
    for n in range(6, 9):
        make(modem, feed, n)
    assert seen(client) == [1, 2, 3, 4, 5, 6, 7, 8] and len(client.frames) == 4


def test_a_row_that_arrives_while_the_history_is_written_is_sent_once_after_it_and_none_is_lost() -> None:
    modem, feed = setup()
    for n in range(1, 4):
        make(modem, feed, n)
    client, conn = page()
    arriving = iter(range(4, 7))

    def another(frame: bytes) -> None:
        n = next(arriving, None)
        if n is not None:
            # Made while a frame to this page is being written: the history, then each row
            make(modem, feed, n)

    client.while_writing = another
    feed.ask(conn, True)
    client.while_writing = None
    make(modem, feed, 7)
    assert seen(client) == [1, 2, 3, 4, 5, 6, 7], "history, then the rows in order, none twice"
    assert [parse_row(frame) is None for frame in client.frames] == [True, False, False, False, False]


def test_two_pages_each_have_their_history_and_one_that_leaves_in_the_middle_stops_nothing_of_the_other() -> None:
    modem, feed = setup()
    make(modem, feed, 1)
    first, a = page()
    feed.ask(a, True)
    make(modem, feed, 2)
    second, b = page()
    feed.ask(b, True)
    assert seen(first) == [1, 2] and seen(second) == [1, 2] and feed.pages == 2

    def leave(frame: bytes) -> None:
        # The first page leaves while a row is written to it
        feed.forget(a)

    first.while_writing = leave
    make(modem, feed, 3)
    make(modem, feed, 4)
    assert seen(first) == [1, 2, 3] and seen(second) == [1, 2, 3, 4] and feed.pages == 1
    feed.ask(b, False)
    make(modem, feed, 5)
    assert seen(second) == [1, 2, 3, 4] and feed.pages == 0
    feed.ask(b, True)
    assert seen(second) == [1, 2, 3, 4, 5], "asking again is a history again"
    assert [r.bins[0] for r, _ in parse_history(second.frames[-1]) or []] == [3, 4, 5], (
        "of the rows from the one before its newest on: the page holds the rest"
    )


def test_a_page_that_is_behind_is_sent_no_history_and_is_passed_over_and_a_page_that_has_left_is_not_taken() -> None:
    modem, feed = setup()
    make(modem, feed, 1)
    client, conn = page()
    client.held = 10**9
    feed.ask(conn, True)
    make(modem, feed, 2)
    assert client.frames == [] and feed.pages == 1, "behind: nothing, but it looks"
    client.held = 0
    make(modem, feed, 3)
    assert [parse_row(f).bins[0] for f in client.frames if parse_row(f) is not None] == [3], (
        "once it has read, the rows that come, not the ones it was passed over for"
    )
    gone, closed = page()
    closed.closed = True
    feed.ask(closed, True)
    assert feed.pages == 1 and gone.frames == []


def test_the_pages_that_look_are_told_when_the_rows_kept_are_forgotten() -> None:
    modem, feed = setup()
    make(modem, feed, 1)
    client, conn = page()
    feed.ask(conn, True)
    other, _ = page()
    modem.scope_history.clear()
    feed.cleared()
    assert parse_history(client.frames[-1]) == [] and other.frames == [], (
        "an empty history to the page that looks, nothing to one that does not"
    )
    make(modem, feed, 2)
    assert seen(client) == [2]


def test_a_page_that_looks_again_on_its_socket_is_sent_the_rows_from_its_newest_on_while_they_are_kept_and_all_of_them_else() -> (
    None
):
    modem, feed = setup()
    for n in range(1, 4):
        make(modem, feed, n)
    client, conn = page()
    feed.ask(conn, True)
    make(modem, feed, 4)
    feed.ask(conn, False)  # (another tab)
    for n in range(5, 9):
        make(modem, feed, n)
    feed.ask(conn, True)
    assert [r.bins[0] for r, _ in parse_history(client.frames[-1]) or []] == [3, 4, 5, 6, 7, 8], (
        "the one before its newest, its newest, and what it did not see"
    )
    assert seen(client) == list(range(1, 9))
    other, again = page()
    feed.ask(again, True)
    assert [r.bins[0] for r, _ in parse_history(other.frames[-1]) or []] == list(range(1, 9)), (
        "a page on another socket holds nothing of these: all of them"
    )
    feed.ask(conn, False)
    modem.scope_history.clear()
    feed.cleared()
    make(modem, feed, 9)
    feed.ask(conn, True)
    assert [r.bins[0] for r, _ in parse_history(client.frames[-1]) or []] == [9], (
        "the rows were forgotten meanwhile: what is kept now is all of it"
    )


def test_a_page_that_was_behind_when_the_rows_were_forgotten_is_told_before_its_next_row() -> None:
    modem, feed = setup()
    for n in range(1, 4):
        make(modem, feed, n)
    client, conn = page()
    feed.ask(conn, True)
    client.held = 10**9
    modem.scope_history.clear()
    feed.cleared()
    make(modem, feed, 4)
    assert len(client.frames) == 1, "behind: nothing"
    client.held = 0
    make(modem, feed, 5)
    assert parse_history(client.frames[1]) == [] and parse_row(client.frames[2]) == row(5), (
        "first the empty history, then the row"
    )
    assert seen(client) == [5], "it holds what a page that opens now would"
    make(modem, feed, 6)
    assert [parse_history(f) for f in client.frames].count([]) == 1, "told once"


def test_every_history_says_the_daemons_clock() -> None:
    modem, feed = setup()
    make(modem, feed, 1)
    client, conn = page()
    before = time.time() * 1000
    feed.ask(conn, True)
    modem.scope_history.clear()
    feed.cleared()
    assert all(before <= history_clock(f) <= time.time() * 1000 for f in client.frames), (
        "milliseconds since 1970, when it was made"
    )


def test_a_row_of_before_the_machine_slept_is_as_old_as_the_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform != "linux":
        pytest.skip("only Linux's monotonic clock stands still while the machine sleeps")
    modem, feed = setup()
    for n in range(1, 4):
        make(modem, feed, n)
    # The lid closed for an hour, the program and its link up all along
    asleep(monkeypatch, 3600.0)
    client, conn = page()
    feed.ask(conn, True)
    assert parse_history(client.frames[0]) == [], (
        "older than the time kept: none of them is sent as of the last minutes"
    )


def aged(modem: Modem, n: int, age: float) -> None:
    """Row `n` kept as made `age` seconds ago."""
    modem.scope_history.add(row(n), scope_clock() - age)


def test_a_page_is_sent_only_the_rows_of_the_seconds_it_asks_for() -> None:
    modem, feed = setup()
    for n in range(1, 101):
        aged(modem, n, 100 - n + 0.5)
    client, conn = page()
    feed.ask(conn, True, 30)
    history = parse_history(client.frames[0])
    assert history is not None and [r.bins[0] for r, _ in history] == list(range(71, 101)), "the last half minute"
    assert all(age <= 30_000 for _, age in history)
    make(modem, feed, 101)
    assert seen(client) == list(range(71, 102)), "and every row after them"


def test_a_page_that_asks_again_for_more_seconds_is_sent_all_of_them_and_for_as_many_or_fewer_only_what_it_lacks() -> (
    None
):
    modem, feed = setup()
    for n in range(1, 101):
        aged(modem, n, 100 - n + 0.5)
    client, conn = page()
    feed.ask(conn, True, 30)
    feed.ask(conn, True, 60)
    assert [r.bins[0] for r, _ in parse_history(client.frames[-1]) or []] == list(range(41, 101)), (
        "a taller picture: the rows of the whole minute, though it holds the newest"
    )
    make(modem, feed, 101)
    feed.ask(conn, True, 60)
    assert [r.bins[0] for r, _ in parse_history(client.frames[-1]) or []] == [100, 101], "as many: from its newest"
    feed.ask(conn, True, 30)
    assert [r.bins[0] for r, _ in parse_history(client.frames[-1]) or []] == [100, 101], "fewer: the same"
    feed.ask(conn, True, 60)
    assert [r.bins[0] for r, _ in parse_history(client.frames[-1]) or []] == list(range(41, 102)), (
        "after fewer, more again: it holds only the fewer"
    )
