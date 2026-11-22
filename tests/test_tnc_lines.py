"""What the page is told of the TNC's log (`lines` of a radio's row in the `radios` topic) and of a
search (`searching`): every line has its full time and text without the time of day, ports are a
list; and the radio id every packet carries.
"""
import asyncio
from datetime import timedelta

import pytest

from neoaprs import ax25, dummyline
from neoaprs.clock import iso
from neoaprs.dummyline import DUMMY_PATH
from neoaprs.packet import Packet
from neoaprs.tnc import Tnc
from neoaprs.tnclines import LINE_TIME_WIDTH
from neoaprs.tncprofile import DUMMY, DUMMY_HF, Profile
from tests.support.clock import FixedClock
from tests.support.env import until


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


# ---- the radio of the packets the Tnc makes

async def played(profile: Profile, radio_id: int | None) -> tuple[Tnc, list[Packet]]:
    """A Tnc of the Dummy profile as the line of the radio `radio_id` (None: no driver set it), what
    it heard in a made-up quarter of an hour and the one frame it sent."""
    clock = FixedClock()
    tnc = Tnc(profile=profile, port=DUMMY_PATH, clock=clock)
    if radio_id is not None:
        # As its driver sets it: neoaprs/tncdriver.py, mercurydriver.py
        tnc.radio_id = radio_id
    made: list[Packet] = []
    tnc.packet.connect(made.append)
    await tnc.start()
    await until(lambda: tnc.confirmed)
    assert tnc.send_frame(ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("OH2GBA"), (), info=b">on the air"))
    for _ in range(30):
        clock.advance(30)
        await asyncio.sleep(0.02)
    await tnc.stop()
    return tnc, made


async def test_every_packet_the_tnc_makes_heard_or_sent_carries_the_id_of_its_radio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dummyline, "TICK_SEC", 0.01)
    for profile, radio_id in ((DUMMY, 1), (DUMMY, 4), (DUMMY_HF, 2), (DUMMY_HF, 5)):
        tnc, made = await played(profile, radio_id)
        assert {p.direction for p in made} == {"in", "out"} and len(made) > 3, profile.key
        assert all(p.radio_id == radio_id for p in made), f"{profile.key} as radio {radio_id}: {[p.radio_id for p in made]}"
        assert any("on the air" in line for line in tnc.lines) and any("  ->  " in line for line in tnc.lines), "the lines of its log are what they were"


async def test_a_tnc_no_driver_has_set_stamps_radio_1_and_the_hf_one_radio_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dummyline, "TICK_SEC", 0.01)
    for profile, radio_id in ((DUMMY, 1), (DUMMY_HF, 2)):
        tnc, made = await played(profile, None)
        assert tnc.radio_id == radio_id and made and all(p.radio_id == radio_id for p in made)
