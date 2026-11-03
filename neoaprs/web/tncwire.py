"""The radio on the wire: the topics `tnc` and `hf` (one value each, told whole at most four times a second), and the commands of the HF radio's Tune and keying test. Models like the rest of the protocol, listed in
`neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Message, _Model


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


class FrequencyRow(_Model):
    """A frequency the project suggests for the HF radio."""
    band: str = Field(description="the band, `40 m`")
    dial: str = Field(description="the dial with its mode, `7.0541 MHz USB`")


class ModemState(_Model):
    """The Mercury HF modem behind the line, while the radio type is Mercury: the program's state, whether it keys the radio now and whether its busy detector hears a signal."""
    state: Literal["stopped", "starting", "running", "waiting"] = Field(description="`starting`: the program was started (or a Mercury something else runs is not yet answering on its control port); `running`: its control port answers; `waiting`: it is not running, `problem` says why")
    problem: str = Field(description="why the modem is not running (not installed, stopped); empty while it runs")
    reason: Literal["", "not_installed", "stopped", "network", "no_port", "not_started", "sound_card"] = Field(description="why the modem is `waiting`, as a code the page puts in its own words in the language of the viewer (`problem` is the English of the log and is not shown): `not_installed` this installation carries no Mercury; `stopped` the program ended and is started again; `network` the program listens on the network and is not run; `no_port` no port was free for it; `not_started` the program could not be started or its configuration written; `sound_card` the program could not open its sound card and was ended, another is to be chosen; empty unless the state is `waiting`")
    mode: str = Field(description="the modem's mode, the same for every station: `DATAC3`")
    keyed: bool = Field(description="the modem keys the radio now: a frame is on the air (about four seconds), or the tune tone or the keying test is on")
    busy: bool = Field(description="another station's signal is on the channel: our frames wait. The daemon judges it from the modem's spectrum (a signal as wide as a frame; a step in the noise or a carrier is none) while it reads that, else it is the modem's own fixed-threshold detector")
    test: Literal["", "tune", "key"] = Field(description="`tune` while the tune tone is on (`hf_tune`), `key` during the keying test (`hf_key_test`); empty otherwise. Our frames wait while either is on")
    snr: float | None = Field(description="the signal-to-noise ratio of the latest frame decoded, in dB; null before one")
    frames_keyed: int = Field(ge=0, description="how many times the radio was keyed since the modem started")
    max_frame: int = Field(ge=1, description="the longest packet the modem carries whole, in bytes (123): a longer message is refused, a longer beacon has its comment cut")
    sound_card: str = Field(description="the sound card the modem runs with (`mercury/sound_card`, or the daemon's choice while that is empty); empty for the system's default device")
    frequencies: list[FrequencyRow] = Field(max_length=3, description="the frequencies the project suggests, one to three: the list of the project's file (site/frequencies.json, asked a minute after the start and when a page sends `hf_frequencies`), else the dial the version page names, else the built-in "
                                                                       "two; the page shows them in the HF radio's box as they are, with the words \"suggested\": they are not read from the radio")
    keying: str = Field(description="how it keys the radio (`mercury/keying`, or the daemon's choice while that is empty): `vox`, `cm108`, `rts:PORT` or `dtr:PORT`")
    scope: bool = Field(description="the daemon reads the modem's UI interface: the spectrum scope can be shown (`hf_scope`) and the transmit gain is set live; false for a modem without the interface (the page shows no scope, and a change of the gain restarts the modem)")
    tx_gain_db: int = Field(ge=-20, le=20, description="the transmit gain the modem runs with, in dB (`mercury/tx_gain_db`); the tune tone follows it")
    tx_peak_dbfs: int | None = Field(description="the peak of the latest transmission (a frame, or the tune tone) in whole dBFS, as the modem says it; 0 or more clips in the sound card; null before one, and while the interface is not read")


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


class HfTune(_Command):
    """Tune: with `on`, keys the HF radio through the keying in use and sends a steady tone (1000 Hz, Mercury's own TUNE) through its sound card for ten seconds, then stops by itself; with `on` false, stops it early.
    For tuning the antenna, setting the audio level and finding which sound device is the radio. The topic `hf` says `test: "tune"` meanwhile and our frames wait. Answered with an `error` while RX only is ticked
    (`transmit.off`), while the HF radio is not the Mercury modem running (`hf.not_running`) and while a frame is on the air or the channel is busy (`hf.held`)."""
    cmd: Literal["hf_tune"]
    on: bool = Field(description="true starts the tone, false stops it")


class HfFrequencies(_Command):
    """The page shows the HF radio's box (the Mercury type): the daemon asks the project's server for the suggested frequencies again, unless it asked less than 15 minutes ago or the update check is off (`NEOAPRS_UPDATE_CHECK=0`). Nothing is
    answered; the topic `hf` has the list when it changes."""
    cmd: Literal["hf_frequencies"]


class HfScope(_Command):
    """The scope: with `on`, this page is sent `hf_scope` messages (five a second at most) of the spectrum of the HF radio's audio, and with `on` false,
    or when the page closes, the page is sent no more. Nothing happens, and no error is told, while the modem is not running or has no interface (the topic `hf` says
    `modem.scope`)."""
    cmd: Literal["hf_scope"]
    on: bool = Field(description="true starts the pictures for this page, false stops them")


class HfScopeMsg(_Message):
    """One picture of the HF radio's audio, told to the pages that asked for it (`hf_scope`), five a second at most: the spectrum of the passband in 48 bins of 50 Hz from 300 to 2700 Hz, the bins' level over the quiet floor
    of the band, and the level of the passband. The frame's signal band is 1200 to 1800 Hz (bins 18 to 29)."""
    type: Literal["hf_scope"]
    bins: list[int] = Field(min_length=48, max_length=48, description="the level of each 50 Hz bin over the band's quiet floor, whole dB, 0 to 60, the first bin 300 to 350 Hz")
    level: int = Field(ge=-90, le=0, description="the RMS level of the audio in the passband, whole dBFS, -90 for silence (a full-scale sine reads -3)")
    tx: bool = Field(description="the radio is transmitting: the picture is of our own signal (the tune tone shows as a line at 1000 Hz), and the level is of that")


class HfKeyTest(_Command):
    """The keying test: keys the HF radio for one second, so that the operator sees it go to transmit and come back: with next to no audio (Mercury's TUNE at its quietest level) where the keying is a line (RTS, DTR, CM108), with the tune tone where the radio keys on audio (VOX); the topic `hf` says
    `test: "key"` meanwhile. The same refusals as `hf_tune`."""
    cmd: Literal["hf_key_test"]
