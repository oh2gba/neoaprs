"""What the services see of the radios once there are any number of them (plan §2): `AirRadio`, one radio with its kind, its limits, what it is allowed, its counters and the operator's choices on it, and
`RadioPick`, the choice of a radio (by id, the enabled ones, the main radio, the station's, the one a packet came on, the email radio). `fit` is the one place that makes our frame for a radio: the path where the
radio may carry one, the comment cut to what it carries whole; `our_frame`, `fixed_prefix` and `fit_frame` are its parts (services/common.py and services/sender.py give them, and SendError, under their old
names), here so that every service may import this module and it imports none of theirs.

The registry of the app layer (neoaprs/radioregistry.py) satisfies `RadioPick` and its radios `AirRadio`, and the services take them; a test may still give an old shape (common.Radio, common.RadioSet), which common.as_pick reads as one. The members of both
Protocols are read-only, so that a plain attribute, a property and a frozen field all satisfy them, and `enabled` is a Sequence, so that a list of the registry's own radios does."""
import logging
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Protocol

from neoaprs import TOCALL, ax25
from neoaprs.callsign import CallsignError
from neoaprs.config import Config
from neoaprs.message import path_choice
from neoaprs.packet import Packet
from neoaprs.radiotype import Allowed, Kind, Limits, RadioId
from neoaprs.source import Source
from neoaprs.tncwatchdog import TncStats

log = logging.getLogger("neoaprs.radioset")

NO_RADIO = "there is no radio"           # the reason of every send while the main or the chosen radio is None (a fresh installation)
FRAME_ERRORS = (ax25.Ax25Error, CallsignError, ValueError)          # what `our_frame` raises for a call or a path that makes no frame
_EXTENSION = re.compile(rb"PHG\d{4}|RNG\d{4}|\d{3}/\d{3}|DFS\d{4}")        # a 7-byte data extension right after a position (spec chapter 7)
UNCOMPRESSED = 19                                                    # a position with its symbol: 8 + 1 + 9 + 1
COMPRESSED = 13


class SendError(ValueError):
    """The settings and the values make no frame."""


class AirRadio(Protocol):
    @property
    def id(self) -> RadioId: ...
    @property
    def kind(self) -> Kind: ...
    @property
    def name(self) -> str:
        """radiospec.log_name."""
        ...
    @property
    def limits(self) -> Limits: ...
    @property
    def allowed(self) -> Allowed: ...
    @property
    def stats(self) -> TncStats:
        """Its line's counters (the digipeater counts what it repeated and held on the radio)."""
        ...
    @property
    def state(self) -> Source.State: ...
    @property
    def usable(self) -> bool: ...
    @property
    def max_frame(self) -> int | None: ...
    def why_unusable(self) -> str: ...
    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool: ...
    def choice(self, key: str) -> Any:
        """The radio's own value of "beacon", "path" or "digipeat" (RadioSpec.value)."""
        ...


class RadioPick(Protocol):
    def get(self, id: RadioId) -> AirRadio | None: ...
    def enabled(self) -> Sequence[AirRadio]: ...
    @property
    def main(self) -> AirRadio | None: ...
    def for_station(self, call: str) -> AirRadio | None: ...
    def for_packet(self, packet: Packet) -> AirRadio | None: ...
    def email(self) -> AirRadio | None: ...


def our_frame(config: Config, path: tuple[str, ...], info: bytes) -> ax25.Frame:
    """Our frame with this information field: from `station/call` to the tocall by way of `path`. Raises one of FRAME_ERRORS, each caller says it in its own error."""
    return ax25.Frame(ax25.Address.parse(TOCALL), ax25.Address.parse(config.station_call), tuple(ax25.Address.parse(call) for call in path), info=info)


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


def path_on(radio: AirRadio, config: Config, path: tuple[str, ...] | None) -> tuple[str, ...]:
    """The digipeaters of our frame on the radio: none where it may carry none; else the path given, or (None) the radio's own "path" choice, which empty is the recommended path of the station's symbol and DIRECT none."""
    if not radio.allowed.paths:
        return ()
    if path is not None:
        return path
    chosen = path_choice(str(radio.choice("path")))
    return tuple(c for c in config.recommended_path.split(",") if c) if chosen is None else chosen


def fit(radio: AirRadio, config: Config, info: bytes, path: tuple[str, ...] | None) -> ax25.Frame:
    """Our frame with this information field for the radio (plan §2: the one fit function): from station/call by `path_on`, its comment cut to what the radio carries whole (said in the log). SendError when
    the settings and the values make no frame."""
    if len(info) > ax25.MAX_INFO:
        raise SendError(f"the information field is {len(info)} bytes, more than the {ax25.MAX_INFO} AX.25 allows")
    try:
        frame = our_frame(config, path_on(radio, config, path), info)
        fitted = fit_frame(frame, radio.max_frame)
    except FRAME_ERRORS as e:
        raise SendError(str(e)) from None
    if fitted is not frame:
        log.warning("%s: a frame of ours is %d bytes more than the radio carries (%d): its comment is cut: %s", radio.name, len(ax25.encode(frame)) - len(ax25.encode(fitted)), radio.max_frame, fitted.tnc2())
    return fitted
