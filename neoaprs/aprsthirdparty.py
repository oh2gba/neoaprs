"""Third-party packets: an iGate that hears a station on the internet (an ack, a reply) and puts it on the air transmits it wrapped in a frame of its own, `}SRC>DST,TCPIP,IGATE*:info`. The frame we hear is
the iGate's; the packet inside is what its sender said. `parse_packet` reads the wrapper and the packet inside it with the ordinary dispatcher; a wrapper inside a wrapper is not opened again (it stays
`Other("third-party")`), and a wrapper whose header is not a header stays one too.

Pure code, like the parsers it uses."""
from datetime import datetime

from neoaprs.aprsparse import parse
from neoaprs.callsign import CallsignError, format_call, parse_call
from neoaprs.packet import Decoded, ThirdParty

MARK = b"}"


def header_of(info: bytes) -> tuple[ThirdParty, bytes] | None:
    """The header of a third-party information field (`}SRC>DST[,PATH]:`) and the information field inside; None when the field is not one or the header is none (no `>` or `:`, a source or a
    destination that is no call). The path is kept as text, each piece as it is written (TCPIP, an iGate's call with its star)."""
    if info[:1] != MARK:
        return None
    head, colon, inner = info[1:].partition(b":")
    source, arrow, rest = head.decode("latin-1").partition(">")
    if not colon or not arrow or not inner:
        return None
    destination, *path = rest.split(",")
    try:
        names = [format_call(*parse_call(name.strip())) for name in (source, destination)]
    except CallsignError:
        return None
    return ThirdParty(names[0], names[1], tuple(piece.strip() for piece in path if piece.strip())), inner


def parse_packet(info: bytes, source: str, destination: str, now: datetime) -> tuple[Decoded, ThirdParty | None]:
    """What the information field of a packet from `source` to `destination` says and, when it is a third-party packet, its header: then `Decoded` is what the packet inside says, read as from the
    inner source to the inner destination."""
    opened = header_of(info)
    if opened is None:
        return parse(info, source, destination, now), None
    third, inner = opened
    return parse(inner, third.source, third.destination, now), third
