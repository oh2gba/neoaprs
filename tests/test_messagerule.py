"""The radio a message of ours to a station goes out on (neoaprs/messagerule.py, plan rule 3.2), as a table: the operator's choice while its radio is on, and one that is off or removed; the radio heard most
recently within six hours (policy.MESSAGE_RADIO_RECENT_HOURS), a local kind (FM, LoRa) before HF in that time; the radio heard last at all after that; a call never heard on the main radio; one enabled radio
whatever else is said; no radio, none. And a radio a message was given that only stood in for the station's own (`stood_in`): one that never heard the station, that no Route names, while another had
heard it by then; not the main radio of a station no radio had heard."""
from datetime import datetime, timedelta

import pytest

from neoaprs.clock import utc
from neoaprs.messagerule import message_radio, stood_in
from neoaprs.policy import MESSAGE_RADIO_RECENT_HOURS
from neoaprs.radiospec import FM_ID, HF_ID, RadioHeard, RadioId, RadioSpec, main_radio

NOW = utc(2026, 11, 14, 18, 0)
FM2, LORA = 3, 4


def ago(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


def radios(*off: RadioId, removed: tuple[RadioId, ...] = (), order: tuple[RadioId, ...] = (FM_ID, HF_ID, FM2, LORA)) -> tuple[RadioSpec, ...]:
    """FM (1), HF (2), a second FM radio (3) and a LoRa radio (4), by position in `order`; those in `off` not enabled, those in `removed` removed."""
    kinds = {FM_ID: ("fm", "kiss"), HF_ID: ("hf", "mercury"), FM2: ("fm", "kiss"), LORA: ("lora", "dummy-lora")}
    return tuple(RadioSpec(id, kinds[id][0], kinds[id][1], "", id not in off, order.index(id) + 1, ago(100) if id in removed else None) for id in order)


def heard(**by: float | None) -> dict[RadioId, RadioHeard]:
    """What each radio heard, by name (fm, hf, fm2, lora): hours ago, or None for heard with no time."""
    ids = {"fm": FM_ID, "hf": HF_ID, "fm2": FM2, "lora": LORA}
    return {ids[name]: RadioHeard(3, None if hours is None else ago(hours)) for name, hours in by.items()}


def pick(choice: RadioId | None, seen: dict[RadioId, RadioHeard], specs: tuple[RadioSpec, ...]) -> RadioId | None:
    return message_radio(choice, seen, specs, main_radio(specs, None), NOW)


ALL = radios()
FM_HF = radios(FM2, LORA)

CASES = [
    # (what the case is, the choice, what was heard, the radios, the radio)
    ("the choice, while its radio is on", HF_ID, heard(fm=0.1), FM_HF, HF_ID),
    ("the choice of a radio that is off: the rule", HF_ID, heard(fm=0.1, hf=0.05), radios(HF_ID, LORA), FM_ID),
    ("the choice of a radio that is removed: the rule", FM2, heard(hf=1), radios(LORA, removed=(FM2,)), HF_ID),
    ("heard on HF alone", None, heard(hf=2), FM_HF, HF_ID),
    ("heard on FM alone", None, heard(fm=30), FM_HF, FM_ID),
    ("both within six hours: FM, a local kind, though HF heard it later", None, heard(fm=5.9, hf=0.01), FM_HF, FM_ID),
    ("FM over six hours ago, HF within: HF", None, heard(fm=MESSAGE_RADIO_RECENT_HOURS + 0.5, hf=1), FM_HF, HF_ID),
    ("neither within six hours: the radio heard last at all", None, heard(fm=9, hf=7), FM_HF, HF_ID),
    ("neither within six hours, FM later", None, heard(fm=7, hf=9), FM_HF, FM_ID),
    ("two local radios within the time: the one heard later", None, heard(fm=3, fm2=1, hf=0.1), radios(LORA), FM2),
    ("LoRa is a local kind too", None, heard(lora=2, hf=0.1), radios(FM_ID, FM2), LORA),
    ("at the same moment: a local kind first", None, {FM_ID: RadioHeard(1, ago(1)), HF_ID: RadioHeard(1, ago(1))}, FM_HF, FM_ID),
    ("at the same moment over six hours ago, HF first by position: a local kind first", None, {FM_ID: RadioHeard(1, ago(8)), HF_ID: RadioHeard(1, ago(8))}, radios(FM2, LORA, order=(HF_ID, FM_ID, FM2, LORA)), FM_ID),
    ("at the same moment on two FM radios: the first by position", None, heard(fm=1, fm2=1), radios(HF_ID, LORA, order=(FM2, FM_ID, HF_ID, LORA)), FM2),
    ("heard with no time: heard, but not lately", None, heard(fm=None, hf=8), FM_HF, HF_ID),
    ("heard on no radio with a time", None, heard(fm=None, hf=None), FM_HF, FM_ID),
    ("never heard: the main radio", None, {}, FM_HF, FM_ID),
    ("never heard, the main radio the first by position", None, {}, radios(FM2, LORA, order=(HF_ID, FM_ID, FM2, LORA)), HF_ID),
    ("heard only on a radio that is off: as never heard", None, heard(hf=0.1), radios(HF_ID, LORA), FM_ID),
    ("one enabled radio: that one, whatever is chosen", HF_ID, heard(hf=0.1), radios(HF_ID, FM2, LORA), FM_ID),
    ("one enabled radio: that one, whatever heard the station", None, heard(fm=0.1), radios(FM_ID, FM2, LORA), HF_ID),
    ("no radio enabled: none", FM_ID, heard(fm=0.1), radios(FM_ID, HF_ID, FM2, LORA), None),
]


@pytest.mark.parametrize(("case", "choice", "seen", "specs", "expected"), CASES, ids=[case[0] for case in CASES])
def test_the_radio_of_a_message(case: str, choice: RadioId | None, seen: dict[RadioId, RadioHeard], specs: tuple[RadioSpec, ...], expected: RadioId | None) -> None:
    assert pick(choice, seen, specs) == expected, case


def test_the_six_hours_are_counted_from_now_to_the_minute() -> None:
    inside, outside = MESSAGE_RADIO_RECENT_HOURS - 1 / 60, MESSAGE_RADIO_RECENT_HOURS + 1 / 60
    assert pick(None, heard(fm=inside, hf=0.1), FM_HF) == FM_ID
    assert pick(None, heard(fm=outside, hf=0.1), FM_HF) == HF_ID
    six = NOW - timedelta(hours=MESSAGE_RADIO_RECENT_HOURS)
    assert pick(None, {FM_ID: RadioHeard(1, six), HF_ID: RadioHeard(1, ago(0.1))}, FM_HF) == FM_ID, "heard six hours ago to the second: within"
    assert pick(None, {FM_ID: RadioHeard(1, six - timedelta(seconds=1)), HF_ID: RadioHeard(1, ago(0.1))}, FM_HF) == HF_ID, "a second more: not"
    assert pick(None, {FM_ID: RadioHeard(1, NOW + timedelta(minutes=5)), HF_ID: RadioHeard(1, ago(0.1))}, FM_HF) == FM_ID, "a time after now (a clock that stepped back) is recent"


def test_today_two_radios_choose_as_before_while_the_station_was_heard_lately() -> None:
    """The station of FM and HF, heard within the time: what the two radios of before chose (FM unless heard on HF alone; the operator's choice; a station never heard on FM, the main radio)."""
    for fm in (None, 0.5):
        for hf in (None, 0.2):
            seen = heard(**{name: hours for name, hours in (("fm", fm), ("hf", hf)) if hours is not None})
            before = HF_ID if hf is not None and fm is None else FM_ID
            assert pick(None, seen, FM_HF) == before, (fm, hf)
            assert pick(HF_ID, seen, FM_HF) == HF_ID and pick(FM_ID, seen, FM_HF) == FM_ID


STOOD_IN = [
    # (what the case is, the radio the message was given, the choice, what was heard, when the station was first in the book, the radio stood in)
    ("HF given while FM, which heard the station, was off: a stand-in", HF_ID, None, heard(fm=1), ago(2), True),
    ("HF heard the station too: the rule's choice", HF_ID, None, heard(fm=1, hf=3), ago(4), False),
    ("Route names HF: the operator's choice", HF_ID, HF_ID, heard(fm=1), ago(2), False),
    ("Route names another radio: HF still stood in", HF_ID, FM2, heard(fm=1), ago(2), True),
    ("never heard by any radio: the main radio, the rule's choice", HF_ID, None, {}, None, False),
    ("in the book from the internet alone: as never heard", HF_ID, None, {}, ago(2), False),
    ("first heard after the radio was given: the main radio of a station never heard then", HF_ID, None, heard(fm=0.5), ago(0.5), False),
    ("first heard when the radio was given, to the second: heard by then", HF_ID, None, heard(fm=1), ago(1), True),
    ("heard on a radio of any kind: FM stood in for LoRa", FM_ID, None, heard(lora=3), ago(3), True),
    ("a count of 0 is not heard", HF_ID, None, {FM_ID: RadioHeard(0, ago(2))}, ago(2), False),
]


@pytest.mark.parametrize(("case", "radio", "choice", "seen", "known", "expected"), STOOD_IN, ids=[case[0] for case in STOOD_IN])
def test_a_radio_that_only_stood_in_for_the_stations_own(case: str, radio: RadioId, choice: RadioId | None, seen: dict[RadioId, RadioHeard], known: datetime | None, expected: bool) -> None:
    """The radio a message was given an hour ago (messagerule.stood_in), from what each radio heard of the station and when the station was first in the book."""
    assert stood_in(radio, choice, seen, known, ago(1)) is expected, case
