"""The radio an email goes out on (plan rule 3.5), from the radios and the operator's choice.

The choice is `email/radio`. An email goes out once, on one enabled radio that can send; no I/O.
"""

from collections.abc import Iterable

from .radiospec import RadioId, RadioSpec, senders, unheard_radio
from .radiotype import RadioTypeError


def gateway_heard(spec: RadioSpec) -> bool:
    """Return whether internet gateways hear the radio (its `gateway_heard`); False if unknown."""
    try:
        return spec.rtype.allowed.gateway_heard
    except RadioTypeError:
        return False


def email_radio(specs: Iterable[RadioSpec], chosen: RadioId | None) -> RadioId | None:
    """Return the radio an email goes out on: the only sender, else the chosen, else the first."""
    pool = list(specs)
    on = [spec.id for spec in senders(pool)]
    if len(on) == 1:
        return on[0]
    if chosen is not None and chosen in on:
        return chosen
    return unheard_radio(pool)
