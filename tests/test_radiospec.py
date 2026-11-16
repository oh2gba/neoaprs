"""A radio as it is stored (neoaprs/radiospec.py): the live and the enabled radios by position, the number within a kind and the log's name of a radio, the radio of what no fact gives one, a station's choice and a set of radios
read against the radios that are enabled (plan §2), the name the operator types, and a radio's own value with its field's default for one that is missing or wrong."""
import logging

import pytest

from neoaprs.clock import utc
from neoaprs.radiospec import FM_ID, HF_ID, MAX_NAME, RadioError, RadioSpec, check_name, enabled, in_force_choice, in_force_set, live, log_name, number_in_kind, unheard_radio
from neoaprs.radiotypes import type_of

GONE = utc(2026, 11, 14, 9, 0)


def radio(id: int, kind: str = "fm", enabled: bool = True, position: int | None = None, name: str = "", removed: bool = False, **settings: str) -> RadioSpec:
    return RadioSpec(id, kind, {"fm": "kiss", "hf": "mercury", "lora": "dummy-lora"}[kind], name, enabled, id if position is None else position, GONE if removed else None, settings)  # type: ignore[arg-type]


SIX = [radio(1), radio(2, "hf", position=5), radio(3, "hf", enabled=False, position=2), radio(4, "fm", removed=True, position=0), radio(5, "lora", position=3), radio(6, "hf", name="20m", position=4)]


def test_the_live_radios_are_the_ones_not_removed_and_the_enabled_ones_are_also_on_both_by_position() -> None:
    assert [s.id for s in live(SIX)] == [1, 3, 5, 6, 2]
    assert [s.id for s in enabled(SIX)] == [1, 5, 6, 2]
    assert [s.id for s in live([radio(2, position=1), radio(1, position=1)])] == [1, 2], "the id after the position"
    assert enabled([]) == []


def test_a_radio_is_numbered_within_its_kind_by_id_and_a_removed_one_after_the_live_ones() -> None:
    assert [number_in_kind(s, SIX) for s in SIX] == [1, 1, 2, 2, 1, 3]
    assert [log_name(s, SIX) for s in SIX] == ["FM", "Mercury", "Mercury 2", "FM 2", "LoRa", "20m"]
    one = [radio(4, removed=True), radio(7)]
    assert [log_name(s, one) for s in one] == ["FM 2", "FM"], "the live one is the first FM radio once the other is removed"
    two_gone = [radio(1, removed=True), radio(3, removed=True), radio(5)]
    assert [log_name(s, two_gone) for s in two_gone] == ["FM 2", "FM 3", "FM"], "a live radio among the live ones of its kind, a removed one after them, by id among the removed"
    hf = [radio(1), radio(2, "hf", removed=True), radio(5, "hf")]
    assert log_name(hf[1], hf) != log_name(hf[2], hf), "a removed Mercury radio 2 and a live Mercury radio 5 are not both called Mercury"


def test_what_no_fact_gives_a_radio_goes_on_the_first_that_can_send_in_the_order_of_the_boxes() -> None:
    assert unheard_radio(SIX) == 1 and unheard_radio([radio(1, position=9), *SIX[1:]]) == 5, "by position: radio 1's box moved last, the LoRa radio's is the first that is on"
    assert unheard_radio([radio(1, enabled=False), radio(2, "hf")]) == 2
    assert unheard_radio([radio(1, enabled=False)]) is None and unheard_radio([]) is None


def test_a_stations_choice_that_names_no_enabled_radio_is_automatic_and_with_one_radio_that_one() -> None:
    assert in_force_choice(6, SIX) == 6 and in_force_choice(3, SIX) is None and in_force_choice(4, SIX) is None and in_force_choice(None, SIX) is None
    alone = [radio(1, enabled=False), radio(2, "hf")]
    assert in_force_choice(1, alone) == 2 and in_force_choice(None, alone) == 2
    assert in_force_choice(1, []) is None


def test_a_set_of_radios_is_its_enabled_ticks_none_when_none_is_on_and_with_one_radio_that_one() -> None:
    assert in_force_set([2, 1, 3], SIX) == (1, 2), "the enabled ticks by position"
    assert in_force_set([3, 4], SIX) == () and in_force_set([], SIX) == (), "ticked nowhere is not sent: no radio stands in"
    assert in_force_set([1], [radio(1, enabled=False), radio(2, "hf")]) == (2,), "one radio that can send: that one"
    assert in_force_set([1], [radio(1, enabled=False)]) == ()


def test_a_name_is_stripped_short_printable_ascii_and_unique_among_the_live_radios() -> None:
    assert check_name("  ", SIX, None) == "" and check_name(" 2m ", SIX, None) == "2m"
    assert check_name("20M", SIX, 6) == "20M", "its own name, in other letters"
    assert check_name("x" * MAX_NAME, SIX, None) == "x" * MAX_NAME
    with pytest.raises(RadioError, match="radio 6's already"):
        check_name("20M", SIX, 1)
    with pytest.raises(RadioError, match="at most 8"):
        check_name("x" * (MAX_NAME + 1), SIX, None)
    for bad in ("Kälte", "a\tb"):
        with pytest.raises(RadioError, match="printable ASCII"):
            check_name(bad, SIX, None)
    assert check_name("old", [radio(4, name="old", removed=True)], None) == "old", "a removed radio's name is free"


def test_a_radios_value_is_parsed_by_its_field_and_a_missing_or_wrong_one_is_the_default(caplog: pytest.LogCaptureFixture) -> None:
    spec = radio(1, port="/dev/ttyUSB0", baud="19200", digipeat="yes", tcp_port="0")
    assert spec.rtype is type_of("kiss") and not spec.removed and radio(4, removed=True).removed
    assert (spec.value("port"), spec.value("baud"), spec.value("digipeat"), spec.value("beacon"), spec.value("tcp_host")) == ("/dev/ttyUSB0", 19200, True, True, "127.0.0.1")
    with caplog.at_level(logging.WARNING, "neoaprs.radiospec"):
        assert spec.value("tcp_port") == 8001
    assert "radio/1/tcp_port" in caplog.text and "the default 8001 is used" in caplog.text
    with pytest.raises(RadioError, match="radio/2/port"):
        radio(2, "hf").value("port")                                    # (a key of another kind: the FM kind's port; every HF key is an FM one too, the Sound card type's)
    assert radio(2, "hf").value("tx_gain_db") == 0
    assert (FM_ID, HF_ID) == (1, 2)


def test_a_spec_is_a_value() -> None:
    assert radio(1, port="a") == radio(1, port="a") and hash(radio(1, port="a")) == hash(radio(1, port="a"))
    assert radio(1, port="a") != radio(1, port="b")
    assert len({radio(1), radio(1), radio(2, "hf")}) == 2
