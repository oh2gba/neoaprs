"""What the services that send share: `Radio` (what they need of the Tnc), `RadioSet` (the two radios as one, with the choice by station, by packet and by kind: `radio_to`, `radio_for`, `radios_on`), `ConfigSource` (how they read
the settings), `transmit_refusal` and `our_call` (why nothing may be sent, and the call we may send under), `our_frame` (our frame to the tocall), `radio_path` (the path a frame goes by on the radio: none on HF) and `fit_frame` (the frame
shortened to what a radio with a fixed frame carries: the Mercury HF modem's 123 bytes). The rule every service follows: a frame is built for, gated by and sent on *its* radio, the one the station is reached on or the one the request
came on, never "the radio" of a station that has two."""
import re
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol, runtime_checkable

from neoaprs import TOCALL, ax25
from neoaprs.callsign import CallsignError
from neoaprs.coded import CodedError
from neoaprs.config import Config, can_transmit
from neoaprs.message import EMAIL_GATEWAY, MessagingError
from neoaprs.packet import Packet
from neoaprs.radiorules import RadioRules
from neoaprs.source import Source

ConfigSource = Callable[[], Config]
FRAME_ERRORS = (ax25.Ax25Error, CallsignError, ValueError)          # what `our_frame` raises for a call or a path that makes no frame
_EXTENSION = re.compile(rb"PHG\d{4}|RNG\d{4}|\d{3}/\d{3}|DFS\d{4}")        # a 7-byte data extension right after a position (spec chapter 7)
UNCOMPRESSED = 19                                                    # a position with its symbol: 8 + 1 + 9 + 1
COMPRESSED = 13


class Radio(Protocol):
    """What the services need of the Tnc."""
    @property
    def state(self) -> Source.State: ...
    @property
    def usable(self) -> bool: ...
    @property
    def max_frame(self) -> int | None: ...
    @property
    def rules(self) -> RadioRules: ...
    def why_unusable(self) -> str: ...
    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool: ...


@runtime_checkable
class RadioSet(Radio, Protocol):
    """The radios of the station as a service that answers stations sees them (neoaprs/radios.py): itself the default radio (FM while it is on, else HF), and the choice of the radio a station is reached on, or
    the one a packet came on. A service that never chooses takes a plain Radio."""
    def for_station(self, call: str) -> Radio: ...
    def for_packet(self, packet: Packet) -> Radio: ...
    def of(self, kind: str) -> Radio | None: ...
    @property
    def on(self) -> list[Radio]: ...


def radios_on(radio: Radio) -> list[Radio]:
    """The radios that are on, each to be asked on its own (a gate that asks "the radio" asks the FM one while it is on, and holds what goes over HF when the FM radio is silent at night): the radios of the set that are
    enabled, or the one radio the service was given (a test's stub)."""
    return radio.on if isinstance(radio, RadioSet) else [radio]


def radio_for(radio: Radio, packet: Packet) -> Radio:
    """The radio to answer the packet on: the one it came on when the service was given the radios, else the one radio it was given (a test's stub)."""
    return radio.for_packet(packet) if isinstance(radio, RadioSet) else radio


def radio_to(radio: Radio, call: str) -> Radio:
    """The radio a frame of ours to the station goes out on: by the station when the service was given the radios, else the one radio it was given."""
    return radio.for_station(call) if isinstance(radio, RadioSet) else radio


def message_radio(radio: Radio, to: str) -> Radio:
    """The radio a message of ours to the station goes out on: the station's (`radio_to`); the FM radio for the email gateway, which is a station of the internet reached through the iGates of the VHF network and never
    over HF, so a mail is refused (MessagingError, the code `message.email_fm_off`) while the FM radio is off."""
    if to == EMAIL_GATEWAY and isinstance(radio, RadioSet):
        fm = radio.of("fm")
        if fm is None:
            raise MessagingError("email goes out over the FM radio, which is off", "message.email_fm_off")
        return fm
    return radio_to(radio, to)


def our_frame(config: Config, path: tuple[str, ...], info: bytes) -> ax25.Frame:
    """Our frame with this information field: from `station/call` to the tocall by way of `path`. Raises one of FRAME_ERRORS, each caller says it in its own error."""
    return ax25.Frame(ax25.Address.parse(TOCALL), ax25.Address.parse(config.station_call), tuple(ax25.Address.parse(call) for call in path), info=info)


def radio_path(radio: Radio, path: tuple[str, ...]) -> tuple[str, ...]:
    """The digipeaters a frame of ours goes by on this radio: the path given where the network has digipeaters (FM), none where every frame is direct (HF: the settings and the stations' own paths are kept for the day the operator is back on VHF, and a path would only cost bytes of the frame)."""
    return path if radio.rules.paths else ()


def fixed_prefix(info: bytes) -> int:
    """How many bytes at the start of an information field are the report itself, which a cut must not touch; what follows is its comment. A position (`!`, `=`, `/`, `@` with its time), an object (`;`) or an item (`)`)
    with the position, uncompressed or compressed, and a data extension after it (PHG, RNG, course and speed, DFS); a status (`>`) with its time; a message (`:`) with its addressee; anything else whole, so that it is never cut."""
    kind = info[:1]
    if kind in (b"!", b"="):
        body = 1
    elif kind in (b"/", b"@"):
        body = 8
    elif kind == b";":
        body = 18
    elif kind == b")":
        marks = [i for i in (info.find(b"!", 1), info.find(b"_", 1)) if i > 0]
        if not marks:
            return len(info)
        body = min(marks) + 1
    elif kind == b":":
        return min(len(info), 11)
    elif kind == b">":
        return min(len(info), 8 if re.match(rb">\d{6}z", info) else 1)
    else:
        return len(info)
    position = UNCOMPRESSED if info[body:body + 1].isdigit() else COMPRESSED
    end = body + position
    if _EXTENSION.match(info[end:end + 7]):
        end += 7
    return min(len(info), end)


def fit_frame(frame: ax25.Frame, max_frame: int | None) -> ax25.Frame:
    """The frame, with its information field cut from the end so that the radio carries it whole, as it is when it fits or there is no limit. The report itself (`fixed_prefix`) is never cut: ValueError when the frame
    would still be too long without any of its comment."""
    if max_frame is None:
        return frame
    over = len(ax25.encode(frame)) - max_frame
    if over <= 0:
        return frame
    keep = fixed_prefix(frame.info)
    if len(frame.info) - over < keep:
        raise ValueError(f"the frame is {over} bytes over the {max_frame} the radio carries, and shortening its comment is not enough")
    return replace(frame, info=frame.info[:len(frame.info) - over])


RX_ONLY = "RX only: nothing is sent"                                # what a refusal to the page says while station/transmit is off (its code is `transmit.off`)


def transmit_refusal(config: Config, error: type[CodedError] = CodedError) -> CodedError | None:
    """Why nothing may be sent now, as an error of the class given (not raised): receive only (the code `transmit.off`), or the interlock's reason (no call); None when we may send."""
    if not config.station_transmit:
        return error(RX_ONLY, "transmit.off")
    if reason := can_transmit(config):
        return error(reason)
    return None


def our_call(config: Config) -> str:
    """The call we send under; raises MessagingError when nothing may be transmitted (transmit_refusal)."""
    if refusal := transmit_refusal(config, MessagingError):
        raise refusal
    return config.station_call
