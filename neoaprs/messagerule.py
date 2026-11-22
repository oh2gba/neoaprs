"""The radio a message of ours to a station goes out on (plan rule 3.2). No I/O.

Order: the only sender, the operator's choice, the radio that heard the station recently
(local kinds first), the one that heard it last, else the first sender.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta

from .policy import MESSAGE_RADIO_RECENT_HOURS
from .radiospec import NOT_HEARD, RadioHeard, RadioId, RadioSpec, in_force_choice, senders, unheard_radio
from .radiotype import LOCAL_KINDS

RECENT = timedelta(hours=MESSAGE_RADIO_RECENT_HOURS)


def message_radio(
    choice: RadioId | None, heard: Mapping[RadioId, RadioHeard], specs: Iterable[RadioSpec], now: datetime
) -> RadioId | None:
    """Return the id of the radio the message goes out on; None if no enabled radio can send."""
    pool = list(specs)
    on = senders(pool)
    # one radio that sends: that one; else the operator's choice while it names one
    if (picked := in_force_choice(choice, on)) is not None:
        return picked
    heard_on = [
        (order, spec, found) for order, spec in enumerate(on) if (found := heard.get(spec.id, NOT_HEARD)).count > 0
    ]
    if not heard_on:
        return unheard_radio(pool)
    recent = [entry for entry in heard_on if entry[2].last_at is not None and entry[2].last_at >= now - RECENT]
    local = [entry for entry in recent if entry[1].kind in LOCAL_KINDS]
    return _latest(local or recent or heard_on)


def _latest(entries: list[tuple[int, RadioSpec, RadioHeard]]) -> RadioId:
    """Return the radio that heard the station last; ties go to a local kind, then position."""
    return max(entries, key=_when)[1].id


def _when(entry: tuple[int, RadioSpec, RadioHeard]) -> tuple[float, bool, int]:
    order, spec, found = entry
    return (float("-inf") if found.last_at is None else found.last_at.timestamp(), spec.kind in LOCAL_KINDS, -order)


def stood_in(
    radio: RadioId,
    choice: RadioId | None,
    heard: Mapping[RadioId, RadioHeard],
    known_since: datetime | None,
    taken_at: datetime,
) -> bool:
    """Return whether the radio only stood in for the station's own radio, which was off."""
    if choice == radio or heard.get(radio, NOT_HEARD).count > 0 or known_since is None or known_since > taken_at:
        return False
    return any(found.count > 0 for id, found in heard.items() if id != radio)
