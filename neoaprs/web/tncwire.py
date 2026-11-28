"""Wire models of the topic `radios` and the suggested frequencies."""

from typing import Any, Literal

from pydantic import Field

from neoaprs.tncwatchdog import TncStats as LineStats
from neoaprs.versions import MAX_FREQUENCIES

from .wirebase import Iso, _Command, _Model


class PassStats(_Model):
    """What the pairs of radios passed onto this radio from one other radio since the daemon started."""

    heard_on: int = Field(ge=1, description="the radio the packets were heard on, by its id")
    sent: int = Field(ge=0, description="frames sent on this radio")
    sent_at: Iso | None = Field(description="when the latest of them went out; null for none yet")
    held: int = Field(
        ge=0,
        description="frames left unsent by this radio's limits: the burst on a fast radio; the budget, its share for packets other than messages and acks, a station's share of messages, the 30-minute floor, a frame already waiting, or a keyed or busy channel past 30 s on a slow one",
    )
    too_long: int = Field(ge=0, description="frames left unsent because they are longer than this radio carries")


class TncStats(_Model):
    """What the TNC has counted since the daemon started."""

    opens: int = Field(description="times the line was opened")
    bytes_in: int
    bytes_out: int
    frames_in: int = Field(description="frames received, including the ones that could not be read as a packet")
    packets: int = Field(description="packets handed on")
    rejected: int = Field(description="frames that could not be read as a packet")
    last_packet: Iso | None = Field(description="when the latest packet was heard; null for none yet")
    keepalive_checks: int = Field(
        ge=0, description="times the keep-alive checked that the radio is there (after 60 seconds of nothing heard)"
    )
    watchdog_probes: int = Field(
        ge=0, description="times the watchdog probed a silent radio (the same sequence as a check, every 30 seconds)"
    )
    port_reopens: int = Field(
        ge=0, description="times the port was closed and opened again (every 5th probe of a silent radio)"
    )
    digipeated: int = Field(
        ge=0,
        description="frames the digipeater sent again for other stations on this radio, the pairs' passed frames among them",
    )
    digipeated_at: Iso | None = Field(description="when the latest of them went out; null for none yet")
    digipeat_held: int = Field(
        ge=0,
        description="frames the digipeater left unsent because it had already sent the most it sends in a burst (`BURST_MAX` in 10 seconds)",
    )
    passed: list[PassStats] = Field(
        description="what the pairs passed onto this radio, one entry for each radio packets came from, in the order of its id; empty while none"
    )


def stats_row(stats: LineStats) -> dict[str, Any]:
    """The radio's counts for the wire, the pairs' by the radio heard on in the order of its id."""
    return TncStats.row(stats, passed=[PassStats.row(count, heard_on=id) for id, count in sorted(stats.passed.items())])


class TncLine(_Model):
    """One line of the TNC's log."""

    at: Iso = Field(description="when the line was written")
    text: str = Field(
        description="what the TNC saw (TNC2 text and what it understood of it) or did (`NeoAPRS: ...`), without the time"
    )


class FrequencyRow(_Model):
    """A frequency the project suggests for the HF radio."""

    band: str = Field(description="the band, `40 m`")
    dial: str = Field(description="the dial with its mode, `7.0541 MHz USB`")


class ModemState(_Model):
    """The modem program behind a radio's line, while its type is one the daemon starts a modem for (the Mercury modem, Direwolf on a sound card): the program's state, whether it keys the radio now and whether
    it hears a signal."""

    state: Literal["stopped", "starting", "running", "waiting"] = Field(
        description="`starting`: the program was started (or a Mercury something else runs is not yet answering on its control port); `running`: its control port answers; `waiting`: it is not running, `reason` says why"
    )
    reason: Literal[
        "",
        "not_installed",
        "stopped",
        "network",
        "no_port",
        "not_started",
        "sound_card",
        "keying",
        "keying_in_use",
        "keying_missing",
        "ports_taken",
        "receive_stalled",
    ] = Field(
        description="why the modem is `waiting`, as a code the page puts in its own words in the language of the viewer (the log has the English): `not_installed` this installation carries no such program; `stopped` the program ended and is started again; `network` the program listens on the network and is not run; `no_port` no port was free for it; `not_started` the program could not be started or its configuration written; `sound_card` the program could not open its sound card (or, on Windows, find it among the devices) and was ended, another is to be chosen; `keying` the program could not open its keying device (or, on Windows, found several CM108 chips) and was ended, another way of keying is to be chosen; `keying_in_use` its keying port is in use by another program (Mercury: Windows error 5, or the device is busy) and the program was ended; it is started again after a back-off for as long as the radio is on; `keying_missing` its keying port is not there and the program was ended, started again in the same way; `ports_taken` another program listens on the KISS or control port of the modem's pair (most likely a Mercury the operator started himself): no modem is started beside it, no line connects to it, and the start is tried again after a back-off; the radio's type `mercury-own` is the one for such a Mercury; `receive_stalled` the program heard nothing (its receive side stalled) again after three restarts in an hour and is not started again until the radio is; empty unless the state is `waiting`"
    )
    mode: str = Field(
        description="the modem's mode, the same for every station of the type: `DATAC3` (Mercury), `AFSK1200` (Direwolf)"
    )
    keyed: bool = Field(
        description="the modem keys the radio now: a frame is on the air (about four seconds), or the tune tone or the keying test is on"
    )
    busy: bool = Field(
        description="another station's signal is on the channel and our frames wait: for 20 s at most (`BUSY_HOLD_MAX_SEC`), after which it is false while the channel stays busy, since nothing waits any more. The daemon judges it from the modem's spectrum (a signal as wide as a frame; a step in the noise or a carrier is none) while it reads that, else it is the modem's own fixed-threshold detector"
    )
    test: Literal["", "tune", "key"] = Field(
        description="`tune` while the tune tone is on (`radio_tune`), `key` during the keying test (`radio_key_test`); empty otherwise. Our frames wait while either is on"
    )
    snr: float | None = Field(
        description="the signal-to-noise ratio of the latest frame decoded, in dB; null before one"
    )
    frames_keyed: int = Field(ge=0, description="how many times the radio was keyed since the modem started")
    max_frame: int | None = Field(
        ge=1,
        description="the longest packet the modem carries whole, in bytes (Mercury 123): a longer message is refused, a longer beacon has its comment cut; null for AX.25's own (Direwolf)",
    )
    sound_card: str = Field(
        description="the sound card the modem runs with (`mercury/sound_card`, or the daemon's choice while that is empty); empty for the system's default device"
    )
    frequencies: list[FrequencyRow] = Field(
        max_length=MAX_FREQUENCIES,
        description="the frequencies the project suggests, one to five, by band, the longest first: the list of the project's file (site/frequencies.json, asked a minute after the start and when a page sends `frequencies`), else the dial the version page names, else the built-in "
        'five; the page shows them in the Mercury radio\'s box as they are, with the words "suggested": they are not read from the radio',
    )
    keying: str = Field(
        description="how it keys the radio (`mercury/keying`, or the daemon's choice while that is empty): `vox`, `cm108`, `rts:PORT`, `dtr:PORT`, or through a rig program the operator runs, `flrig` or `rigctld`, each with `:HOST:PORT` after it unless it is this computer on the program's default port (12345, 4532)"
    )
    scope: bool = Field(
        description="the daemon reads the modem's UI interface: the spectrum scope can be shown (`radio_scope`) and the transmit gain is set live; false for a modem without the interface (the page shows no scope, and a change of the gain restarts the modem)"
    )
    tx_gain_db: int = Field(
        ge=-20,
        le=20,
        description="the transmit gain the modem runs with, in dB (`mercury/tx_gain_db`); the tune tone follows it",
    )
    tx_peak_dbfs: int | None = Field(
        description="the peak of the latest transmission (a frame, or the tune tone) in whole dBFS, as the modem says it; 0 or more clips in the sound card; null before one, and while the interface is not read"
    )
    rx_level: int | None = Field(
        ge=0,
        description="the receive level as it is now, on Direwolf's own scale (0 to about 200: about 50 for most stations, under 5 too low, over 110 too high; `LIMITS.sound_card` has the zones): said every two seconds and at each packet heard; null while its Direwolf does not run, and for a modem that has none",
    )


class Frequencies(_Command):
    """The page shows the station's suggested frequencies (the box of a radio whose type can show them, the HF tests tab): the daemon asks the project's server for them again, unless it asked less than 15 minutes ago or the
    update check is off (`NEOAPRS_UPDATE_CHECK=0`). The suggested dials are the project's, not a radio's: one list for the station. Nothing is answered; the topic `skeds` and each Mercury radio's `modem` have the list
    when it changes."""

    cmd: Literal["frequencies"]


class CardLevelsRow(_Model):
    """The radio's sound card's own levels (the radio's `tx_card` and `rx_card` set them): a slider is drawn only where the card has the control, at the card's level."""

    tx: int | None = Field(
        ge=0,
        le=100,
        description="the card's playback level in percent, what the radio is given to transmit (ALSA's Speaker, PCM or Master control; the playing device's master volume on Windows); null where the card has no such control, the radio has no sound card or its card was never read",
    )
    rx: int | None = Field(
        ge=0,
        le=100,
        description="the card's capture level in percent, what it takes from the radio (ALSA's Capture or Mic control; the recording device's master volume on Windows); null as `tx`",
    )
    read: bool = Field(
        description="the levels are the card's: its card was read in this run of the daemon, or there is nothing to wait for (this system has no mixer, the radio has no sound card of its own); false while an enabled radio's card was not read yet, and for a radio that is off and was never read in this run. While false the page draws neither the slider nor the modem's - and +, so that the row has one shape from its first paint"
    )


# ---- the topic `radios`

RadioProblemCode = Literal[
    "radio.not_connected",
    "radio.searching",
    "radio.silent",
    "radio.text_lines",
    "radio.incoming_port",
    "radio.port_in_use",
    "radio.no_answer",
    "radio.not_paired",
    "radio.refused",
    "radio.open_failed",
    "radio.sends_text",
    "radio.write_timeout",
    "radio.resource_held",
    "modem.not_installed",
    "modem.stopped",
    "modem.network",
    "modem.no_port",
    "modem.not_started",
    "modem.sound_card",
    "modem.keying",
    "modem.keying_in_use",
    "modem.keying_missing",
    "modem.ports_taken",
    "modem.receive_stalled",
    "modem.receive_deaf",
    "modem.rig_silent",
    "modem.rig_keyed_long",
    "transmit.off",
    "beacon.not_sent",
]


class RadioProblem(_Model):
    """Why a radio, or its beacon, does not do what it is set to, as a code the page puts in its own words, with the values its sentence is made of (the English of the log is not told)."""

    code: RadioProblemCode = Field(
        description="`radio.not_connected` its line is not open (`name`: the radio's name in the log); `radio.searching` the daemon looks for its port; `radio.silent` its line is open and the radio does not answer (`since`: "
        "when the latest byte came, UTC); `radio.text_lines` its line is open and the LoRa board on it sends text lines, not KISS: nothing is sent until it is set to KISS; `radio.incoming_port` its port is the computer's incoming Bluetooth port (Windows), which reaches no device (`port`); `radio.port_in_use` another program has its port; `radio.no_answer` its Bluetooth device does not answer (switched off, asleep or out of range); `radio.not_paired` its Bluetooth device is not paired with this computer; `radio.refused` its Bluetooth device refused the connection; `radio.open_failed` its Bluetooth port could not be opened for another reason (the log says Windows' words); `radio.sends_text` its line is open and the KISS device on it sends text lines (monitor text, GPS sentences, KISS written as text) and no KISS frame; `radio.write_timeout` the last write to its port timed out (`seconds`): shown until a write goes through or a byte comes; `radio.resource_held` a device it is set to use is another's (`resource`: `serial`, `sound_card`, `keying`, `modem_ports` or `gps`; `holder`: the name of the radio that holds it, "
        "`GPS` for the GPS receiver; `held_by`: its id, 0 for the GPS receiver); `modem.<reason>` its Mercury modem is not running, `reason` as `ModemState.reason` says it; `modem.receive_deaf` its Mercury modem runs and hears nothing (its receive side stalled) and is started again soon; `modem.rig_silent` the rig program it is keyed through (flrig, rigctld) does not answer, refused a key-down or has not confirmed a key-up: its frames wait; `modem.rig_keyed_long` a key-down through the rig program outlasted its frame and the daemon let the radio go, shown until a key-down ends by itself; for its beacon `transmit.off` (RX only) and `beacon.not_sent` (`why`: the code of the reason, whose sentence the page has as the refusal `error.<why>`, "
        "and that reason's values)"
    )
    params: dict[str, str | int | float] = Field(
        description="the values of the sentence, by name; empty for a code that has none"
    )


class RadioLimits(_Model):
    """What the radio's type cannot do (neoaprs/radiotype.py `Limits`): constants of the type."""

    max_frame: int | None = Field(
        description="the longest AX.25 frame the radio carries whole, in bytes (Mercury: 123); null for AX.25's own"
    )
    beacon_min_min: int = Field(
        ge=1,
        description="the shortest beacon interval the radio takes, in minutes (Packet 20, Mercury 30): the station's interval is raised to it on this radio",
    )
    slow: bool = Field(
        description="a frame holds the shared channel for seconds (HF, LoRa): what the pairs pass onto the radio is limited (`LIMITS.pass` of the page)"
    )


class RadioAllowed(_Model):
    """What we decided the radio's type may do (neoaprs/radiotype.py `Allowed`): a control exists only where it is true."""

    paths: bool = Field(
        description="our frames on it may carry digipeaters: the path controls are shown for it; false: every frame goes direct"
    )
    digipeat: bool = Field(description="it may repeat what it hears (its own Digipeater tick, `radio/<id>/digipeat`)")
    smart_beacon: bool = Field(
        description="a moving station's SmartBeaconing applies on it; elsewhere the timed beacon goes with the latest fix"
    )
    gateway_heard: bool = Field(description="internet gateways hear its kind")
    shared_channel: bool = Field(
        description="it is a 1200-baud shared channel: the ALOHA circle is worked out from what it hears"
    )


class RadioCan(_Model):
    """What the radio's type can do (neoaprs/radiotype.py `Can`): the controls of its box."""

    find: bool = Field(description="Find my radio (a serial line: `find_radio` with this radio)")
    terminal: bool = Field(description="its line's log can be shown (`lines`)")
    tune: bool = Field(description="Tune (`radio_tune`)")
    key_test: bool = Field(description="the keying test (`radio_key_test`)")
    scope: bool = Field(
        description="the spectrum scope (`radio_scope`); whether it is shown now is the modem's `scope`"
    )
    tx_gain: bool = Field(description="the transmit gain (`radio/<id>/tx_gain_db`)")
    frequencies: bool = Field(description="the station's suggested frequencies are shown in its box")
    transmit: bool = Field(
        description="it can send: false for a receive-only type, which is never a message's, the beacon's, an object's, a bulletin's or the email radio, and whose line is never written to"
    )
    rx_level: bool = Field(description="its receive level is shown in its box (its modem's `rx_level`)")


class RadioChoices(_Model):
    """The operator's own values of the radio where its kind has them (`radio/<id>/beacon`, `radio/<id>/status`, `radio/<id>/ask`, `radio/<id>/local_info`, `radio/<id>/path`, `radio/<id>/digipeat`), as they are in force."""

    beacon: bool = Field(
        description="Send on: the beacon goes out on this radio (with one radio on, it goes on that one whatever this says)"
    )
    status: bool = Field(
        description="the status's Send on: the status report goes out on this radio; false by default (with one radio that can send on, on that one whatever this says; with several, while none that is on is ticked, on none); false for a radio that only receives"
    )
    ask: bool = Field(
        description="Ask around's Send on: a general query (`general_query`) goes out on this radio; read as `status` is"
    )
    local_info: bool = Field(
        description="Local info's Send on: the request to QRU that names no radio (`qru_ask`) goes out on this radio; read as `status` is"
    )
    path: str | None = Field(
        description="the digipeaters of its frames as the setting holds them (empty: the recommended path of the station's symbol, `DIRECT`: none); null for a kind that has no path"
    )
    digipeat: bool | None = Field(description="its digipeater is on; null for a kind that may not repeat")


class RadioBeaconState(_Model):
    """The radio's own beacon timer."""

    last_sent: Iso | None = Field(description="when our position last went out on it; null before one")
    next_due: Iso | None = Field(
        description="when the next timed beacon is due on it: its slot and the radio's random pause; null while none is planned (off, a moving station, the radio off)"
    )
    interval_min: int = Field(
        ge=0,
        description="the interval in force on it, in minutes: `beacon/interval_min` raised to the radio's own floor; 0 while the beacon does not go out on it (off, Send on not ticked, the radio off)",
    )
    problem: RadioProblem | None = Field(
        description="why the latest beacon due on it did not go out (`transmit.off`, `beacon.not_sent`); null after one that did"
    )


class RadioStatusState(_Model):
    """The status report on the radio (services/rigstatus.py `on_radio`)."""

    last_sent: Iso | None = Field(description="when our status report last went out on it; null before one")
    next_due: Iso | None = Field(
        description="when the next timed report is due on it: an interval after the slot of its last, and the radio's random pause; null while none is (the status does not go on it, the beacon or the status is off, none sent on it yet)"
    )
    interval_min: int = Field(
        ge=0,
        description="the interval in force on it, in minutes: `status/interval_min` raised to the radio's own floor (`limits.beacon_min_min` on HF and LoRa); 0 while the status does not go out on it",
    )


class RadioHold(_Model):
    """A device the radio holds now in the station's table of resources: no other radio, and not the GPS receiver, is given it."""

    resource: Literal["serial", "sound_card", "keying", "modem_ports", "gps"] = Field(
        description="what kind of device: a serial port, a sound card, the keying line's port, the port pair of a Mercury modem"
    )
    value: str = Field(
        description="the device as the table holds it: a serial port's resolved path (`/dev/ttyUSB0`, `COM3`), a sound card's id, the broadcast port of a Mercury pair (`8100`)"
    )


class RadioRow(_Model):
    """One radio of the station: what it is, how it is set, and how its line, its beacon and its modem are now. The rows are the values of the topic `radios`, keyed by `id` as text; a removed radio stays, marked,
    so that the packets and messages that name it still have its name. A radio that is added is a `set` of its row; a change of its state, counters, lines, beacon or modem is a `set` of the row, told at most four
    times a second; a change of the settings tells the topic whole."""

    id: int = Field(
        ge=1,
        description="the radio's id (an integer the database gave it, never given again): what every other row and command names it by",
    )
    kind: Literal["fm", "hf", "lora"] = Field(
        description="the kind of radio, fixed when it was added: its tag's colour and the defaults follow it"
    )
    type: str = Field(
        description="its type, a `key` of `RADIO_TYPES` (ui/src/protocol/lists.ts), of its kind; it may change within the kind (`radio_change`)"
    )
    name: str = Field(
        description="the name the operator typed (at most 8 characters); empty for none: the page calls it by its kind and `number` (`Packet`, `Mercury 2`) in its own words"
    )
    number: int = Field(
        ge=1,
        description="its number within its kind: 1 for the first of the kind by id among the radios not removed (`Mercury 2` is 2); a removed radio keeps its own",
    )
    enabled: bool = Field(description="its Enable is ticked (`radio_change` with `enabled`); false for a removed radio")
    position: int = Field(
        ge=1,
        description="its place in the list of boxes (and of the radio a call no radio heard takes: the first that can send): the lowest first, then by id",
    )
    removed: bool = Field(
        description="it was removed: its row stays so that what came by it keeps its name; it is no longer started, chosen or offered"
    )
    dummy: bool = Field(
        description="its type is a Dummy radio: the traffic is made up and nothing goes on the air; its tag is dashed"
    )
    state: Literal["stopped", "connecting", "connected", "waiting", "silent"] = Field(
        description="its line: `waiting` is between two attempts to open it, or its line is open again after a write timed out and nothing has gone through or come since, `silent` the line is open and the radio does not answer (a check of the keep-alive got no byte at all in answer), nothing is sent until it does; `stopped` for a radio that is off or removed"
    )
    problem: RadioProblem | None = Field(
        description="why it is not connected, while it is enabled and not connected; null otherwise"
    )
    stats: TncStats
    lines: list[TncLine] = Field(
        max_length=100,
        description="the latest 100 lines of what its line saw and did, oldest first; empty for a removed radio",
    )
    limits: RadioLimits
    allowed: RadioAllowed
    can: RadioCan
    choices: RadioChoices
    beacon: RadioBeaconState
    status: RadioStatusState
    modem: ModemState | None = Field(
        description="its modem, while its type is one the daemon starts a modem for (Mercury, Sound card); null for every other type and for a removed radio"
    )
    card: CardLevelsRow = Field(
        description="its sound card's own levels, read every two seconds while it runs and kept as read last while it is stopped or its card cannot be read; both null for a radio without a sound card of its own and before its card was read (`read` says which)"
    )
    holds: list[RadioHold] = Field(
        description="the devices it holds now: a serial port, a sound card, a keying line, a Mercury port pair; empty while it holds none"
    )
