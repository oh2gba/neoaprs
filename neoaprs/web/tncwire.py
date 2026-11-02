"""The radio on the wire: the topic `tnc` (one value, told whole at most four times a second) and the command to open the line again. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Model


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
    digipeated_at: Iso | None = Field(description="when the latest of them went out; null for none yet")
    digipeat_held: int = Field(ge=0, description="frames the digipeater left unsent because it had already sent the most it sends in a burst (`BURST_MAX` in 10 seconds)")


class TncLine(_Model):
    """One line of the TNC's log."""
    at: Iso = Field(description="when the line was written")
    text: str = Field(description="what the TNC saw (TNC2 text and what it understood of it) or did (`NeoAPRS: ...`), without the time")


class ModemState(_Model):
    """The Mercury HF modem behind the line, while the radio type is Mercury: the program's state, whether it keys the radio now and whether its busy detector hears a signal."""
    state: Literal["stopped", "starting", "running", "waiting"] = Field(description="`starting`: the program was started (or a Mercury something else runs is not yet answering on its control port); `running`: its control port answers; `waiting`: it is not running, `problem` says why")
    problem: str = Field(description="why the modem is not running (not installed, stopped); empty while it runs")
    mode: str = Field(description="the modem's mode, the same for every station: `DATAC3`")
    keyed: bool = Field(description="the modem keys the radio now: a frame is on the air (about four seconds)")
    busy: bool = Field(description="the modem's busy detector hears a signal on the channel: our frames wait")
    snr: float | None = Field(description="the signal-to-noise ratio of the latest frame decoded, in dB; null before one")
    frames_keyed: int = Field(ge=0, description="how many times the radio was keyed since the modem started")
    max_frame: int = Field(ge=1, description="the longest packet the modem carries whole, in bytes (123): a longer message is refused, a longer beacon has its comment cut")
    sound_card: str = Field(description="the sound card the modem runs with (`mercury/sound_card`, or the daemon's choice while that is empty); empty for the system's default device")
    keying: str = Field(description="how it keys the radio (`mercury/keying`, or the daemon's choice while that is empty): `vox`, `cm108`, `rts:PORT` or `dtr:PORT`")


class RadioRulesState(_Model):
    """What the kind of the radio in use allows (neoaprs/radiorules.py): the page shows the path, the digipeater and the moving-station controls only where they apply."""
    kind: Literal["fm", "hf"] = Field(description="`fm` is the local radio (the KISS TNC), `hf` the Mercury HF modem")
    paths: bool = Field(description="whether a frame of ours carries digipeaters; false: every frame goes direct whatever `beacon/path` and the stations' paths say, and the path controls are not shown")
    digipeat: bool = Field(description="whether the fill-in digipeater can repeat what this radio hears; false: the Digipeater group is not shown and nothing is repeated")
    smart_beacon: bool = Field(description="whether a moving station's SmartBeaconing and the GPS apply; false: the timed beacon of a fixed station only, and the GPS source is not shown")
    beacon_min_min: int = Field(ge=1, description="the shortest beacon interval the radio takes, in minutes")


class TncState(_Model):
    """The TNC, the one feed of packets: its state and why it is not connected, the port, and the latest lines of what it saw and did. The value of the topic `tnc`."""
    state: Literal["stopped", "connecting", "connected", "waiting", "silent"] = Field(
        description="`waiting` is between two attempts to open the line; `problem` says why. `silent`: the line is open and the radio does not answer (a check of the keep-alive got no byte at all in answer); nothing is sent until it does")
    problem: str = Field(description="why it is not (yet) connected or not sending KISS; empty when all is well")
    last_error: str = Field(description="the latest reason for waiting")
    path: str = Field(description="the serial port in use; empty while none is open")
    baud: int
    dummy: bool = Field(description="the radio is the Dummy radio: the traffic is made up and nothing goes on the air; `path` and `baud` mean nothing then")
    modem: ModemState | None = Field(description="the Mercury HF modem behind the line while the radio type is Mercury; null for every other radio type")
    rules: RadioRulesState = Field(description="what the kind of the radio in use allows: the page shows only the controls that apply")
    describe: str = Field(description="one line for the log and `neoaprs doctor`: the port, the speed and what the TNC does; while `silent` it says since when, in UTC")
    searching: list[str] = Field(description="the ports the daemon is listening to while it looks for the radio; empty when it is not searching")
    silent_since: Iso | None = Field(description="while `state` is `silent`, when the latest byte came; null otherwise")
    stats: TncStats
    last_watchdog_action: Literal["", "check", "probe", "reopen"] = Field(
        description="what the watchdog did last: `check` (the radio asked whether it is there, after a quiet period), `probe` (the same, while the radio is silent) or `reopen` (the port closed and opened again); empty if it has done nothing since the daemon started")
    last_watchdog_at: Iso | None = Field(description="when the watchdog did that; null if it has done nothing since the daemon started")
    lines: list[TncLine] = Field(max_length=100, description="the latest 100 lines of what the TNC saw and did, oldest first")
