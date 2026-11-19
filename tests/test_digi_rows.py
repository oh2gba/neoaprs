"""The digipeater as a table (neoaprs/services/digipeater.py `DigiRow`, `digi_rows`, plan rule 3.4): one row "heard on A, sent on A" for each enabled radio whose type may repeat and whose own digipeater the
operator turned on (radio 1's is `digi/enabled`), none on HF, none for a radio that is off, none from one radio to another; the rows follow the settings in force, and a packet goes through the rows of the
radio it came on. The duplicate check, the burst and the counts per radio are tests/test_digipeater.py's. Then the rows between two radios of a pair (neoaprs/services/passrows.py `rows_in_force`): both directions
of each pair that passes, none for a pair that is off, a radio that is off or only receives, a Dummy radio facing a real one, an SSID that is the station's or another pair's, or a station call that does not
parse."""
from dataclasses import replace

import pytest

from neoaprs import ax25
from neoaprs.config import Config
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.radiotypes.common import FM_ALLOWED
from neoaprs.pairsetting import PairSpec
from neoaprs.services.digipeater import DigiRow, Digipeater, digi_rows, repeats
from neoaprs.services.passrows import PairRow, rows_in_force
from neoaprs.tncmode import packet_of
from tests.support.env import ON_AIR
from tests.support.seamshapes import FrozenAir, LiveShape, RegistryShape, frozen_air
from tests.support.stubtnc import StubTnc

ON, OFF = {"digipeat": "true"}, {"digipeat": "false"}


def radio(id: int, settings: dict[str, str], kind: str = "fm", type: str = "kiss", enabled: bool = True, position: int | None = None) -> RadioSpec:
    return RadioSpec(id, kind, type, "", enabled, id if position is None else position, settings=settings)       # type: ignore[arg-type]


def airs(*specs: RadioSpec) -> list[FrozenAir]:
    return [frozen_air(spec) for spec in specs]


def test_the_default_settings_have_no_row() -> None:
    assert digi_rows(airs(*ON_AIR.radios)) == ()


def test_radio_1_with_digi_enabled_is_one_row_heard_on_it_sent_on_it() -> None:
    config = replace(ON_AIR, digi_enabled=True, hf_enabled=True)
    assert digi_rows(airs(*config.radios)) == (DigiRow(FM_ID, FM_ID),), "the HF radio repeats nothing"


def test_each_radio_that_may_repeat_and_has_its_digipeater_on_is_a_row_of_its_own_in_the_order_given() -> None:
    specs = (radio(3, ON), radio(1, ON), radio(2, {}, "hf", "mercury"), radio(4, OFF), radio(5, ON, type="kiss-tcp"), radio(6, ON, type="dummy"))
    assert digi_rows(airs(*specs)) == (DigiRow(3, 3), DigiRow(1, 1), DigiRow(5, 5), DigiRow(6, 6))
    assert all(row.heard == row.sent for row in digi_rows(airs(*specs))), "only A to A: nothing heard on one radio goes out on another"


def test_a_radio_that_is_not_allowed_or_cannot_say_repeats_nothing() -> None:
    hf = frozen_air(radio(HF_ID, {}, "hf", "mercury"))
    assert not repeats(hf), "HF: every station hears every frame"
    odd = replace(hf, allowed=FM_ALLOWED)                                                     # (allowed to, but its kind has no digipeat setting)
    assert not repeats(odd)


def test_the_digipeaters_rows_are_the_enabled_radios_and_follow_the_settings_in_force() -> None:
    lines = {1: StubTnc(), 3: StubTnc()}
    shapes = [LiveShape(radio(1, ON), (), lines[1]), LiveShape(radio(3, OFF), (), lines[3])]      # type: ignore[arg-type]
    config: Config = replace(ON_AIR, digi_enabled=True)
    digi = Digipeater(RegistryShape(shapes), lambda: config)
    assert digi.rows() == (DigiRow(1, 1),)
    shapes[1].spec = radio(3, ON)
    assert digi.rows() == (DigiRow(1, 1), DigiRow(3, 3)), "radio 3's digipeater turned on"
    shapes[0].spec = radio(1, ON, enabled=False)
    assert digi.rows() == (DigiRow(3, 3),), "a radio that is off repeats nothing"
    heard = ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("OH2XYZ"), (ax25.Address.parse("WIDE1-1"),), info=b">hi")
    digi.on_packet(packet_of("in", ax25.encode(heard), heard, digi.clock(), radio_id=3))
    digi.on_packet(packet_of("in", ax25.encode(heard), heard, digi.clock(), radio_id=1))
    assert (len(lines[3].sent), len(lines[1].sent)) == (1, 0), "a packet goes through the rows of the radio it came on"


# ---- the rows between two radios of a pair

FOUR = (radio(1, {}, type="kenwood-tnc2"), radio(2, {}, "hf", "mercury"), radio(3, {}, "lora", "lora-tcp"), radio(4, {}, type="kiss"))


def rows(*pairs: PairSpec, specs: tuple[RadioSpec, ...] = FOUR, call: str = "OH2GBA") -> tuple[PairRow, ...]:
    config = replace(ON_AIR, radios=specs, pairs=pairs, station_call=call)
    return rows_in_force(config, RegistryShape([LiveShape(spec, specs, StubTnc()) for spec in specs]).senders())     # type: ignore[arg-type]


def test_each_pair_that_passes_is_both_its_directions_in_the_order_of_the_pairs() -> None:
    found = rows(PairSpec(2, 3, True, 11), PairSpec(1, 2, True, 12), PairSpec(1, 4, False, 10))
    assert found == (PairRow(1, 2, ("OH2GBA", 12)), PairRow(2, 1, ("OH2GBA", 12)), PairRow(2, 3, ("OH2GBA", 11)), PairRow(3, 2, ("OH2GBA", 11))), "a pair that is off has none"
    assert rows(PairSpec(1, 4, True, 9)) == (PairRow(1, 4, ("OH2GBA", 9)), PairRow(4, 1, ("OH2GBA", 9))), "two FM radios are a pair like any other"


def test_a_pair_with_a_radio_off_removed_or_receive_only_has_no_row() -> None:
    off = tuple(replace(s, enabled=s.id != 2) for s in FOUR)
    assert rows(PairSpec(1, 2, True, 12), specs=off) == ()
    receive_only = tuple(replace(s, type="tnc-text") if s.id == 4 else s for s in FOUR)
    assert rows(PairSpec(1, 4, True, 12), specs=receive_only) == ()
    assert rows(PairSpec(1, 5, True, 12)) == (), "a radio the station does not have"


def test_a_dummy_radio_facing_a_real_one_has_no_row_and_two_dummies_have() -> None:
    dummies = (radio(1, {}, type="dummy"), radio(2, {}, "hf", "dummy-hf"), radio(3, {}, type="kiss"))
    assert rows(PairSpec(1, 3, True, 12), specs=dummies) == ()
    assert len(rows(PairSpec(1, 2, True, 12), specs=dummies)) == 2


@pytest.mark.parametrize("call", ["OH2GBA-12", "", "not a call"])
def test_a_station_call_that_has_the_pairs_ssid_or_does_not_parse_gives_no_row(call: str) -> None:
    assert rows(PairSpec(1, 2, True, 12), call=call) == ()


def test_two_enabled_pairs_with_one_ssid_pass_nothing_and_a_disabled_one_takes_none() -> None:
    assert rows(PairSpec(1, 2, True, 12), PairSpec(1, 3, True, 12)) == ()
    assert len(rows(PairSpec(1, 2, True, 12), PairSpec(1, 3, False, 12))) == 2
    assert rows(PairSpec(1, 2, True, None)) == (), "no SSID chosen yet"
