"""The Mercury HF modem as a part of the daemon: started with the Tnc when the radio type is Mercury (the program on this computer, mercuryhelper.py, with the configuration written from the two settings, the
sound card and the keying), listened to on its control port (mercurycontrol.py), started again after the back-off when it dies, stopped with the Tnc, and asked by the Tnc (tnc.py, the `Modem` protocol) why a
frame is not to go now and what to say in the radio's status line.

The hold is the carrier sense this plane lacks: while Mercury keys the radio (`PTT ON` until `PTT OFF`, about four seconds for a frame) no frame is handed to it, so that our own frames go one at a time and
the services' pace (10 s between two of ours) counts from a frame that has really left; while Mercury's busy detector hears a signal (`BUSY ON` until `BUSY OFF`) no frame goes either, for at most
BUSY_HOLD_MAX_SEC, because the detector takes a step in the noise for a signal for a minute or two and traffic must not be stranded by it. A hold is a reason the Tnc gives (`why_unusable`): the beacon, the
messages, the acks and the answers wait, as they wait for a radio that is silent, and go when it is over.

Tune and the keying test (`tune`, `tune_stop`, `key_test`) are Mercury's own TUNE command on the control port, the half of this part that mercurytune.py holds (`Mercury` inherits it): the radio is keyed through
the keying the modem runs with and the tone goes through its sound card, for TUNE_SEC or until the operator presses again, or for the second of the keying test; the hold is on meanwhile, so no frame of ours goes under
the tone. Mercury unkeys by itself after a minute whatever happens to us.

The ports are chosen once for a start and kept for the program started again in the place of one that died (the HF Tnc is told its port when the radios start, and waits on it with its back-off: it finds the modem
where it left it); only when something else took the pair meanwhile is another chosen, and the owner is told (`ports_changed`) to point the Tnc at it. Given the station's table and a folder (a radio's modem:
mercuryclaims.py), it keeps its files in the radio's folder, takes its pair from the table and holds the pair, its sound card and its keying line there as its radio's. A program of ours that listens on an address that is not the
loopback is ended and not run again (`foreign_listeners`): its ports have no password, and the Mercury NeoAPRS ships, on every system, listens on this computer only (packaging/mercury/loopback.patch).

A Mercury that something else runs (the port given for this run, `--hf-port`, the benches') is not started or stopped here, only listened to on the control port 200 above its KISS port. The setting `serial/port` is never the sign of one: it is the FM radio's, and a `tcp://` address there is a Direwolf's KISS port.

As the speaker of the Dummy Mercury radio (`start(..., speaker=True)`) the same program is started keying nothing on its fifo audio backend, paced and played by mercuryspeaker.py through the system's own player,
and the frames the dummy line is given (`play`) are written to its broadcast port, so that the operator hears the modem's own audio from the speakers; the Tnc is not connected to it, the hold is never asked,
and a player or a Mercury that is not there is a line in the log and nothing more (the Dummy Mercury radio works without it)."""
import asyncio
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from . import nodevices
from .claims import Claim, Claims
from .clock import Clock, utcnow
from .config import Config
from .mercury import BROADCAST_PORT, CONTROL_OFFSET, MODE, SUGGESTED, TUNE_OFF, Keying, SerialPort, SoundCard, command, ini_text, keying_of, ports_from, propose_keying, propose_sound_card, speaker_audio
from .mercurycontrol import ControlLine
from .mercurytune import Tuning
from .mercuryclaims import INI_FILE, PID_FILE, HeldPorts, Holding, keying_claim, take_folder
from .mercuryhelper import Command, Program, choose_setup, expected_program, find, foreign_listeners, free_ports, is_shipped, list_sound_cards, next_modem_ports
from .mercurychannel import CHANNEL_BUSY, TRANSMITTING, Channel
from .mercuryscoping import Scoping
from .mercuryscope import clamp_gain
from .mercurystale import end_stale
from .mercuryspeaker import CAPTURE_FIFO, PLAYBACK_FIFO, SpeakerAudio, SpeakerLine
from .radiotype import HF_ID, RadioId
from .radiotypes import kind_field
from .serialprobe import PortInfo, available_ports, claim_value, holder_words, named_ports
from .modemstate import ModemState
from .signal import Signal
from .source import Backoff, os_error_text
from .tasks import TaskSet
from .versions import Frequency

log = logging.getLogger("neoaprs.mercury")

HOST = "127.0.0.1"
NOT_INSTALLED = "the Mercury program is not in this installation of NeoAPRS (the AppImage, the .deb and the Windows installer carry it)"
OPEN_TO_NETWORK = "Mercury listens on the network and is not run: the Mercury NeoAPRS ships listens on this computer only"
SOUND_CARD_FAILED = "the sound card could not be opened: choose another one in the Sound card field"       # Mercury runs on deaf and mute when its sound card fails (seen on a station with two USB sound cards): the program is ended and the operator told where to act
STATES = ("stopped", "starting", "running", "waiting")
REASONS = ("", "not_installed", "stopped", "network", "no_port", "not_started", "sound_card")     # why the state is `waiting`, for the page to say in its own words (`problem` is the English of the log)
TESTS = ("", "tune", "key")                  # what the control port was asked for and not yet told to stop: nothing, the tune tone, the keying test


def system_serial_ports() -> list[SerialPort]:
    """The serial ports of the machine, the little the choice of a keying line needs of each (reads the system's lists: for a thread)."""
    return [SerialPort(p.device, p.vid, p.pid) for p in available_ports()]


def left_out(config: Config, but: RadioId) -> tuple[str, ...]:
    """The serial ports that key no radio of `but`: every device another radio is set to, on or off (serialprobe.named_ports: its port, its keying line's port, as the station's table compares them), the port radio 1's
    search remembered, the GPS receiver's and the skipped ones (the choice of a keying line leaves them out; what is held, the choice leaves out by the table). Each as the table compares it (`claim_value`: a link
    resolved, a COM port in upper case): a listed port is left out when its `claim_value` is one of them."""
    named = tuple(c.value for c in named_ports(config, off_too=True) if c.holder != but)
    return tuple(dict.fromkeys(v for v in (*named, *(claim_value(p) for p in (config.serial_last_port, config.gps_device, *config.serial_skip_paths))) if v))


def own_choice(config: Config, holder: RadioId) -> tuple[str, str, int]:
    """The modem's radio's own sound card, keying and transmit gain (`radio/<id>/sound_card`, `keying`, `tx_gain_db`), the radio being `holder` of the settings: empty, empty and 0 (the daemon's own
    choice, the modem's own level) for a radio the settings do not have, one that is removed, or one of a kind without them."""
    spec = config.radio(holder)
    if spec is None or spec.removed or kind_field(spec.kind, "sound_card") is None:
        return "", "", 0
    return str(spec.value("sound_card")), str(spec.value("keying")), int(spec.value("tx_gain_db"))


def proposal(cards: Sequence[SoundCard], ports: Sequence[PortInfo], config: Config, *, claims: Claims | None = None, holder: RadioId = HF_ID) -> tuple[str, str]:
    """The sound card (its id) and the keying (as the setting writes it) that the page proposes and stores while the settings are empty: the card from the cards listed, the keying from that card and the serial ports that key
    a radio (the ones the choice of the modem leaves out are left out here too, and what the other radios and the GPS receiver hold in `claims`); both empty when no card is listed."""
    serial, held_cards = (claims.held_by_others(holder, "serial"), claims.held_by_others(holder, "sound_card")) if claims is not None else (frozenset[str](), frozenset[str]())
    card = propose_sound_card([c for c in cards if c.id not in held_cards])
    leave = left_out(config, holder)
    return card, propose_keying(cards, card, [SerialPort(p.device, p.vid, p.pid) for p in ports if (key := claim_value(p.device)) not in leave and (not serial or key not in serial)])


def _address(url: str) -> tuple[str, int]:
    """The host and port of a `socket://host:port` or `tcp://host:port`."""
    rest = url.strip().split("://", 1)[1]
    host, _, port = rest.rpartition(":")
    return host.strip("[]") or HOST, int(port)


class Mercury(Channel, Tuning, Scoping, Holding, ModemState):
    PROGRAM, LOG = "Mercury", log

    def __init__(self, data_dir: Path, clock: Clock = utcnow, finder: Callable[[], Command | None] | None = None, backoff: Backoff | None = None, control_backoff: Backoff | None = None, *,
                 claims: Claims | None = None, holder: RadioId = HF_ID, folder: Path | None = None) -> None:
        self.data_dir, self.clock = data_dir, clock
        self.claims, self.holder, self.folder = claims, holder, folder   # the station's table of resources, the radio this modem is, its own folder (mercuryclaims.py): none, today's shape (nothing held, the files in the data folder)
        self._finder = finder or find                                # the shipped program (mercuryhelper.find); a test gives its own
        self.backoff = backoff or Backoff()                          # between two starts of a program that died
        self._control_backoff = control_backoff
        self.changed: Signal[[]] = Signal("mercury.changed")        # the state, the keying, the busy channel: the page's radio topic is told again
        self.frequencies: list[Frequency] = [Frequency(band, dial) for band, dial in SUGGESTED]       # the frequencies the HF box suggests (versions.suggested: the project's list, else the version page's dial, else these two)
        self.ports_changed: Signal[[]] = Signal("mercury.ports_changed")      # a program started again had to take other ports: the owner points the HF Tnc at them
        self._held = HeldPorts()                                     # the pair of ports of this start, kept across the relaunches of a program that died
        self.state = "stopped"                                       # one of STATES: `starting` is the program started (or an attached one not yet answering on its control port), `running` its control port answering, `waiting` a problem (also while the start after it is under way: the problem stands until a start is running)
        self.problem, self.reason = "", ""                           # why it is not running, in English for the log; empty while it is. And the same as a code of REASONS, for the page's words (only `waiting` has one)
        self.broadcast_port, self.control_port = BROADCAST_PORT, BROADCAST_PORT + CONTROL_OFFSET
        self.attached = ""                                           # the address of a Mercury that something else runs; empty for one of ours
        self.speaker = False                                         # started as the speaker of the Dummy Mercury radio: nothing keyed, the frames of the dummy line played
        self._init_channel()
        self._init_scoping()
        self.test = ""                                               # one of TESTS: the tune tone or the keying test is on (the hold is on with it)
        self.ports: Callable[[], list[SerialPort]] = system_serial_ports      # the serial ports the choice of a keying line looks at (a test gives none: the operator's ports are never read by a test)
        self.sound_card = ""                                         # the sound card the program runs with (the setting, else the daemon's choice; "" is the system's default device)
        self.keying = Keying("vox")                                  # how it keys the radio (the setting, else the daemon's choice)
        self.frames_keyed = 0                                        # how many times the radio was keyed since the start
        self.starts = 0                                              # how many times the program was started
        self._program = Program(self._ended, self._audio_error)
        self._audio_failed = False                                   # the program's sound card could not be opened: the problem to keep when the program we ended for it ends
        self._control: ControlLine | None = None
        self.speaker_line = SpeakerLine(HOST, lambda: self.broadcast_port, lambda: self._program.running)        # the line to the broadcast port as the speaker: open while the program runs, counts what it played
        self._audio = SpeakerAudio(self.home)
        self._test_task: asyncio.Task[None] | None = None
        self._tasks = TaskSet(log, "mercury")
        self._generation = 0
        self._waits = 0                                              # the number of the latest wait that has a start after the back-off due (`_relaunch_later`)
        self._config: Config | None = None

    # ---- life
    async def start(self, config: Config, attach: str = "", speaker: bool = False) -> None:
        """Starts the program for these settings (its radio's own, `own_choice`: the sound card, the keying and the gain), or, for a Mercury something else runs (`attach`, the port given for this run; never
        a port of another radio), only listens to its control port; as `speaker`, starts it on the computer's own sound output for the Dummy Mercury radio."""
        await self.stop()
        self._generation += 1
        self._config = config
        self.speaker = speaker
        _, keying, gain = own_choice(config, self.holder)
        self.tx_gain_db = clamp_gain(gain)
        self.backoff.reset()
        self._held.forget()
        if not speaker and attach:
            self.attached = attach
            _, port = _address(self.attached)
            self.broadcast_port, self.control_port = port, port + CONTROL_OFFSET
            self._hold_pair()
            if keying:
                self.keying = keying_of(keying)                         # (the keying of the program something else runs is not ours to know: the setting is the best word there is, for what the keying test sends)
            log.info("Mercury is run by something else at %s; its control port %d is listened to", self.attached, self.control_port)
            self._set("starting", "")
            self._start_control()
            return
        await self._launch()

    async def stop(self) -> None:
        self._generation += 1
        if self.test:
            self._write(TUNE_OFF)                                    # (best effort: Mercury unkeys by itself after its deadline in any case)
            self.test = ""
        await self._tasks.cancel_all()
        control, self._control = self._control, None
        if control is not None:
            await control.stop()
        self.speaker_line.close()
        await asyncio.to_thread(self._audio.stop)
        await self._stop_ui()
        await asyncio.to_thread(self._program.stop)
        self._release_claims()
        self.attached = ""
        self.speaker = False
        self._clear_channel()
        self.snr = None
        self._set("stopped", "")

    async def _launch(self) -> None:
        """One start of the program: found, the radio's folder made, a Mercury of ours left behind ended, the sound card and the keying chosen and held, the configuration written, the ports chosen last and the
        program started. A failure that may pass is tried again after the back-off; one that cannot (no program, a speaker without pipes) is said and left."""
        config = self._config
        assert config is not None
        program = self._program_to_run()
        self._audio_failed = False
        if program is None:
            if not nodevices.on():                                     # (under the no-devices switch the program was not looked for, and the switch has said so itself)
                log.warning("no Mercury program at %s", expected_program())
            self._set("waiting", NOT_INSTALLED, "not_installed")
            return
        log.info("Mercury program: %s%s", program[0], "" if is_shipped(program) else " (not the one NeoAPRS ships)")
        pid_file = self.home / PID_FILE
        try:
            await asyncio.to_thread(take_folder, self.data_dir, self.home, self.holder == HF_ID, program)     # (first: what an older NeoAPRS of one HF radio left in the data folder is radio 2's, its process id among it)
        except OSError as e:
            log.warning("Mercury's folder %s could not be made: %s", self.home, os_error_text(e))
            return self._failed(f"Mercury's folder could not be made in the data folder: {os_error_text(e)}", "not_started")
        await asyncio.to_thread(end_stale, pid_file, self.home / INI_FILE, program)       # (first: a program of ours left behind holds the sound card and the ports)
        audio = await self._speaker_audio() if self.speaker else []
        if audio is None:
            return
        if not self.speaker and (problem := await self._choose_setup(program, config)):
            log.warning("Mercury cannot be started: %s", problem)
            return self._failed(problem, "not_started")
        await self._run(program, audio, pid_file)

    async def _speaker_audio(self) -> list[str] | None:
        """The speaker of the Dummy Mercury radio keys nothing and plays through the system's own player: the flags of its fifo backend, with the pipes made anew; None, and the modem stopped, where there are none."""
        self.sound_card, self.keying = "", Keying("vox")               # (the choosers are for a radio)
        log.info("Mercury is started as the speaker of the Dummy Mercury radio: it keys nothing and plays through the computer's sound output")
        self._audio.capture, self._audio.playback = self.home / CAPTURE_FIFO, self.home / PLAYBACK_FIFO      # (the pipes in the modem's folder of this start)
        if not await asyncio.to_thread(self._audio.prepare):
            log.info("the Dummy Mercury radio's speaker is not started: this system has no named pipes for Mercury's audio, and the modem on the default sound devices would be heard, or hear, for real")
            self._set("stopped", "")
            return None
        return speaker_audio(str(self._audio.capture), str(self._audio.playback))

    async def _choose_setup(self, program: Command, config: Config) -> str:
        """The sound card and the keying the program runs with (mercuryhelper.choose_setup: the settings, else the daemon's own choice, which leaves out what the other radios and the GPS receiver hold), held for the
        radio; why it cannot start when another radio holds the one it is to run with ("" when it can). A choice of the daemon's that another radio's modem took meanwhile is made again, without it."""
        other: Claim | None = None
        for _ in range(3):                                             # (two modems that choose at once: the later one chooses again, leaving out what the first now holds)
            if (other := await self._chosen_and_held(program, config)) is None:
                return ""
            card, keying, _ = own_choice(config, self.holder)
            if card if other.kind == "sound_card" else keying:
                break                                                  # (what the settings name is theirs: it is the problem, not chosen anew)
        assert other is not None
        what = (f"the sound card {self.sound_card}" if self.sound_card else "the system's default sound device") if other.kind == "sound_card" else f"the keying line {self.keying.device}"
        return f"{what} is held by {self.claims.words(other.holder) if self.claims is not None else holder_words(other.holder)}"

    async def _chosen_and_held(self, program: Command, config: Config) -> Claim | None:
        """One choice of the sound card and the keying, held for the radio: the claim of the other radio that holds one of them, None when both are the radio's now."""
        serial, held_cards = (self.claims.held_by_others(self.holder, "serial"), self.claims.held_by_others(self.holder, "sound_card")) if self.claims is not None else (frozenset[str](), frozenset[str]())
        ports = self.ports
        self.sound_card, self.keying = await asyncio.to_thread(choose_setup, program, *own_choice(config, self.holder)[:2], lambda: [p for p in ports() if not serial or claim_value(p.device) not in serial], left_out(config, self.holder), held_cards, key=claim_value)
        return self._hold_setup(self.sound_card, keying_claim(self.keying, claim_value(self.keying.device) if self.keying.device else None))

    async def _run(self, program: Command, audio: list[str], pid_file: Path) -> None:
        """The ports chosen, the configuration written and the program started on them."""
        keying, ini = self.keying, self.home / INI_FILE
        try:
            self._choose_ports()                                       # (last of the slow steps: nothing of the above, which takes seconds, is to find the pair taken meanwhile)
        except OSError as e:
            log.warning("Mercury cannot be started: %s", e)
            return self._failed("no free port for Mercury; the log says which were tried", "no_port")
        try:
            ini.write_text(ini_text(keying, self.tx_gain_db, self.ui_port), encoding="utf-8")
        except OSError as e:
            log.warning("Mercury's configuration could not be written to %s: %s", ini, os_error_text(e))
            return self._failed(f"Mercury's configuration could not be written in the data folder: {os_error_text(e)}", "not_started")
        argv = command(program, str(ini), self.sound_card, keying, self.broadcast_port, self.control_port, audio)
        try:
            self._program.start(argv, self.home, pid_file)
        except OSError as e:
            return self._failed(f"Mercury could not be started: {os_error_text(e)}", "not_started")
        self.starts += 1
        if self.state == "waiting":
            self.changed.emit()                                        # (a start after a wait: its problem stands until this one is running, so the status line does not lose it at every attempt)
        else:
            self._set("starting", "")
        self._start_control()
        await self._stop_ui()
        self._start_ui()
        if self.speaker:
            generation = self._generation
            self._tasks.spawn(self.speaker_line.run(lambda: generation == self._generation), "mercury-speaker")
            if audio:
                self._audio.start()

    def _failed(self, problem: str, reason: str) -> None:
        """A launch that failed for a reason that may pass (no free port, the data folder briefly unwritable, the program not started): said, and tried again after the back-off, as a program that ended is."""
        self._set("waiting", problem, reason)
        self._relaunch_later()

    def _free_pair(self) -> tuple[int, int]:
        """A free pair of ports for a fresh start: the first pair the probe finds free (free_ports), and with the station's table the first from there up that no other radio's modem holds (next_modem_ports)."""
        pair = free_ports()
        return pair if self.claims is None else ports_from(next_modem_ports(self.claims, self.holder, first=pair[0]))

    def _ended(self, code: int | None, lines: list[str]) -> None:
        """The program ended by itself (told from its reader thread): started again after the back-off, unless it was stopped."""
        if self.state == "stopped":
            return
        log.warning("Mercury ended (exit %s) after %d frames keyed; its last lines: %s", code, self.frames_keyed, " | ".join(lines[-3:]) or "(nothing)")
        self._gone(f"Mercury stopped (exit {code}); the log says why", "stopped")

    def _audio_error(self, line: str) -> None:
        """The program printed that its sound card could not be opened (told from its reader thread): it would run on deaf and mute and the status say "running", so it is ended, the operator is told where to act,
        and it is started again after the back-off (a card plugged in, or chosen anew, is taken then)."""
        if self.state == "stopped" or self._audio_failed:
            return
        log.warning("Mercury could not open its sound card %r: %s", self.sound_card or "the system's default", line)
        self._audio_failed = True
        self._tasks.spawn(asyncio.to_thread(self._program.stop), "mercury-audio-stop")
        self._gone(SOUND_CARD_FAILED, "sound_card")

    def _gone(self, problem: str, reason: str) -> None:
        """The program is no more: the control line and the speaker go, the hold is off, and a start is due after the back-off."""
        control, self._control = self._control, None
        if control is not None:
            self._tasks.spawn(control.stop(), "mercury-control-stop")
        self.speaker_line.close()
        self._clear_channel()
        self.test = ""
        self._set("waiting", problem, reason)
        self._relaunch_later()

    def _relaunch_later(self) -> None:
        """A start after the back-off, for this wait only: a later failure (of the start it makes, or of the program meanwhile) brings its own, and this one is void. (The state cannot tell: it stays `waiting` while that start is under way.)"""
        self._waits += 1
        self._tasks.spawn(self._relaunch_after(self.backoff.next_delay_sec(), self._generation, self._waits), "mercury-restart")

    async def _relaunch_after(self, delay_sec: float, generation: int, wait: int) -> None:
        log.info("Mercury is started again in %g s", delay_sec)
        await asyncio.sleep(delay_sec)
        if generation == self._generation and wait == self._waits and self.state == "waiting":
            await self._launch()

    # ---- the control port
    def _start_control(self) -> None:
        self._control = ControlLine(HOST if not self.attached else _address(self.attached)[0], self.control_port, self._event, self._control_state, self._control_backoff)
        self._control.start()

    def _control_state(self, up: bool, why: str) -> None:
        if up:
            if not self.attached and (found := foreign_listeners((self.broadcast_port, self.control_port, self.control_port + 1, *([self.ui_port] if self.ui_port else [])))):
                self._tasks.spawn(self._refuse_open(found), "mercury-refuse")
                return
            self.backoff.connected()
            self._set("running", "")
        else:
            self._clear_channel()
            self.test = ""                                           # (a tone under way ends by Mercury's own deadline at the latest; we cannot say any more)
            if self.state == "running":
                log.info("Mercury's control port: %s", why)
                self._set("starting", "")

    async def _refuse_open(self, found: list[str]) -> None:
        """The program we started listens on an address that is not the loopback (the kernel's table says so, `found`): it is ended and not started again. Its ports take a TUNE or a KISS frame from anyone who reaches
        them, past every interlock of ours, so a Mercury that is not the one NeoAPRS ships (built to listen on this computer only) does not run under this daemon."""
        log.warning("Mercury listens on the network (%s): it is ended and not run", ", ".join(found))
        self._generation += 1
        control, self._control = self._control, None
        if control is not None:
            await control.stop()
        await asyncio.to_thread(self._program.stop)
        self._clear_channel()
        self._set("waiting", OPEN_TO_NETWORK, "network")

    def _write(self, line: str) -> bool:
        return self._control is not None and self._control.write(line)

    # ---- the speaker of the Dummy Mercury radio
    def play(self, data: bytes) -> None:
        """A frame of the Dummy Mercury radio, as KISS bytes, handed to the program to be heard (mercuryspeaker.py); nothing while the program is not there."""
        self.speaker_line.play(data)

    # ---- what the Tnc and the page ask
    def describe(self) -> str:
        """The modem in a few words, for the radio's status line: "Mercury DATAC3, listening, SNR 3 dB". The ports are the log's business (the lines that start the program say them), not the operator's."""
        if self.state == "waiting":
            return f"Mercury {MODE}: {self.problem}"
        if self.state != "running":
            return f"Mercury {MODE}, {self.state}"
        held = self.hold()
        words = ("tuning" if self.test == "tune" else "keyed" if self.test == "key" else "transmitting") if held == TRANSMITTING else "channel busy" if held == CHANNEL_BUSY else "listening"
        snr = f", SNR {self.snr:.0f} dB" if self.snr is not None else ""
        return f"Mercury {MODE}, {words}{snr}"


    @property
    def running(self) -> bool:
        return self.state == "running"

    @property
    def pid(self) -> int | None:
        return self._program.pid

    def sound_cards(self) -> list[SoundCard]:
        """The sound cards Mercury lists; none when this installation has no Mercury. Runs the program: for a thread, not the loop."""
        program = self._program_to_run()
        return [] if program is None else list_sound_cards(program)

    def _program_to_run(self) -> Command | None:
        """The Mercury program of this installation; none under the no-devices switch, as in an installation without it, so that no modem is started on a sound card and a keying line and no sound card is listed."""
        return None if nodevices.refused("the Mercury modem program is not started and its sound cards are not listed") else self._finder()

    def _clear_channel(self) -> None:
        """What the program said is cleared (mercurychannel.py), and the rows of the scope it fed are forgotten with it."""
        super()._clear_channel()
        self.forget_scope()
