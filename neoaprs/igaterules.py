"""What a receive-only iGate puts on APRS-IS: which heard frames go, and the line each becomes.

Pure code; services/igate.py keeps duplicates, counts and the connection. The path is kept as
heard with `,qAO,IGATECALL` appended (aprs-is.net IGate details)."""

import re
from dataclasses import dataclass

from neoaprs import ax25
from neoaprs.aprsisline import MAX_LINE
from neoaprs.aprsthirdparty import MARK, header_of
from neoaprs.callsign import PLACEHOLDER_CALLS, CallsignError, normal_name
from neoaprs.packet import DuplicateKey, duplicate_key
from neoaprs.route import INTERNET_MARKERS, NO_GATE_MARKERS, is_q_construct

Q_CONSTRUCT = "qAO"
MAX_UNWRAP = 3  # nested third-party wrappers; a deeper one is no packet
# sources that are no station
ALIASES = ("WIDE", "TRACE", "RELAY", "TCP", "NOGATE", "RFONLY", "SERVER", "BEACON")
# an element of a path on the air (stricter than callsign.PATH_ELEMENT)
_PATH_ELEMENT = re.compile(r"[A-Za-z0-9]{1,9}(?:-[A-Za-z0-9]{1,2})?\*?")

TCPIP, NOGATE, QUERY, SOURCE, OWN, NEWLINE, LONG, FRAME, DUPLICATE, OFFLINE, NOT_AIR = (
    "tcpip",
    "nogate",
    "query",
    "source",
    "own",
    "newline",
    "long",
    "frame",
    "duplicate",
    "offline",
    "not_air",
)
REASON_WORDS = {
    TCPIP: "TCPIP",
    NOGATE: "NOGATE",
    QUERY: "query",
    SOURCE: "bad source",
    OWN: "own",
    NEWLINE: "line break",
    LONG: "too long",
    FRAME: "bad frame",
    DUPLICATE: "duplicate",
    OFFLINE: "offline",
    NOT_AIR: "not from the air",
}
# why a packet was not gated


@dataclass(frozen=True, slots=True)
class Gate:
    """A packet as it goes to APRS-IS before the q construct."""

    source: str
    destination: str
    path: str
    info: bytes

    def line(self, igate_call: str) -> bytes:
        """Return `SOURCE>DEST,PATH,qAO,IGATECALL:INFO`."""
        path = f",{self.path}" if self.path else ""
        return f"{self.source}>{self.destination}{path},{Q_CONSTRUCT},{igate_call}:".encode("ascii") + self.info

    @property
    def key(self) -> DuplicateKey:
        """Return what makes two copies the same packet."""
        return duplicate_key(self.source, self.destination, self.info)


@dataclass(frozen=True, slots=True)
class Dropped:
    reason: str


def element_names(path: list[str]) -> set[str]:
    """Return the calls of path elements, without star and SSID."""
    return {element.rstrip("*").partition("-")[0].upper() for element in path}


def _header_reason(path: list[str]) -> str | None:
    names = element_names(path)
    if names & INTERNET_MARKERS:
        return TCPIP
    if names & NO_GATE_MARKERS:
        return NOGATE
    if any(_never_on_air(element) for element in path) or any(
        _PATH_ELEMENT.fullmatch(element) is None for element in path
    ):
        return FRAME
    return None


def _never_on_air(element: str) -> bool:
    """Return whether a path element is a q or `,I` construct, which never belong on the air."""
    return is_q_construct(element) or element.upper() == "I"


def source_is_station(name: str) -> bool:
    """Return whether a source can be a station on APRS-IS."""
    try:
        base = normal_name(name).partition("-")[0]
    except CallsignError:
        return False
    return base not in PLACEHOLDER_CALLS and not base.startswith(ALIASES)


def gate_of(frame: ax25.Frame, ours: str) -> Gate | Dropped:
    """Return the packet for a frame heard on the radio, or why none; `ours` is the iGate's call."""
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
