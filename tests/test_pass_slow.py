"""What a pair passes onto a slow radio (HF, LoRa) through the Digipeater on stub lines and a held
clock (neoaprs/services/passrows.py, passlimits.py): at most four frames in five minutes, one frame
waiting while the radio is keyed, busy or just handed a frame. The rows themselves are
tests/test_pass_rows.py's.
"""
import logging
from dataclasses import replace

import pytest

from neoaprs.coded import Reason
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.recent import KEEP_MAX
from neoaprs.services.passlimits import BURST_MAX, SLOW_HANDOVER_SEC, SLOW_PASS_MAX
from neoaprs.source import Source
from tests.test_digipeater import frame
from tests.test_pass_rows import msg, pair_rig

KEYED = Reason("the radio is transmitting", "radio.transmitting")


def test_five_messages_from_five_stations_in_a_minute_give_four_frames_and_the_sixth_goes_after_five_minutes() -> None:
    rig = pair_rig()
    for n in range(5):
        rig.hear(frame("OH2GBA-12", source=f"OH3AB{n}", info=msg(n)))
        rig.clock.advance(12)
    assert len(rig.hf.sent) == SLOW_PASS_MAX and rig.hf.stats.passed[FM_ID].held == 1
    rig.clock.advance(300 - 60)
    rig.hear(frame("OH2GBA-12", source="OH3AB5", info=msg(5)))
    assert len(rig.hf.sent) == 5


def test_three_messages_of_one_station_in_a_minute_give_two() -> None:
    rig = pair_rig()
    for n in range(3):
        rig.hear(frame("OH2GBA-12", info=msg(n)))
        rig.clock.advance(20)
    assert len(rig.hf.sent) == 2 and rig.hf.stats.passed[FM_ID].held == 1


@pytest.mark.parametrize(("minutes", "sent"), [(10, 1), (31, 2)])
def test_positions_of_one_station_pass_once_in_half_an_hour(minutes: int, sent: int) -> None:
    rig = pair_rig()
    rig.hear(frame("OH2GBA-12", info=b"!6010.20N/02456.40E-one"))
    rig.clock.advance(minutes * 60)
    rig.hear(frame("OH2GBA-12", info=b"!6010.20N/02456.40E-two"))
    assert len(rig.hf.sent) == sent and rig.hf.stats.passed[FM_ID].held == 2 - sent


def test_a_telemetry_definition_is_held_by_the_floor_and_a_message_is_not() -> None:
    rig = pair_rig()
    rig.hear(frame("OH2GBA-12", info=b">status"))
    rig.clock.advance(60)
    rig.hear(frame("OH2GBA-12", info=b":OH2XYZ   :PARM.Volts,Temp"))
    rig.clock.advance(60)
    rig.hear(frame("OH2GBA-12", info=msg()))
    assert [f.info for f in rig.hf.sent] == [b">status", msg()] and rig.hf.stats.passed[FM_ID].held == 1


def test_a_directed_query_is_not_passed_onto_hf_and_counts_nothing() -> None:
    rig = pair_rig()
    rig.hear(frame("OH2GBA-12", info=b":OH2GAX   :?APRSP"))
    assert rig.hf.sent == [] and rig.hf.stats.passed == {}


def test_a_message_offered_while_hf_is_keyed_goes_from_the_tick_when_it_is_free_within_thirty_seconds() -> None:
    rig = pair_rig()
    rig.hf.held = KEYED
    rig.hear(frame("OH2GBA-12", info=msg()))
    rig.clock.advance(5)
    rig.digi.passer.tick()
    assert rig.hf.sent == []
    rig.hf.held = ""
    rig.clock.advance(5)
    rig.digi.passer.tick()
    assert len(rig.hf.sent) == 1 and rig.hf.stats.passed[FM_ID].held == 0


def test_a_message_that_waits_longer_than_thirty_seconds_is_held() -> None:
    rig = pair_rig()
    rig.hf.held = Reason("the channel is busy", "radio.channel_busy")
    rig.hear(frame("OH2GBA-12", info=msg()))
    rig.clock.advance(31)
    rig.hf.held = ""
    rig.digi.passer.tick()
    assert rig.hf.sent == [] and rig.hf.stats.passed[FM_ID].held == 1


def test_while_one_waits_a_second_is_held_and_a_copy_of_the_waiting_one_counts_nothing() -> None:
    rig = pair_rig()
    rig.hf.held = KEYED
    rig.hear(frame("OH2GBA-12", info=msg(1)))
    rig.hear(frame("OH2GBA-12", source="OH3ABC", info=msg(2)))
    # The waiting one through another digipeater
    rig.hear(frame("OH2RCH*,OH2GBA-12", info=msg(1)))
    assert rig.hf.stats.passed[FM_ID].held == 1
    rig.hf.held = ""
    rig.digi.passer.tick()
    assert [f.info for f in rig.hf.sent] == [msg(1)]


def test_a_copy_of_a_frame_held_as_busy_is_dropped_within_the_duplicate_window_even_when_the_radio_is_free() -> None:
    rig = pair_rig()
    rig.hf.held = KEYED
    rig.hear(frame("OH2GBA-12", info=msg(1)))
    rig.hear(frame("OH2GBA-12", source="OH3ABC", info=msg(2)))               # held: another frame waits
    rig.hf.held = ""
    rig.digi.passer.tick()
    rig.clock.advance(10)
    # Its copy through a digipeater: the sender's own retry is what comes again
    rig.hear(frame("OH2RCH*,OH2GBA-12", source="OH3ABC", info=msg(2)))
    assert [f.info for f in rig.hf.sent] == [msg(1)] and rig.hf.stats.passed[FM_ID].held == 1


@pytest.mark.parametrize("state", [Source.State.SILENT, Source.State.WAITING])
def test_onto_a_radio_not_connected_nothing_is_sent_or_counted_and_nothing_waits(state: Source.State) -> None:
    rig = pair_rig()
    rig.hf.state = state
    rig.hear(frame("OH2GBA-12", info=msg()))
    rig.hf.state = Source.State.CONNECTED
    rig.digi.passer.tick()
    assert rig.hf.sent == [] and rig.hf.stats.passed == {}


def test_two_messages_half_a_second_apart_go_one_now_and_one_after_the_gap() -> None:
    rig = pair_rig()
    rig.hear(frame("OH2GBA-12", info=msg(1)))
    rig.clock.advance(0.5)
    rig.hear(frame("OH2GBA-12", source="OH3ABC", info=msg(2)))
    rig.digi.passer.tick()
    assert len(rig.hf.sent) == 1
    rig.clock.advance(SLOW_HANDOVER_SEC - 0.5)
    rig.digi.passer.tick()
    assert [f.info for f in rig.hf.sent] == [msg(1), msg(2)]


def test_a_passed_frame_right_after_one_of_ours_on_hf_waits_the_gap() -> None:
    rig = pair_rig()
    rig.hear(frame("", source="OH2GBA", info=b">our status"), "out", radio_id=HF_ID)
    rig.clock.advance(1)
    rig.hear(frame("OH2GBA-12", info=msg()))
    assert rig.hf.sent == []
    rig.clock.advance(SLOW_HANDOVER_SEC)
    rig.digi.passer.tick()
    assert len(rig.hf.sent) == 1


@pytest.mark.parametrize("change", ["pair off", "radio off"])
def test_a_waiting_frame_whose_pair_no_longer_passes_is_dropped_at_the_tick_and_counts_nothing(change: str) -> None:
    rig = pair_rig()
    rig.hf.held = KEYED
    rig.hear(frame("OH2GBA-12", info=msg()))
    if change == "pair off":
        rig.set(pairs=(replace(rig.config.pairs[0], enabled=False),))
    else:
        rig.set(radios=tuple(replace(r, enabled=r.id != HF_ID) for r in rig.config.radios))
    rig.hf.held = ""
    rig.digi.passer.tick()
    rig.set(pairs=(replace(rig.config.pairs[0], enabled=True),), radios=tuple(replace(r, enabled=True) for r in rig.config.radios))
    rig.digi.passer.tick()
    assert rig.hf.sent == [] and rig.hf.stats.passed == {}


def test_receive_only_ticked_during_the_wait_drops_the_frame_with_one_warning(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    rig = pair_rig()
    rig.hf.held = KEYED
    rig.hear(frame("OH2GBA-12", info=msg()))
    rig.set(station_transmit=False)
    rig.hf.held = ""
    rig.digi.passer.tick()
    rig.digi.passer.tick()
    assert rig.hf.sent == [] and rig.hf.stats.passed == {}
    assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) == 1, "the interlock's one line"


def test_fm_as_the_target_keeps_four_in_ten_seconds_shared_with_the_fill_in() -> None:
    rig = pair_rig(fill_in=True)
    for n in range(BURST_MAX - 1):
        rig.hear(frame("WIDE1-1", info=f">{n}".encode()))
    rig.hear(frame("OH2GBA-12", source="OH3ABC", info=msg(1)), radio_id=HF_ID)
    rig.hear(frame("OH2GBA-12", source="OH3ABD", info=msg(2)), radio_id=HF_ID)
    assert len(rig.tnc.sent) == BURST_MAX and rig.stats.passed[HF_ID].held == 1 and rig.stats.digipeat_held == 0


def test_a_copy_of_a_packet_the_floor_held_counts_nothing_within_the_duplicate_window_and_counts_again_after_it() -> None:
    rig = pair_rig()
    beacon = b"!6010.20N/02456.40E-trk"
    rig.hear(frame("OH2GBA-12", info=beacon))
    rig.clock.advance(60)
    rig.hear(frame("OH2GBA-12", info=b"!6010.20N/02456.40E-next"))
    assert rig.hf.stats.passed[FM_ID].held == 1
    rig.clock.advance(1)
    rig.hear(frame("OH2RCH*,OH2GBA-12", info=b"!6010.20N/02456.40E-next"))      # (the same beacon through a digipeater)
    assert rig.hf.stats.passed[FM_ID].held == 1 and len(rig.hf.sent) == 1
    rig.clock.advance(31)
    rig.hear(frame("OH2RCH*,OH2GBA-12", info=b"!6010.20N/02456.40E-next"))
    assert rig.hf.stats.passed[FM_ID].held == 2


def test_a_beacon_heard_direct_and_through_a_digipeater_every_minute_is_held_once_a_minute() -> None:
    rig = pair_rig()
    for n in range(10):
        info = f"!6010.20N/02456.40E-{n}".encode()
        rig.hear(frame("OH2GBA-12,WIDE2-1", info=info))
        rig.clock.advance(1)
        rig.hear(frame("OH2RCH*,OH2GBA-12", info=info))
        rig.clock.advance(59)
    assert len(rig.hf.sent) == 1 and rig.hf.stats.passed[FM_ID].held == 9


def test_a_copy_of_a_frame_too_long_for_hf_counts_nothing_within_the_duplicate_window() -> None:
    rig = pair_rig()
    rig.hear(frame("OH2GBA-12", info=b">" + b"x" * 100))
    rig.clock.advance(1)
    rig.hear(frame("OH2RCH*,OH2GBA-12", info=b">" + b"x" * 100))
    assert rig.hf.stats.passed[FM_ID].too_long == 1


def test_a_copy_of_a_packet_the_burst_held_onto_fm_counts_nothing_within_the_duplicate_window() -> None:
    rig = pair_rig(fill_in=True)
    for n in range(BURST_MAX):
        rig.hear(frame("OH2GBA-12", source=f"OH3AB{n}", info=msg(n)), radio_id=HF_ID)
    rig.hear(frame("OH2GBA-12", source="OH3ABX", info=msg(9)), radio_id=HF_ID)
    rig.clock.advance(1)
    rig.hear(frame("OH2RCH*,OH2GBA-12", source="OH3ABX", info=msg(9)), radio_id=HF_ID)
    assert rig.stats.passed[HF_ID].held == 1


def test_the_table_of_a_radio_nothing_is_passed_onto_stays_bounded() -> None:
    rig = pair_rig()
    for n in range(KEEP_MAX + 500):
        rig.clock.advance(31)
        rig.hear(frame("WIDE1-1", info=f">{n}".encode()))
    assert len(rig.digi.passer.table(FM_ID)) <= KEEP_MAX + 1
