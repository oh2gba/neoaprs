"""The radio an email goes out on (plan rule 3.5), as one function of the radios there are and the main radio: the radio registry's `email()` and the status of the page read it, and the services send on it.

This is TODAY's rule, written with ids (services/common.message_radio for the email gateway): the FM radio while it is enabled, else none (a mail is refused: internet gateways hear VHF, never HF). Package R3 writes
rule 3.5 in its place (the main radio when internet gateways hear its kind, else the first enabled radio of such a kind, else none). No I/O."""
from collections.abc import Iterable

from .radiospec import FM_ID, RadioId, RadioSpec, enabled


def email_radio(specs: Iterable[RadioSpec], main: RadioId | None) -> RadioId | None:
    """The id of the radio an email goes out on; None when none may carry it (`main` is rule 3.5's, unused by today's rule)."""
    return FM_ID if any(s.id == FM_ID for s in enabled(specs)) else None
