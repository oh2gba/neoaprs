"""The rows between two radios of a pair (neoaprs/services/passrows.py) through the Digipeater on
stub lines and a held clock: a packet whose first unused hop is the pair's call goes out once on the
other radio, marked used.
"""

import logging
from dataclasses import replace
from datetime import timedelta

import pytest

from neoaprs import ax25
from neoaprs.pairsetting import PairSpec
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import FM_ID, HF_ID, RadioId
from neoaprs.services.passback import PASS_BACK_SEC
from neoaprs.services.passlimits import SLOW_HANDOVER_SEC
from neoaprs.tncwatchdog import PassCount
from tests.test_digipeater import Rig, frame

PAIR = PairSpec(FM_ID, HF_ID, True, 12)


def msg(n: int = 12, to: str = "OH2GAX") -> bytes:
    return f":{to:<9}:Hello {n}{{{n}".encode()


def pair_rig(*pairs: PairSpec, fill_in: bool = False, **changes: object) -> Rig:
    """Radio 1 (FM, Kenwood) and radio 2 (Mercury) with the pairs given (1 and 2 as OH2GBA-12 when
    none), the FM fill-in on or off."""
    rig = Rig(**changes)
    rig.set(digi_enabled=fill_in, pairs=pairs or (PAIR,))
    return rig


def spec(id: RadioId, kind: str, type: str, **settings: str) -> RadioSpec:
    return RadioSpec(id, kind, type, "", True, id, settings=settings)  # type: ignore[arg-type]


def own_rig(specs: tuple[RadioSpec, ...], *pairs: PairSpec, **changes: object) -> Rig:
    """The radios of the test's own make, with the pairs given."""
    rig = Rig(specs, **changes)
    rig.config = replace(rig.config, radios=specs, pairs=pairs)
    return rig


THREE = (spec(1, "fm", "kenwood-tnc2"), spec(2, "hf", "mercury"), spec(3, "lora", "lora-tcp"))


def test_a_request_on_fm_gives_one_frame_on_hf_with_the_call_marked_used_and_none_on_fm() -> None:
    rig = pair_rig()
    rig.hear(frame("OH2RCH-2*,OH2GBA-12,WIDE1-1", info=msg()))
    assert rig.hf.lines() == [f"OH2XYZ>APRS,OH2RCH-2,OH2GBA-12*,WIDE1-1:{msg().decode()}"] and rig.tnc.sent == []
    [sent] = rig.hf.sent
    assert [hop.repeated for hop in sent.path] == [True, True, False], (
        "the hops before keep their marks, the ones after stay unused"
    )
    assert rig.hf.stats.digipeated == 1 and rig.hf.stats.passed == {FM_ID: PassCount(sent=1, sent_at=rig.clock())}


def test_the_same_request_twice_within_thirty_seconds_gives_one_frame_and_after_them_two() -> None:
    rig = pair_rig()
    rig.hear(frame("OH2GBA-12", info=msg()))
    rig.clock.advance(29)
    rig.hear(frame("OH2GBA-12", info=msg()))
    assert len(rig.hf.sent) == 1
    rig.clock.advance(31)
    rig.hear(frame("OH2GBA-12", info=msg()))
    assert len(rig.hf.sent) == 2


def test_a_copy_without_the_request_does_not_hold_back_a_later_copy_that_asks() -> None:
    rig = pair_rig()
    rig.hear(frame("WIDE1-1,OH2GBA-12", info=msg()))
    rig.hear(frame("OH2RCH*,OH2GBA-12", info=msg()))
    assert rig.hf.lines() == [f"OH2XYZ>APRS,OH2RCH,OH2GBA-12*:{msg().decode()}"]


def test_with_the_fill_in_on_a_request_after_wide1_1_gives_one_frame_on_each_radio() -> None:
    rig = pair_rig(fill_in=True)
    rig.hear(frame("WIDE1-1,OH2GBA-12", info=msg()))
    assert rig.tnc.lines() == [f"OH2XYZ>APRS,OH2GBA*,OH2GBA-12:{msg().decode()}"]
    assert rig.hf.lines() == [f"OH2XYZ>APRS,OH2GBA,OH2GBA-12*:{msg().decode()}"]


@pytest.mark.parametrize(
    "path", ["WIDE1-1", "WIDE2-2", "WIDE1-1,WIDE2-1", "OH2GBA", "OH2GBA-11", "WIDE2-2,OH2GBA-12", "OH2GBA-12*", ""]
)
def test_a_path_that_does_not_name_the_pair_call_next_crosses_nowhere(path: str) -> None:
    rig = pair_rig(fill_in=True)
    rig.hear(frame(path, info=msg()))
    assert rig.hf.sent == [] and rig.hf.stats.passed == {}


def test_a_packet_already_heard_on_hf_is_not_passed_onto_it() -> None:
    rig = pair_rig()
    rig.hear(frame("", info=msg()), radio_id=HF_ID)
    rig.hear(frame("OH2GBA-12", info=msg()))
    assert rig.hf.sent == [] and rig.hf.stats.passed == {}, "a duplicate counts nothing"


def test_a_request_heard_on_a_radio_outside_the_pair_is_none() -> None:
    rig = own_rig(THREE, PAIR)
    rig.hear(frame("OH2GBA-12", info=msg()), radio_id=3)
    assert rig.line(1).sent == rig.line(2).sent == rig.line(3).sent == []


def test_three_radios_with_two_pairs_send_each_request_on_its_own_target_only() -> None:
    rig = own_rig(THREE, PAIR, PairSpec(1, 3, True, 11))
    rig.hear(frame("OH2GBA-12", info=msg(1)))
    rig.hear(frame("OH2GBA-11", info=msg(2)))
    assert (
        [f.info for f in rig.line(2).sent] == [msg(1)]
        and [f.info for f in rig.line(3).sent] == [msg(2)]
        and rig.line(1).sent == []
    )


def test_a_frame_too_long_for_hf_is_not_sent_and_is_counted_too_long() -> None:
    rig = pair_rig()
    rig.hear(frame("OH2GBA-12", info=b">" + b"x" * 100))  # (124 bytes: Mercury carries 123)
    assert rig.hf.sent == [] and rig.hf.stats.passed == {FM_ID: PassCount(too_long=1)} and rig.hf.stats.digipeated == 0


def test_a_dummy_radio_and_a_real_one_pass_nothing_even_with_a_stored_pair() -> None:
    rig = own_rig((spec(1, "fm", "kenwood-tnc2"), spec(2, "hf", "dummy-hf")), PAIR)
    rig.hear(frame("OH2GBA-12", info=msg()))
    rig.hear(frame("OH2GBA-12", info=msg(13)), radio_id=2, dummy=True)
    assert rig.line(1).sent == rig.line(2).sent == []


def test_two_dummy_radios_pass_a_dummy_packet() -> None:
    rig = own_rig((spec(1, "fm", "dummy"), spec(2, "hf", "dummy-hf")), PAIR)
    rig.hear(frame("OH2GBA-12", info=msg()), dummy=True)
    assert len(rig.line(2).sent) == 1


def test_receive_only_passes_nothing_and_counts_nothing() -> None:
    rig = pair_rig(station_transmit=False)
    rig.hear(frame("OH2GBA-12", info=msg()))
    rig.hear(frame("OH2GBA-12", info=msg(13)), radio_id=HF_ID)
    assert rig.tnc.sent == rig.hf.sent == [] and rig.hf.stats.passed == rig.stats.passed == {}


def test_heard_on_two_radios_at_once_the_request_goes_out_once() -> None:
    rig = own_rig(THREE, PAIR)
    rig.hear(frame("OH2GBA-12", info=msg()))
    rig.clock.advance(0.5)
    rig.hear(frame("OH2GBA-12", info=msg()), radio_id=3)
    assert len(rig.line(2).sent) == 1, "only the pair's other radio"
    rig = own_rig(THREE, PairSpec(1, 3, True, 11))
    rig.hear(frame("OH2GBA-11", info=msg()))
    rig.clock.advance(0.5)
    rig.hear(frame("OH2GBA-11", info=msg()), radio_id=3)
    assert len(rig.line(3).sent) == 1 and rig.line(1).sent == [], "FM heard it itself"


def test_our_own_packet_and_our_passed_frame_heard_back_are_not_passed() -> None:
    rig = pair_rig()
    rig.hear(frame("OH2GBA-12", source="OH2GBA", info=b">our status"))
    rig.hear(frame("OH2GBA-12", source="OH2GBA-12", info=b">a pair call"))
    rig.hear(frame("OH2GBA-12*", info=msg()), radio_id=HF_ID)  # (one of ours heard back)
    rig.hear(frame("OH2GBA-12*,OH2GBA-12", info=msg(13)), radio_id=HF_ID)  # (and one that would name it again)
    assert rig.tnc.sent == rig.hf.sent == []


def test_a_pair_whose_radio_is_off_passes_nothing_and_keeps_its_setting() -> None:
    rig = pair_rig()
    radios = rig.config.radios
    rig.set(radios=tuple(replace(r, enabled=r.id != FM_ID) for r in radios))
    rig.hear(frame("OH2GBA-12", info=msg()))
    assert rig.hf.sent == [] and rig.config.pairs == (PAIR,)
    rig.set(radios=radios)
    rig.hear(frame("OH2GBA-12", info=msg()))
    assert len(rig.hf.sent) == 1


def test_a_packet_with_no_radio_is_no_request() -> None:
    rig = pair_rig()
    rig.hear(frame("OH2GBA-12", info=msg()), radio_id=None)
    assert rig.tnc.sent == rig.hf.sent == []


def test_a_station_call_with_the_pairs_ssid_passes_nothing() -> None:
    rig = pair_rig(station_call="OH2GBA-12")
    rig.hear(frame("OH2GBA-12", info=msg()))
    assert rig.hf.sent == []


def test_a_request_on_hf_gives_one_frame_on_fm() -> None:
    rig = pair_rig()
    rig.hear(frame("OH2GBA-12", source="OH3ABC-9", info=msg()), radio_id=HF_ID)
    assert rig.tnc.lines() == [f"OH3ABC-9>APRS,OH2GBA-12*:{msg().decode()}"] and rig.hf.sent == []
    assert rig.stats.passed == {HF_ID: PassCount(sent=1, sent_at=rig.clock())} and rig.stats.digipeated == 1


def test_two_pair_calls_in_turn_cross_twice_and_the_chain_ends() -> None:
    fast = (spec(1, "fm", "kenwood-tnc2"), spec(2, "fm", "kiss"), spec(3, "fm", "kiss-tcp"))
    rig = own_rig(fast, PairSpec(1, 2, True, 12), PairSpec(2, 3, True, 11), PairSpec(1, 3, True, 10))
    rig.hear(frame("OH2GBA-12,OH2GBA-11,WIDE2-1", info=msg()))
    assert rig.line(2).lines() == [f"OH2XYZ>APRS,OH2GBA-12*,OH2GBA-11,WIDE2-1:{msg().decode()}"]
    assert rig.line(3).lines() == [f"OH2XYZ>APRS,OH2GBA-12,OH2GBA-11*,WIDE2-1:{msg().decode()}"]
    assert rig.line(1).sent == []
    assert rig.line(3).stats.passed == {2: PassCount(sent=1, sent_at=rig.clock())}, "counted by the radio it came from"


def band(*ends: tuple[Rig, RadioId]) -> None:
    """The radios `ends` on one channel: a frame one sends is heard by each of the others."""
    for rig, id in ends:
        line = rig.line(id)
        took = line.send_frame

        def send(f: ax25.Frame, raw: bytes | None = None, rig: Rig = rig, took: object = took) -> bool:
            done = bool(took(f, raw))  # type: ignore[operator]
            for other, other_id in ends:
                if other is not rig:
                    other.hear(f, "in", other_id)
            return done

        line.send_frame = send  # type: ignore[method-assign]


@pytest.mark.parametrize("both_hear_it", [True, False])
def test_two_gateways_that_name_each_other_in_turn_send_one_frame_each_at_most_then_nothing(both_hear_it: bool) -> None:
    g1, g2 = pair_rig(), pair_rig(station_call="OH1XYZ")
    g2.clock = g1.clock
    band((g1, FM_ID), (g2, FM_ID))
    band((g1, HF_ID), (g2, HF_ID))
    heard = frame(",".join(["OH2GBA-12", "OH1XYZ-12"] * 4), source="OH3ABC", info=msg())
    if both_hear_it:
        g2.hear(heard)
    g1.hear(heard)
    sent = [len(g.line(id).sent) for g in (g1, g2) for id in (FM_ID, HF_ID)]
    assert sent == ([0, 1, 0, 0] if both_hear_it else [0, 1, 1, 0]), (
        "G1 once onto HF; G2 onto its FM only when it had not heard the original there"
    )
    g1.clock.advance(60)
    assert [len(g.line(id).sent) for g in (g1, g2) for id in (FM_ID, HF_ID)] == sent


def test_the_counts_are_the_target_radios_by_direction_and_every_change_is_told() -> None:
    rig = pair_rig()
    told: list[RadioId] = []
    rig.digi.counted.connect(told.append)
    rig.hear(frame("OH2GBA-12", info=msg(1)))
    rig.hear(frame("OH2GBA-12", source="OH3ABC", info=msg(2)), radio_id=HF_ID)
    rig.clock.advance(1)
    rig.hear(frame("OH2GBA-12", source="OH3ABD", info=msg(3)), radio_id=HF_ID)
    rig.hear(frame("OH2GBA-12", info=b">" + b"x" * 100))
    assert rig.hf.stats.passed == {FM_ID: PassCount(sent=1, sent_at=rig.clock() - timedelta(seconds=1), too_long=1)}
    assert rig.stats.passed == {HF_ID: PassCount(sent=2, sent_at=rig.clock())}
    assert (rig.stats.digipeated, rig.hf.stats.digipeated) == (2, 1)
    assert told == [HF_ID, FM_ID, FM_ID, HF_ID], (
        "a frame too long changes no counter of the line and is told all the same"
    )


def test_a_passed_frame_is_told_at_info_and_a_held_one_at_info_once_and_never_as_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.digipeater")
    rig = pair_rig()
    rig.hear(frame("OH2GBA-12", info=msg()))
    for n in range(2):
        rig.hear(frame("OH2GBA-12", info=b">" + b"x" * (100 + n)))
    infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert infos == [
        "passed OH2XYZ>APRS from Packet to Mercury: the path OH2GBA-12 is sent as OH2GBA-12*",
        "Mercury: a packet of OH2XYZ from Packet is not passed: too long: 124 bytes, the radio carries 123",
    ]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


async def test_the_digipeaters_timer_starts_and_stops_and_a_frame_that_waits_is_dropped() -> None:
    rig = pair_rig()
    await rig.digi.start()
    assert len(rig.digi.tasks) == 1
    rig.hear(frame("OH2GBA-12", info=msg(1)))
    rig.hear(frame("OH2GBA-12", info=msg(2), source="OH3ABC"))  # (waits out the gap after the first)
    await rig.digi.stop()
    assert len(rig.digi.tasks) == 0
    rig.clock.advance(SLOW_HANDOVER_SEC)
    rig.digi.passer.tick()
    assert len(rig.hf.sent) == 1 and rig.hf.stats.passed[FM_ID].held == 0


# ---- the ack of a message passed goes back once

ACK = b":OH3ABC-9 :ack12"


def passed_from_hf(rig: Rig) -> None:
    """OH3ABC-9 on HF messages a station on FM through the pair."""
    rig.hear(frame("OH2GBA-12", source="OH3ABC-9", info=b":OH2GAX   :Hi{12"), radio_id=HF_ID)
    assert len(rig.tnc.sent) == 1
    rig.clock.advance(5)


@pytest.mark.parametrize("fill_in", [False, True])
def test_a_kenwoods_ack_heard_on_fm_for_a_message_passed_from_hf_goes_back_on_hf_once(fill_in: bool) -> None:
    rig = pair_rig(fill_in=fill_in)
    passed_from_hf(rig)
    rig.hear(frame("WIDE1-1,WIDE2-1", source="OH2GAX", info=ACK))
    assert rig.hf.lines() == [f"OH2GAX>APRS,OH2GBA-12*:{ACK.decode()}"]
    assert len(rig.tnc.sent) == (2 if fill_in else 1), (
        "the fill-in's own copy on FM, which does not go back with its hop"
    )
    rig.clock.advance(31)
    rig.hear(frame("WIDE1-1,WIDE2-1", source="OH2GAX", info=ACK))
    assert len(rig.hf.sent) == 1, "a second copy, after the duplicate window, answers nothing"


def test_a_frame_held_by_a_limit_is_told_as_counted_with_the_target() -> None:
    rig = pair_rig()
    told: list[RadioId] = []
    rig.digi.counted.connect(told.append)
    for n in range(3):
        rig.hear(frame("OH2GBA-12", info=msg(n)))
        rig.clock.advance(SLOW_HANDOVER_SEC)
    assert len(rig.hf.sent) == 2 and rig.hf.stats.passed[FM_ID].held == 1
    assert told == [HF_ID, HF_ID, HF_ID], "the third is held by its station's share and told all the same"


def test_a_pair_that_is_set_after_the_packet_passes_nothing_before_and_the_next_one_after() -> None:
    rig = own_rig(THREE, PAIR)
    rig.hear(frame("OH2GBA-11", info=msg(1)))
    assert rig.line(3).sent == [] and rig.line(3).stats.passed == {}, "radio 3 has no pair yet"
    rig.config = replace(rig.config, pairs=(PAIR, PairSpec(1, 3, True, 11)))
    rig.clock.advance(31)
    rig.hear(frame("OH2GBA-11", info=msg(1)))
    assert len(rig.line(3).sent) == 1


def test_an_hf_radio_changed_to_receive_only_while_running_gets_nothing_more() -> None:
    rig = pair_rig()
    rig.hear(frame("OH2GBA-12", info=msg(1)))
    assert len(rig.hf.sent) == 1
    rig.set(radios=tuple(replace(r, type="tnc-text") if r.id == HF_ID else r for r in rig.config.radios))
    rig.clock.advance(31)
    rig.hear(frame("OH2GBA-12", info=msg(1)))
    assert len(rig.hf.sent) == 1


def test_our_frame_heard_back_on_a_third_radio_passes_nothing_while_its_next_hop_is_no_pair_call() -> None:
    rig = own_rig(THREE, PAIR, PairSpec(1, 3, True, 11))
    rig.hear(frame("OH2GBA-12*", info=msg()), radio_id=3)
    rig.hear(frame("OH2GBA-12*,WIDE1-1", source="OH2XYZ", info=msg(2)), radio_id=3)
    assert [rig.line(i).sent for i in (1, 2, 3)] == [[], [], []]


def test_an_ack_heard_with_no_path_goes_back_with_the_pair_call_as_the_only_hop() -> None:
    rig = pair_rig()
    passed_from_hf(rig)
    rig.hear(frame("", source="OH2GAX", info=ACK))
    assert rig.hf.lines() == [f"OH2GAX>APRS,OH2GBA-12*:{ACK.decode()}"]


def test_an_ack_for_another_id_or_after_ten_minutes_goes_nowhere() -> None:
    rig = pair_rig()
    passed_from_hf(rig)
    rig.hear(frame("WIDE1-1", source="OH2GAX", info=b":OH3ABC-9 :ack13"))
    rig.clock.advance(PASS_BACK_SEC)
    rig.hear(frame("WIDE1-1", source="OH2GAX", info=ACK))
    assert rig.hf.sent == []


def test_the_ack_back_keeps_the_used_hops_and_drops_the_unused_ones() -> None:
    rig = pair_rig()
    passed_from_hf(rig)
    rig.hear(frame("OH2RCH-2*,WIDE2-1", source="OH2GAX", info=ACK))
    assert rig.hf.lines() == [f"OH2GAX>APRS,OH2RCH-2,OH2GBA-12*:{ACK.decode()}"]


def test_an_ack_back_falls_under_the_budget_of_hf() -> None:
    rig = pair_rig()
    passed_from_hf(rig)
    for n in range(4):
        rig.hear(frame("OH2GBA-12", source=f"OH3AB{n}", info=msg(n)))
        rig.clock.advance(SLOW_HANDOVER_SEC)
    rig.hear(frame("WIDE1-1", source="OH2GAX", info=ACK))
    assert len(rig.hf.sent) == 4 and rig.hf.stats.passed[FM_ID].held == 1


def test_an_ack_whose_path_would_have_more_than_eight_hops_back_sends_nothing_and_raises_nothing_and_a_later_copy_goes_back() -> (
    None
):
    rig = pair_rig()
    passed_from_hf(rig)
    rig.hear(frame(",".join(f"OH2RC{n}*" for n in range(8)), source="OH2GAX", info=ACK))
    assert rig.hf.sent == [] and rig.hf.stats.passed == {}
    rig.clock.advance(31)
    rig.hear(frame("WIDE1-1", source="OH2GAX", info=ACK))
    assert rig.hf.lines() == [f"OH2GAX>APRS,OH2GBA-12*:{ACK.decode()}"], (
        "the copy refused leaves the message for the next copy of the ack"
    )


def test_an_ack_that_names_the_pair_call_goes_once_by_its_path() -> None:
    rig = pair_rig()
    passed_from_hf(rig)
    rig.hear(frame("OH2GBA-12", source="OH2GAX", info=ACK))
    rig.clock.advance(31)
    rig.hear(frame("WIDE1-1", source="OH2GAX", info=ACK))
    assert rig.hf.lines() == [f"OH2GAX>APRS,OH2GBA-12*:{ACK.decode()}"], (
        "the request passed it, and its entry is used up"
    )
