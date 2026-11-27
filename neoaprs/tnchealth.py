"""What a radio's line is as the page shows it: one state and one problem code, decided in one place.

`line_health` reads the line and the modem behind it; the radio's settings and the station's table
of resources add theirs in `radiohealth.py`. `takes_frames` and `why_unusable` say whether a frame may
go now, and why not.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from .clock import iso
from .coded import Param, Reason, code_of
from .source import CHECKING, Source, unusable_because
from .tncport import Modem
from .tncprofile import Profile
from .tncreader import Reader
from .tnctextreader import RX_ONLY

COMMAND_MODE = Reason("the TNC is in command mode (KISS ON is sent again)", "radio.command_mode")


# The reasons of a waiting modem shown while the line is connected: the radio looks connected and hears
# nothing. Any other reason shows only once the line is down too (a modem that ended takes its line with it).
DEAF_REASONS = frozenset({"receive_stalled"})


@dataclass(frozen=True)
class RadioHealth:
    state: Source.State
    # a problem code of the page (`radio.*`, `modem.*`), None when there is none
    code: str | None = None
    params: Mapping[str, Param] = field(default_factory=dict)


STOPPED = RadioHealth(Source.State.STOPPED)


class Line(Protocol):
    """What the decision reads of a line (the Tnc)."""

    @property
    def state(self) -> Source.State: ...
    @property
    def problem(self) -> str: ...
    @property
    def write_stuck(self) -> Reason | None: ...
    @property
    def entering_kiss(self) -> bool: ...
    @property
    def usable(self) -> bool: ...
    @property
    def searching(self) -> list[str]: ...
    @property
    def silent_since(self) -> datetime | None: ...
    @property
    def modem_in_use(self) -> Modem | None: ...
    def why_unusable(self) -> str: ...


def line_health(line: Line) -> RadioHealth:
    """Return the line's state and problem as the page shows them."""
    return RadioHealth(shown_state(line), *_problem(line))


def shown_state(line: Line) -> Source.State:
    """Return the line's state, `connecting` in KISS entry and `waiting` after a write timed out.

    A TNC is silent in KISS mode until it hears a packet, so usable counts as connected early.
    """
    if line.state is Source.State.CONNECTED and line.write_stuck is not None:
        return Source.State.WAITING
    if line.state is Source.State.CONNECTED and line.entering_kiss and not line.usable:
        return Source.State.CONNECTING
    return line.state


def _problem(line: Line) -> tuple[str | None, Mapping[str, Param]]:
    state, stuck, modem = line.state, line.write_stuck, line.modem_in_use
    # the write timeout is the problem while the line is open again, or waits after that very loss
    if stuck is not None and (
        state is Source.State.CONNECTED
        or (state is Source.State.WAITING and code_of(line.problem)[0] == "radio.write_timeout")
    ):
        return "radio.write_timeout", code_of(stuck)[1]
    if state is Source.State.CONNECTED:
        if modem is not None and not modem.test:
            if modem.state == "waiting" and modem.reason in DEAF_REASONS:
                return f"modem.{modem.reason}", {}
            if modem.deaf:
                return "modem.receive_deaf", {}
        return ("radio.text_lines", {}) if code_of(line.why_unusable())[0] == "radio.text_lines" else (None, {})
    if modem is not None and modem.test:
        return None, {}  # Tune or the keying test has the radio; the line is down meanwhile
    if modem is not None and modem.state == "waiting" and modem.reason:
        return f"modem.{modem.reason}", {}
    if state is Source.State.SILENT:
        return "radio.silent", {"since": iso(line.silent_since) or ""}
    if (why := code_of(line.problem))[0] == "radio.incoming_port":
        return why
    if line.searching:
        return "radio.searching", {}
    return "radio.not_connected", {}


class Sender(Protocol):
    """What the send decision reads of a line (the Tnc)."""

    profile: Profile
    confirmed: bool
    _reader: Reader

    @property
    def state(self) -> Source.State: ...
    def _held(self) -> str: ...


def takes_frames(line: Sender) -> bool:
    """Return whether a frame may go now: connected, checked, in KISS and settled, not held."""
    return (
        not line.profile.writes_nothing
        and line.state is Source.State.CONNECTED
        and line.confirmed
        and not line._reader.looking
        and not line._reader.command_mode_unanswered()
        and asyncio.get_running_loop().time() >= line._reader.settle_until
        and not line._held()
        and not line._reader.board_quiet()
    )


def why_unusable(line: Sender) -> str:
    """Return why a frame cannot go now."""
    connected = line.state is Source.State.CONNECTED
    if line.profile.framing == "text":
        return RX_ONLY
    if connected and not line.confirmed:
        return CHECKING
    if connected and line._reader.command_mode_unanswered():
        return COMMAND_MODE
    if connected and (quiet := line._reader.board_quiet() or line._held()):
        return quiet
    return unusable_because(line.state)
