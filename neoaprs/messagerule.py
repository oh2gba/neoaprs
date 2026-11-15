"""The radio a message of ours to a station goes out on (plan rule 3.2), as one function of the operator's choice for the station, what each radio heard of it and the radios there are.

Only the radios that are enabled and can send count (`radiospec.senders`: a receive-only radio is never picked). With one of them, that one, whatever is stored. Else the operator's choice while it names an enabled radio. Else the radio the station was heard on most recently within
policy.MESSAGE_RADIO_RECENT_HOURS, a radio of a local kind (radiotype.LOCAL_KINDS: fm, lora) before any other when one heard it in that time (a station heard on FM an hour ago and on HF a minute ago is near:
its message goes by FM, and HF airtime is everyone's). Else the radio it was heard on last at all. A station no enabled radio heard goes on the main radio. Only the enabled radios that send count: what a
radio that is off or removed heard is no reason to send on it. Of radios heard at the same time a local kind comes first, then the order of the radios (their position).

The rule is asked at a message's first attempt; the message keeps that radio until it ends unless the operator chooses another for the station or that radio goes (services/messageradio.py), or the radio
only stood in for the station's own (`stood_in`). No I/O."""
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta

from .policy import MESSAGE_RADIO_RECENT_HOURS
from .radiospec import NOT_HEARD, RadioHeard, RadioId, RadioSpec, in_force_choice, senders
from .radiotype import LOCAL_KINDS

RECENT = timedelta(hours=MESSAGE_RADIO_RECENT_HOURS)


def message_radio(choice: RadioId | None, heard: Mapping[RadioId, RadioHeard], specs: Iterable[RadioSpec], main: RadioId | None, now: datetime) -> RadioId | None:
    """The id of the radio the message goes out on; None when no radio that can send is enabled (`main` is then None too)."""
    on = senders(specs)
    if (picked := in_force_choice(choice, on)) is not None:            # (one radio that sends: that one; else the operator's choice while it names one)
        return picked
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


def stood_in(radio: RadioId, choice: RadioId | None, heard: Mapping[RadioId, RadioHeard], known_since: datetime | None, taken_at: datetime) -> bool:
    """Whether the radio a message was given at `taken_at` only stood in for the station's own, which was off: it has never heard the station, the operator's choice does not name it, and another radio had
    heard the station by then (the station was in the book, `known_since`, and another radio has heard it). The radio that heard the station, the one Route names and the main radio of a station no radio had
    heard are the rule's choice, and no stand-in."""
    if choice == radio or heard.get(radio, NOT_HEARD).count > 0 or known_since is None or known_since > taken_at:
        return False
    return any(found.count > 0 for id, found in heard.items() if id != radio)
