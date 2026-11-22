"""Parse a line of APRS-IS (`SRC>DST,PATH:information`) into a `Packet` with `via="is"`.

The packet has no AX.25 frame. The q-construct in the path says how it entered the network;
the call after it is the server or iGate.
"""
import re
from datetime import datetime
from typing import NamedTuple

from .aprsthirdparty import parse_packet
from .callsign import PATH_ELEMENT, CallsignError, normal_name
from .packet import IS, Packet
from .route import IGATE_QS, is_q_construct

MAX_LINE = 512  # bytes of an APRS-IS line with its CR LF
# elements between destination and colon (servers add a few to the 8 an AX.25 path may have)
PATH_MAX = 32
# what aprsc puts after the q-construct for an IPv6 client
_IPV6_ELEMENT = re.compile(r"[0-9A-Fa-f]{32}")


class IsLineError(ValueError):
    """The line is no packet: a server comment (`# logresp ...`, `comment` true) or a bad header."""

    def __init__(self, reason: str, comment: bool = False) -> None:
        super().__init__(reason)
        self.comment = comment


class QConstruct(NamedTuple):
    code: str  # `qAC`, `qAR`, ... as written
    server: str  # the call after it; empty when the line ends there


def q_construct(path: tuple[str, ...]) -> QConstruct | None:
    """Return the q-construct of a path and the call after it; None for a path with none."""
    for i, element in enumerate(path):
        if is_q_construct(element):
            return QConstruct(element, path[i + 1].rstrip("*") if i + 1 < len(path) else "")
    return None


def heard_by_radio(path: tuple[str, ...]) -> bool:
    """Return whether the q-construct (`qAR`, `qAO`) says an iGate heard the packet on the radio."""
    found = q_construct(path)
    return found is not None and found.code in IGATE_QS


def _path_is_sound(path: list[str]) -> bool:
    """Return whether every path element is an APRS-IS name, or IPv6 hex after the q-construct."""
    after_q = False
    for element in path:
        if PATH_ELEMENT.fullmatch(element) is None and not (after_q and _IPV6_ELEMENT.fullmatch(element)):
            return False
        after_q = after_q or is_q_construct(element)
    return True


def is_comment(line: bytes | str) -> bool:
    """Return whether the line is a server comment (`# aprsc 2.1.15`, `# logresp ...`)."""
    return line.lstrip()[:1] in (b"#", "#")


def parse_is_line(line: bytes | str, now: datetime) -> Packet:
    """Return the packet for a line of APRS-IS received at `now`; bytes are kept as they are.

    Raise IsLineError for a server comment or a bad header.
    """
    data = line.encode("utf-8") if isinstance(line, str) else bytes(line)
    data = data.rstrip(b"\r\n")
    if is_comment(data):
        raise IsLineError("a comment of the server", comment=True)
    head, colon, info = data.partition(b":")
    source, arrow, rest = head.decode("latin-1").partition(">")
    if not colon or not arrow or not info:
        raise IsLineError("not a packet: it has no SRC>DST:information")
    destination, *path = (piece.strip() for piece in rest.split(","))
    try:
        names = [normal_name(name) for name in (source, destination)]
    except CallsignError:
        raise IsLineError("the source or the destination is neither a call nor a name APRS-IS allows") from None
    if len(path) > PATH_MAX or not _path_is_sound(path):
        raise IsLineError("the path has an element that is none")
    decoded, third_party = parse_packet(info, names[0], names[1], now)
    return Packet(heard_at=now, direction="in", raw=data, source=names[0], destination=names[1], path=tuple(path), info=info, decoded=decoded, third_party=third_party, via=IS)
