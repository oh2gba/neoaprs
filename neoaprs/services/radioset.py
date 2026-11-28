"""What the services see of the radios: `AirRadio`, `RadioPick`, and fitting a frame to a radio.

`fit` is the one place that makes our frame for a radio. These live here so every service may
import this module while it imports none of theirs.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Protocol

from neoaprs import TOCALL, ax25, kiss
from neoaprs.callsign import CallsignError
from neoaprs.coded import Reason
from neoaprs.config import Config
from neoaprs.message import EMAIL_GATEWAY, path_choice, same_call
from neoaprs.packet import Packet
from neoaprs.radiotype import Allowed, Kind, Limits, RadioId
from neoaprs.radiotypes import recommended_path
from neoaprs.route import RF_ONLY
from neoaprs.tnc2line import text_of
from neoaprs.source import Source
from neoaprs.tncwatchdog import TncStats

log = logging.getLogger("neoaprs.radioset")

NO_RADIO = Reason("there is no radio", "radio.none")
FRAME_ERRORS = (ax25.Ax25Error, CallsignError, ValueError)
# a 7-byte data extension after a position (spec chapter 7)
_EXTENSION = re.compile(rb"PHG\d{4}|RNG\d{4}|\d{3}/\d{3}|DFS\d{4}")
UNCOMPRESSED = 19
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
        """The line's counters."""
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
    def senders(self) -> Sequence[AirRadio]:
        """The enabled radios that can send, by position: a receive-only radio is never one."""
        ...

    def for_station(self, call: str) -> AirRadio | None: ...
    def for_packet(self, packet: Packet) -> AirRadio | None: ...
    def email(self) -> AirRadio | None: ...


def our_frame(config: Config, path: tuple[str, ...], info: bytes) -> ax25.Frame:
    """Return our frame to the tocall via `path`; raise one of FRAME_ERRORS."""
    return ax25.Frame(
        ax25.Address.parse(TOCALL),
        ax25.Address.parse(config.station_call),
        tuple(ax25.Address.parse(call) for call in path),
        info=info,
    )


def fixed_prefix(info: bytes) -> int:
    """Return how many leading bytes of an information field are the report, never cut."""
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
    position = UNCOMPRESSED if info[body : body + 1].isdigit() else COMPRESSED
    end = body + position
    if _EXTENSION.match(info[end : end + 7]):
        end += 7
    return min(len(info), end)


def fit_frame(
    frame: ax25.Frame, max_frame: int | None, max_text: int | None = None, max_kiss: int | None = None
) -> ax25.Frame:
    """Return the frame with its information cut from the end to fit the limits.

    Raise ValueError if it is too long even without its comment."""
    overs = [(len(ax25.encode(frame)) - max_frame, max_frame, "")] if max_frame is not None else []
    overs += [(len(text_of(frame)) - max_text, max_text, " of text")] if max_text is not None else []
    overs += [(len(kiss.encode(ax25.encode(frame))) - max_kiss, max_kiss, " in KISS")] if max_kiss is not None else []
    over, limit, what = max(overs, default=(0, 0, ""))
    if over <= 0:
        return frame
    keep = fixed_prefix(frame.info)
    if len(frame.info) - over < keep:
        raise ValueError(
            f"the frame is {over} bytes over the {limit}{what} the radio carries, and shortening its comment is not enough"
        )
    return replace(frame, info=frame.info[: len(frame.info) - over])


def path_on(radio: AirRadio, config: Config, path: tuple[str, ...] | None, *, rf_only: bool = False) -> tuple[str, ...]:
    """Return the path of our frame on the radio: the given path, or its default.

    A radio that carries no path gets none, or RFONLY alone with `rf_only`."""
    if not radio.allowed.paths:
        return (RF_ONLY,) if rf_only else ()
    if path is not None:
        return path
    chosen = path_choice(str(radio.choice("path")))
    return (
        tuple(c for c in (recommended_path(radio.kind) or config.recommended_path).split(",") if c)
        if chosen is None
        else chosen
    )


def reply_path_on(radio: AirRadio, config: Config, path: tuple[str, ...] | None) -> tuple[str, ...]:
    """Return the digipeaters of a message or ack; a radio without paths gets the given path."""
    return path_on(radio, config, path) if radio.allowed.paths else path or ()


def fit(radio: AirRadio, config: Config, info: bytes, path: tuple[str, ...] | None) -> ax25.Frame:
    """Return our frame for the radio, comment cut to fit; raise SendError if none can be made."""
    if len(info) > ax25.MAX_INFO:
        raise SendError(f"the information field is {len(info)} bytes, more than the {ax25.MAX_INFO} AX.25 allows")
    try:
        frame = our_frame(config, path_on(radio, config, path), info)
        fitted = fit_frame(frame, radio.max_frame, radio.limits.max_text, radio.limits.max_kiss)
    except FRAME_ERRORS as e:
        raise SendError(str(e)) from None
    if fitted is not frame:
        log.warning(
            "%s: a frame of ours is %d bytes more than the radio carries (%d): its comment is cut: %s",
            radio.name,
            len(ax25.encode(frame)) - len(ax25.encode(fitted)),
            radio.max_frame,
            fitted.tnc2(),
        )
    return fitted


def first_sender(pick: RadioPick) -> AirRadio | None:
    """Return the first radio that can send, else None."""
    return next(iter(pick.senders()), None)


def sends(pick: RadioPick, radio: AirRadio) -> bool:
    """Return whether the radio is enabled and of a type that can transmit."""
    return any(r.id == radio.id for r in pick.senders())


def ack_radio(pick: RadioPick, packet: Packet, call: str) -> AirRadio | None:
    """Return the radio an ack goes out on, or None if no radio can send.

    Without a sending radio it came on, use the station's radio so the sender stops repeating."""
    came = pick.for_packet(packet)
    if came is not None and sends(pick, came):
        return came
    return pick.email() if same_call(call, EMAIL_GATEWAY) else pick.for_station(call)


def answerable(pick: RadioPick, packet: Packet) -> bool:
    """Return whether a question heard on the air is taken: only on a radio that sends."""
    came = pick.for_packet(packet)
    if came is not None and sends(pick, came):
        return True
    log.debug(
        "a query of %s is not answered: heard on %s",
        packet.sender,
        "a radio that is no longer on" if came is None else f"{came.name}, a radio that sends nothing",
    )
    return False
