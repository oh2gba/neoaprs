"""The radio on the wire: the topic `tnc` (one value, told whole at most four times a second) and the command to open the line again. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Model


class TncStats(_Model):
    """What the TNC has counted since the daemon started."""
    opens: int = Field(description="times the line was opened")
    bytes_in: int
    bytes_out: int
    frames_in: int = Field(description="frames received, including the ones that could not be read as a packet")
    packets: int = Field(description="packets handed on")
    rejected: int = Field(description="frames that could not be read as a packet")
    last_packet: Iso | None = Field(description="when the latest packet was heard; null for none yet")
    keepalive_checks: int = Field(ge=0, description="times the keep-alive checked that the radio is there (after 60 seconds of nothing heard)")
    watchdog_probes: int = Field(ge=0, description="times the watchdog probed a silent radio (the same sequence as a check, every 30 seconds)")
    port_reopens: int = Field(ge=0, description="times the port was closed and opened again (every 5th probe of a silent radio)")
    digipeated: int = Field(ge=0, description="frames the digipeater (`digi/enabled`) sent again for other stations")


class TncLine(_Model):
    """One line of the TNC's log."""
    at: Iso = Field(description="when the line was written")
    text: str = Field(description="what the TNC saw (TNC2 text and what it understood of it) or did (`NeoAPRS: ...`), without the time")


class TncState(_Model):
    """The TNC, the one feed of packets: its state and why it is not connected, the port, and the latest lines of what it saw and did. The value of the topic `tnc`."""
    state: Literal["stopped", "connecting", "connected", "waiting", "silent"] = Field(
        description="`waiting` is between two attempts to open the line; `problem` says why. `silent`: the line is open and the radio does not answer (a check of the keep-alive got no byte at all in answer); nothing is sent until it does")
    problem: str = Field(description="why it is not (yet) connected or not sending KISS; empty when all is well")
    last_error: str = Field(description="the latest reason for waiting")
    path: str = Field(description="the serial port in use; empty while none is open")
    baud: int
    describe: str = Field(description="one line for the log and `neoaprs doctor`: the port, the speed and what the TNC does; while `silent` it says since when, in UTC")
    searching: list[str] = Field(description="the ports the daemon is listening to while it looks for the radio; empty when it is not searching")
    silent_since: Iso | None = Field(description="while `state` is `silent`, when the latest byte came; null otherwise")
    stats: TncStats
    last_watchdog_action: Literal["", "check", "probe", "reopen"] = Field(
        description="what the watchdog did last: `check` (the radio asked whether it is there, after a quiet period), `probe` (the same, while the radio is silent) or `reopen` (the port closed and opened again); empty if it has done nothing since the daemon started")
    last_watchdog_at: Iso | None = Field(description="when the watchdog did that; null if it has done nothing since the daemon started")
    lines: list[TncLine] = Field(max_length=100, description="the latest 100 lines of what the TNC saw and did, oldest first")


class TncReconnect(_Command):
    """Opens the radio's line again with the settings as they are now (the port, the speed, entering KISS): the TNC is stopped and started in the background. The new state is told in `tnc`."""
    cmd: Literal["tnc_reconnect"]
