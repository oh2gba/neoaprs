"""Third-party packets: an iGate puts an internet packet on the air wrapped in its own frame.

The frame is `}SRC>DST,TCPIP,IGATE*:info`. A wrapper inside a wrapper, or one with an invalid
header, is not opened.
"""

from datetime import datetime

from neoaprs.aprsparse import parse
from neoaprs.callsign import CallsignError, normal_name
from neoaprs.packet import Decoded, ThirdParty

MARK = b"}"


def header_of(info: bytes) -> tuple[ThirdParty, bytes] | None:
    """Return the header of a third-party field (`}SRC>DST[,PATH]:`) and the inner field.

    None if the field is not one or the header is invalid. Names may be APRS-IS names (`WINLINK`).
    """
    if info[:1] != MARK:
        return None
    head, colon, inner = info[1:].partition(b":")
    source, arrow, rest = head.decode("latin-1").partition(">")
    if not colon or not arrow or not inner:
        return None
    destination, *path = rest.split(",")
    try:
        names = [normal_name(name) for name in (source, destination)]
    except CallsignError:
        return None
    return ThirdParty(names[0], names[1], tuple(piece.strip() for piece in path if piece.strip())), inner


def parse_packet(info: bytes, source: str, destination: str, now: datetime) -> tuple[Decoded, ThirdParty | None]:
    """Return what the field says and, for a third-party packet, its header.

    `Decoded` is what the inner packet says, read from the inner source to destination.
    """
    opened = header_of(info)
    if opened is None:
        return parse(info, source, destination, now), None
    third, inner = opened
    return parse(inner, third.source, third.destination, now), third
