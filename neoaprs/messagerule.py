"""The radio a message of ours to a station goes out on (plan rule 3.2), as one function of the station's choice, what each radio heard of it and the radios there are.

This is TODAY's rule, written with ids (neoaprs/radios.py `Radios.for_station`): with one enabled radio, that one; the operator's choice while it names an enabled radio; else, while both of today's radios are
enabled, the HF radio when the station was heard on HF alone and the FM radio otherwise (it is near, or never heard: HF airtime is everyone's); else the main radio. Package R2 writes rule 3.2 in its place
(the radio heard most recently within policy.MESSAGE_RADIO_RECENT_HOURS, a local kind first). No I/O."""
from collections.abc import Iterable, Mapping
from datetime import datetime

from .radiospec import FM_ID, HF_ID, NOT_HEARD, RadioHeard, RadioId, RadioSpec, enabled


def message_radio(choice: RadioId | None, heard: Mapping[RadioId, RadioHeard], specs: Iterable[RadioSpec], main: RadioId | None, now: datetime) -> RadioId | None:
    """The id of the radio the message goes out on; None when no radio is enabled (`now` is rule 3.2's, unused by today's rule)."""
    on = [s.id for s in enabled(specs)]
    if len(on) == 1:
        return on[0]
    if choice is not None and choice in on:
        return choice
    if FM_ID in on and HF_ID in on:
        hf_alone = heard.get(HF_ID, NOT_HEARD).count > 0 and heard.get(FM_ID, NOT_HEARD).count == 0
        return HF_ID if hf_alone else FM_ID
    return main
