"""The choices the registry makes for radio 1 (FM) and radio 2 (HF), written out as the expectation
that tests/test_seams.py and tests/test_radioregistry.py hold it to, over the cases of both radios
on or off, heard on each or not, and the operator's choice of either.
"""
from neoaprs.radiospec import FM_ID, HF_ID, RadioId


def main_before(fm_on: bool, hf_on: bool) -> RadioId | None:
    """The radio of what addresses no station: the FM radio while it is on, else the HF one; none
    while neither is (the stopped FM radio of before sent nothing)."""
    return FM_ID if fm_on else HF_ID if hf_on else None


def station_before(fm_on: bool, hf_on: bool, fm: int, hf: int, choice: RadioId | None) -> RadioId | None:
    """The radio a message to a station went out on: the one that is on unless both are; then the
    operator's choice, else the HF radio for a station heard on HF alone, else the FM one. `fm` and
    `hf` are what each radio heard of the station (0 for a station the book does not hold)."""
    if not (fm_on and hf_on):
        return main_before(fm_on, hf_on)
    if choice is not None:
        return choice
    return HF_ID if hf > 0 and fm == 0 else FM_ID


def packet_before(fm_on: bool, hf_on: bool, came_on: RadioId) -> RadioId | None:
    """The radio an answer to a packet went out on: the one it came on while that one is on, else
    the other."""
    on = {FM_ID: fm_on, HF_ID: hf_on}
    return came_on if on[came_on] else main_before(fm_on, hf_on)


def email_before(fm_on: bool, hf_on: bool) -> RadioId | None:
    """The radio an email went out on: the FM radio, which the internet's gateways hear; none (the
    mail refused) while it is off."""
    return FM_ID if fm_on else None


def enabled_before(fm_on: bool, hf_on: bool) -> list[RadioId]:
    return [id for id, on in ((FM_ID, fm_on), (HF_ID, hf_on)) if on]
