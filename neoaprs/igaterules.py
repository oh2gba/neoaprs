"""What a receive-only iGate puts on APRS-IS: which of the frames heard on the radio go, and the line each becomes. Pure code; the service (services/igate.py) keeps the duplicates, the counts and the connection.

The rules, and where each comes from:

* APRS-IS "IGate details", https://www.aprs-is.net/IGateDetails.aspx, RF to APRS-IS: every packet heard on the radio is gated except a frame that is no UI frame (control 0x03, PID 0xF0); a generic query (data type `?`);
  a packet with TCPIP, TCPXX, NOGATE or RFONLY in its header (the last two are optional there, and kept here: they ask for exactly this); and a third-party packet (data type `}`) that has TCPIP or TCPXX in the
  header of the packet inside. A third-party packet without them has the RF header and the `}` taken off and the packet inside is judged again from the first rule (WB2OSZ, "Successful APRS IGate Operation",
  https://github.com/wb2osz/direwolf-doc, "Gating Criteria from RF to Server": "processed again starting with step 1").
* The path is not changed, "except to append ,qAR,IGATECALL. Use qAO instead if the IGate is receive-only" (the same page). So the path is the one heard, the hops not used yet as well, and the
  used ones marked the way an AX.25 monitor writes it: a `*` after the last digipeater the frame has been through (`OH2XYZ-9>APZ123,WIDE1*,WIDE2-1,qAO,OH2GBA-10:...`).
* The q construct (https://www.aprs-is.net/q.aspx): "qAO: An IGate gating from RF without being able to gate messages back to RF. Receive-only IGates use this for everything they gate", followed by the IGate's call,
  without a `*`. q constructs and the `,I` construct "must never appear on RF", so a frame that carries one is not believed and not gated.
* The information field goes as the bytes it is: APRS-IS is a byte stream whose line ends at the first CR or LF, so a packet with a CR or LF inside its field cannot be gated (the CR or LF at its very end, which
  a TNC may add, is cut off, as iGates do); a line is at most 512 bytes with its CR LF (https://www.aprs-is.net/Connecting.aspx).
* The source must be a station: a call (neoaprs/callsign.py), not a placeholder (N0CALL, NOCALL, MYCALL, SERVER, which APRS-IS servers drop) and not a name that stands for a digipeater or the internet (WIDEn, TRACEn,
  RELAY, TCPIP, TCPXX, NOGATE, RFONLY; aprx drops the same).
* Our own call as the source is not gated: our position goes to APRS-IS straight from us (`TCPIP*`, services/igate.py), and the frame of ours that a digipeater repeats would arrive a second time under the call of
  the login. The specification says nothing of it; this is the choice.

The 30 seconds of duplicates are the service's (the specification says nothing of them either)."""
import re
from dataclasses import dataclass

from neoaprs import ax25
from neoaprs.aprsthirdparty import MARK, header_of
from neoaprs.callsign import PLACEHOLDER_CALLS, CallsignError, normal_name
from neoaprs.packet import DuplicateKey, duplicate_key
from neoaprs.route import INTERNET_MARKERS, NO_GATE_MARKERS, is_q_construct

Q_CONSTRUCT = "qAO"
MAX_LINE = 512                                       # bytes of a line of APRS-IS with its CR LF
MAX_UNWRAP = 3                                       # third-party wrappers opened one in another; a deeper one is not a packet
ALIASES = ("WIDE", "TRACE", "RELAY", "TCP", "NOGATE", "RFONLY", "SERVER", "BEACON")        # sources that are no station: the names of paths and of the internet
_PATH_ELEMENT = re.compile(r"[A-Za-z0-9]{1,9}(?:-[A-Za-z0-9]{1,2})?\*?")      # an element of a path on the air (stricter than a name on APRS-IS: callsign.PATH_ELEMENT)

TCPIP, NOGATE, QUERY, SOURCE, OWN, NEWLINE, LONG, FRAME, DUPLICATE, OFFLINE, NOT_AIR = "tcpip", "nogate", "query", "source", "own", "newline", "long", "frame", "duplicate", "offline", "not_air"
REASON_WORDS = {TCPIP: "TCPIP", NOGATE: "NOGATE", QUERY: "query", SOURCE: "bad source", OWN: "own", NEWLINE: "line break", LONG: "too long", FRAME: "bad frame", DUPLICATE: "duplicate", OFFLINE: "offline", NOT_AIR: "not from the air"}
"""Why a packet was not gated, in the words of the log and the page. `tcpip` also covers TCPXX, `nogate` also RFONLY, `source` a source that is no station and `frame` a frame that is no UI frame or whose
header is not one, `offline` the packets heard while the connection was down, `not_air` a packet that was not heard on the radio (from the internet, or made up by the Dummy radio: `Packet.via` is not in `packet.GATEABLE`)."""


@dataclass(frozen=True, slots=True)
class Gate:
    """A packet as it goes to APRS-IS before the q construct: the header as heard and the information field as bytes."""
    source: str
    destination: str
    path: str
    info: bytes

    def line(self, igate_call: str) -> bytes:
        """`SOURCE>DEST,PATH,qAO,IGATECALL:INFO`, with no line end."""
        path = f",{self.path}" if self.path else ""
        return f"{self.source}>{self.destination}{path},{Q_CONSTRUCT},{igate_call}:".encode("ascii") + self.info

    @property
    def key(self) -> DuplicateKey:
        """What makes two copies of a packet the same one (packet.duplicate_key)."""
        return duplicate_key(self.source, self.destination, self.info)


@dataclass(frozen=True, slots=True)
class Dropped:
    reason: str


def element_names(path: list[str]) -> set[str]:
    """The calls of path elements, without the star and the SSID, in capitals."""
    return {element.rstrip("*").partition("-")[0].upper() for element in path}


def _header_reason(path: list[str]) -> str | None:
    names = element_names(path)
    if names & INTERNET_MARKERS:
        return TCPIP
    if names & NO_GATE_MARKERS:
        return NOGATE
    if any(_never_on_air(element) for element in path) or any(_PATH_ELEMENT.fullmatch(element) is None for element in path):
        return FRAME
    return None


def _never_on_air(element: str) -> bool:
    """Whether a path element is a q construct or the `,I` construct, in any case (an AX.25 address is written in capitals): neither belongs on the air."""
    return is_q_construct(element) or element.upper() == "I"


def source_is_station(name: str) -> bool:
    """Whether a source can be a station on APRS-IS: a call or a name APRS-IS allows (`OH2XYZ-L`), none of the placeholders and aliases."""
    try:
        base = normal_name(name).partition("-")[0]
    except CallsignError:
        return False
    return base not in PLACEHOLDER_CALLS and not base.startswith(ALIASES)


def gate_of(frame: ax25.Frame, ours: str) -> Gate | Dropped:
    """The packet to put on APRS-IS for a frame heard on the radio, or why none (`Dropped.reason`). `ours` is the call of the iGate, as the login writes it."""
    if not frame.is_ui:
        return Dropped(FRAME)
    source, destination, path = str(frame.source), str(frame.destination), [str(hop) for hop in frame.path]
    path_text, info = frame.path_text, frame.info
    for _ in range(MAX_UNWRAP + 1):
        if (reason := _header_reason(path)) is not None:
            return Dropped(reason)
        if info[:1] != MARK:
            break
        opened = header_of(info)
        if opened is None:
            return Dropped(FRAME)
        third, info = opened
        source, destination, path = third.source, third.destination, list(third.path)
        path_text = ",".join(path)
    else:
        return Dropped(FRAME)
    return _checked(Gate(source, destination, path_text, info.rstrip(b"\r\n")), ours)


def _checked(gate: Gate, ours: str) -> Gate | Dropped:
    if not gate.info:
        return Dropped(FRAME)
    if gate.info[:1] == b"?":
        return Dropped(QUERY)
    if not source_is_station(gate.source):
        return Dropped(SOURCE)
    if gate.source == ours:
        return Dropped(OWN)
    if b"\r" in gate.info or b"\n" in gate.info:
        return Dropped(NEWLINE)
    if len(gate.line(ours)) + 2 > MAX_LINE:
        return Dropped(LONG)
    return gate
