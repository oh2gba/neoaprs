"""A line of APRS-IS (the packet as an Internet server hands it on: TNC2 text, `SRC>DST,PATH,qAC,SERVER:information`) as a `Packet` that came `via="is"`.

This is the one way a packet from the internet becomes a Packet; the connection that reads the lines is not here (it calls `parse_is_line` and hands the packet to the program through the one gate for internet
packets, `Services.hear_internet` of neoaprs/app.py). The packet has no AX.25 frame: its `raw` is the line itself, its `path` everything between the destination and the colon (digipeaters, the q-construct and
the server or iGate that follows it), and its `info` the bytes after the first colon, read by the ordinary dispatcher (a third-party packet inside it is opened as on the air).

The q-construct (APRS-IS, "q construct" specification) says how the packet entered the network: `qAC` from a verified client connection, `qAS` from an unverified one, `qAR` and `qAO` from an iGate that heard it on the
radio (`qAR`: a verified connection; `qAO`: receive only), `qAU` over UDP, `qAX` from an unverified login, `qAI` a packet that has been traced. The element after it is the server or the iGate.

Pure code, like the parsers it uses."""
import re
from datetime import datetime
from typing import NamedTuple

from .aprsthirdparty import parse_packet
from .callsign import PATH_ELEMENT, CallsignError, normal_name
from .packet import IS, Packet
from .route import IGATE_QS, is_q_construct

PATH_MAX = 32                                      # elements between the destination and the colon (a server adds a few to the 8 an AX.25 path may have)
_IPV6_ELEMENT = re.compile(r"[0-9A-Fa-f]{32}")      # what aprsc puts after the q-construct for a client it knows by an IPv6 address


class IsLineError(ValueError):
    """The line is no packet: a comment of the server (`# logresp ...`), or a header that is none. `comment` is true for a server's comment line, which is no fault."""

    def __init__(self, reason: str, comment: bool = False) -> None:
        super().__init__(reason)
        self.comment = comment


class QConstruct(NamedTuple):
    code: str                                      # `qAC`, `qAR`, `qAO`, ... as written
    server: str                                    # the call after it, the server or the iGate; empty when the line ends there


def q_construct(path: tuple[str, ...]) -> QConstruct | None:
    """The q-construct of a path and the call after it; None for a path with none."""
    for i, element in enumerate(path):
        if is_q_construct(element):
            return QConstruct(element, path[i + 1].rstrip("*") if i + 1 < len(path) else "")
    return None


def heard_by_radio(path: tuple[str, ...]) -> bool:
    """Whether the q-construct says an iGate heard the packet on the radio (`qAR`, `qAO`) and not that a client sent it into the network itself."""
    found = q_construct(path)
    return found is not None and found.code in IGATE_QS


def _path_is_sound(path: list[str]) -> bool:
    """Every element of the path is a name of APRS-IS, with a star if it has been repeated; after the q-construct one may also be the 32 hex characters of an IPv6 address."""
    after_q = False
    for element in path:
        if PATH_ELEMENT.fullmatch(element) is None and not (after_q and _IPV6_ELEMENT.fullmatch(element)):
            return False
        after_q = after_q or is_q_construct(element)
    return True


def is_comment(line: bytes | str) -> bool:
    """Whether the line is one of the server's comments (`# aprsc 2.1.15`, `# logresp OH2GBA verified, server T2FINLAND`) and no packet."""
    return line.lstrip()[:1] in (b"#", "#")


def parse_is_line(line: bytes | str, now: datetime) -> Packet:
    """The packet for a line of APRS-IS received at `now`, as `Packet(via="is")`. A line of text is taken as UTF-8; the bytes a server sends are kept as they are (the information field of a Mic-E packet is
    not text). The line's end (CR, LF) is not part of it. Raises IsLineError for a comment of the server and for a header that is none (no `>` or `:`, a source or destination that is neither a call nor a
    name APRS-IS allows, an element of the path that is none, an empty information field)."""
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
