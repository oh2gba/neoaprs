"""The radio a message of ours to a station goes out on (plan rule 3.2), as one function of the operator's choice for the station, what each radio heard of it and the radios there are.

With one enabled radio, that one, whatever is stored. Else the operator's choice while it names an enabled radio. Else the radio the station was heard on most recently within
policy.MESSAGE_RADIO_RECENT_HOURS, a radio of a local kind (radiotype.LOCAL_KINDS: fm, lora) before any other when one heard it in that time (a station heard on FM an hour ago and on HF a minute ago is near:
its message goes by FM, and HF airtime is everyone's). Else the radio it was heard on last at all. A station no enabled radio heard goes on the main radio. Only the enabled radios count: what a radio that is
off or removed heard is no reason to send on it. Of radios heard at the same time a local kind comes first, then the order of the radios (their position).

The rule is asked at a message's first attempt; the message keeps that radio until it ends unless the operator chooses another for the station or that radio goes (services/messageradio.py). No I/O."""
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta

from .policy import MESSAGE_RADIO_RECENT_HOURS
from .radiospec import NOT_HEARD, RadioHeard, RadioId, RadioSpec, enabled
from .radiotype import LOCAL_KINDS

RECENT = timedelta(hours=MESSAGE_RADIO_RECENT_HOURS)


def message_radio(choice: RadioId | None, heard: Mapping[RadioId, RadioHeard], specs: Iterable[RadioSpec], main: RadioId | None, now: datetime) -> RadioId | None:
    """The id of the radio the message goes out on; None when no radio is enabled (`main` is then None too)."""
    on = enabled(specs)
    if len(on) == 1:
        return on[0].id
    if choice is not None and any(spec.id == choice for spec in on):
        return choice
    heard_on = [(order, spec, found) for order, spec in enumerate(on) if (found := heard.get(spec.id, NOT_HEARD)).count > 0]
    if not heard_on:
        return main
    recent = [entry for entry in heard_on if entry[2].last_at is not None and entry[2].last_at >= now - RECENT]
    local = [entry for entry in recent if entry[1].kind in LOCAL_KINDS]
    return _latest(local or recent or heard_on)


def _latest(entries: list[tuple[int, RadioSpec, RadioHeard]]) -> RadioId:
    """The radio of these that heard the station last; of equal times (a radio without a time is before any time) a local kind, then the first by position."""
    return max(entries, key=_when)[1].id


def _when(entry: tuple[int, RadioSpec, RadioHeard]) -> tuple[float, bool, int]:
    order, spec, found = entry
    return (float("-inf") if found.last_at is None else found.last_at.timestamp(), spec.kind in LOCAL_KINDS, -order)
