"""The radio an email goes out on (plan rule 3.5), as one function of the radios there are and the operator's choice (`email/radio`, the select of the E-mail tab): the radio registry's `email()` and the
status of the page read it, and the services send on it.

An email is one message to the gateway EMAIL-2, and it goes out once, on one radio. Only the radios that are enabled and can send count (`radiospec.senders`), of any kind. With one of them, that one,
whatever is stored (the page then shows no choice). Else the radio chosen while it is one of them. Else (no choice stored, or one that names a radio that is off) the first radio that can send, in the order
of the boxes (`radiospec.unheard_radio`). None only while no radio that can send is on. Migration 34 stored the radio a mail went on before there was a choice, and a radio that comes on beside it keeps
it there (neoaprs/sendonrule.py). Whether internet gateways hear a radio's type (`gateway_heard`) decides only what a radio that comes on writes. No I/O."""
from collections.abc import Iterable

from .radiospec import RadioId, RadioSpec, senders, unheard_radio
from .radiotype import RadioTypeError


def gateway_heard(spec: RadioSpec) -> bool:
    """Whether internet gateways hear what goes out on the radio (its type's `allowed.gateway_heard`); False for a type that is not known."""
    try:
        return spec.rtype.allowed.gateway_heard
    except RadioTypeError:
        return False


def email_radio(specs: Iterable[RadioSpec], chosen: RadioId | None) -> RadioId | None:
    """The id of the radio an email goes out on: the one radio that can send; else the one chosen while it is on and can send; else the first radio that can send. None while no radio that can send is on."""
    pool = list(specs)
    on = [spec.id for spec in senders(pool)]
    if len(on) == 1:
        return on[0]
    if chosen is not None and chosen in on:
        return chosen
    return unheard_radio(pool)
