"""What the page is told of the TNC's log (`TncState.lines`) and of a search (`searching`): every line has the time it was written, in full, and its text without the time of day that `Tnc.lines` shows in front of
it; the ports of a search are a list and not a sentence."""
from datetime import timedelta

from neoaprs.clock import iso
from neoaprs.tnc import LINE_TIME_WIDTH, Tnc
from tests.support.clock import FixedClock


def test_every_line_has_the_time_it_was_written_and_its_text_without_the_time_of_day() -> None:
    clock = FixedClock()
    tnc = Tnc(clock=clock)
    start = clock()
    tnc._note("opened /dev/brainbox_1")
    clock.advance(86400 + 5)
    tnc._saw("OH2XYZ>APRS:>hello  ->  status hello")
    assert list(tnc.lines) == ["12:00:00  NeoAPRS: opened /dev/brainbox_1", "12:00:05  OH2XYZ>APRS:>hello  ->  status hello"]
    assert LINE_TIME_WIDTH == len("12:00:00  ")
    assert tnc.recent_lines(10) == [(start, "NeoAPRS: opened /dev/brainbox_1"), (start + timedelta(days=1, seconds=5), "OH2XYZ>APRS:>hello  ->  status hello")]
    assert [iso(at) for at, _ in tnc.recent_lines(1)] == ["2026-10-22T12:00:05Z"], "the day is the line's own, not a guess from the time of day"


def test_the_lines_asked_for_are_the_latest_ones_and_the_times_stay_with_their_lines() -> None:
    clock = FixedClock()
    tnc = Tnc(clock=clock)
    for n in range(Tnc.MAX_LINES + 20):
        tnc._note(f"line {n}")
        clock.advance(1)
    assert len(tnc.line_times) == len(tnc.lines) == Tnc.MAX_LINES
    [(at, text)] = tnc.recent_lines(1)
    assert text == f"NeoAPRS: line {Tnc.MAX_LINES + 19}" and at == FixedClock()() + timedelta(seconds=Tnc.MAX_LINES + 19)


def test_a_tnc_that_is_not_searching_lists_no_ports() -> None:
    tnc = Tnc()
    assert tnc.searching == [] and "for the radio" not in tnc.describe()
    tnc._search.listening = ["/dev/ttyUSB0", "/dev/ttyUSB1"]
    assert tnc.searching == ["/dev/ttyUSB0", "/dev/ttyUSB1"] and tnc.describe() == "listening on /dev/ttyUSB0, /dev/ttyUSB1 for the radio"
