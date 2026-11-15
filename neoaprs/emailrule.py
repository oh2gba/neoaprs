"""The radio an email goes out on (plan rule 3.5), as one function of the radios there are and the main radio: the radio registry's `email()` and the status of the page read it, and the services send on it.

An email is a message to the gateway EMAIL-2, a station of the internet: it arrives only where an internet gateway (an iGate) hears the frame. Whether gateways hear a radio is its type's (`Allowed.gateway_heard`:
the FM types yes, the HF ones no). So the email goes on the main radio when gateways hear it, else on the first enabled radio that they hear (by position), else on none, and then a mail is refused. With the radios
of today this is what it always was: the FM radio while it is on, else none. A radio whose type is not known is heard by no gateway. No I/O."""
from collections.abc import Iterable

from .radiospec import RadioId, RadioSpec, senders
from .radiotype import RadioTypeError


def gateway_heard(spec: RadioSpec) -> bool:
    """Whether internet gateways hear what goes out on the radio (its type's `allowed.gateway_heard`); False for a type that is not known."""
    try:
        return spec.rtype.allowed.gateway_heard
    except RadioTypeError:
        return False


def email_radio(specs: Iterable[RadioSpec], main: RadioId | None) -> RadioId | None:
    """The id of the radio an email goes out on: the main radio while gateways hear it, else the first enabled radio by position that gateways hear; None when no enabled radio is heard by one."""
    heard = [spec.id for spec in senders(specs) if gateway_heard(spec)]
    if main is not None and main in heard:
        return main
    return heard[0] if heard else None
