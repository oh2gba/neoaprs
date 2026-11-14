"""The digipeater as a table (neoaprs/services/digipeater.py `DigiRow`, `digi_rows`, plan rule 3.4): one row "heard on A, sent on A" for each enabled radio whose type may repeat and whose own digipeater the
operator turned on (radio 1's is `digi/enabled`), none on HF, none for a radio that is off, none from one radio to another; the rows follow the settings in force, and a packet goes through the rows of the
radio it came on. The duplicate check, the burst and the counts per radio are tests/test_digipeater.py's."""
from dataclasses import replace

from neoaprs import ax25
from neoaprs.config import Config
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.radiotypes.common import FM_ALLOWED
from neoaprs.services.digipeater import DigiRow, Digipeater, digi_rows, repeats
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
