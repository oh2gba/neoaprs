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
where it left it); only when something else took the pair meanwhile is another chosen, and the owner is told (`ports_changed`) to point the Tnc at it. A program of ours that listens on an address that is not the
loopback is ended and not run again (`foreign_listeners`): its ports have no password, and the Mercury NeoAPRS ships, on every system, listens on this computer only (packaging/mercury/loopback.patch).

A Mercury that something else runs (the port given for this run, `--hf-port`, the benches') is not started or stopped here, only listened to on the control port 200 above its KISS port. The setting `serial/port` is never the sign of one: it is the FM radio's, and a `tcp://` address there is a Direwolf's KISS port.

As the speaker of the Dummy HF radio (`start(..., speaker=True)`) the same program is started keying nothing on its fifo audio backend, paced and played by mercuryspeaker.py through the system's own player,
and the frames the dummy line is given (`play`) are written to its broadcast port, so that the operator hears the modem's own audio from the speakers; the Tnc is not connected to it, the hold is never asked,
and a player or a Mercury that is not there is a line in the log and nothing more (the Dummy HF radio works without it)."""
import asyncio
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from . import nodevices
from .clock import Clock, utcnow
from .config import Config
from .mercury import BROADCAST_PORT, CONTROL_OFFSET, MODE, SUGGESTED, TUNE_OFF, Keying, SerialPort, SoundCard, command, ini_text, keying_of, propose_keying, propose_sound_card, speaker_audio
from .mercurycontrol import ControlLine
from .mercurytune import Tuning
from .mercuryhelper import Command, HeldPorts, Program, choose_setup, end_stale, expected_program, find, foreign_listeners, free_ports, is_shipped, list_sound_cards
from .mercurychannel import CHANNEL_BUSY, TRANSMITTING, Channel
from .mercuryscoping import Scoping
from .mercuryscope import clamp_gain
from .mercuryspeaker import SpeakerAudio, SpeakerLine
from .serialprobe import PortInfo, available_ports
from .signal import Signal
from .source import Backoff, os_error_text
from .tasks import TaskSet
from .versions import Frequency

log = logging.getLogger("neoaprs.mercury")

HOST = "127.0.0.1"
INI_FILE = "mercury.ini"
PID_FILE = "mercury.pid"
NOT_INSTALLED = "the Mercury program is not in this installation of NeoAPRS (the AppImage, the .deb and the Windows installer carry it)"
OPEN_TO_NETWORK = "Mercury listens on the network and is not run: the Mercury NeoAPRS ships listens on this computer only"
SOUND_CARD_FAILED = "the sound card could not be opened: choose another one in the Sound card field"       # Mercury runs on deaf and mute when its sound card fails (seen on a station with two USB sound cards): the program is ended and the operator told where to act
STATES = ("stopped", "starting", "running", "waiting")
REASONS = ("", "not_installed", "stopped", "network", "no_port", "not_started", "sound_card")     # why the state is `waiting`, for the page to say in its own words (`problem` is the English of the log)
TESTS = ("", "tune", "key")                  # what the control port was asked for and not yet told to stop: nothing, the tune tone, the keying test


def system_serial_ports() -> list[SerialPort]:
    """The serial ports of the machine, the little the choice of a keying line needs of each (reads the system's lists: for a thread)."""
    return [SerialPort(p.device, p.vid, p.pid) for p in available_ports()]


def left_out(config: Config) -> tuple[str, ...]:
    """The serial ports that key no radio: the FM radio's, the GPS receiver's and the skipped ones (the choice of a keying line leaves them out)."""
    return tuple(p for p in (config.serial_port, config.serial_last_port, config.gps_device, *config.serial_skip_paths) if p)


def proposal(cards: Sequence[SoundCard], ports: Sequence[PortInfo], config: Config) -> tuple[str, str]:
    """The sound card (its id) and the keying (as the setting writes it) that the page proposes and stores while the settings are empty: the card from the cards listed, the keying from that card and the serial ports that key
    a radio (the ones the choice of the modem leaves out are left out here too); both empty when no card is listed."""
    card = propose_sound_card(cards)
    leave = left_out(config)
    return card, propose_keying(cards, card, [SerialPort(p.device, p.vid, p.pid) for p in ports if p.device not in leave])


def _address(url: str) -> tuple[str, int]:
    """The host and port of a `socket://host:port` or `tcp://host:port`."""
    rest = url.strip().split("://", 1)[1]
    host, _, port = rest.rpartition(":")
    return host.strip("[]") or HOST, int(port)


class Mercury(Channel, Tuning, Scoping):
    def __init__(self, data_dir: Path, clock: Clock = utcnow, finder: Callable[[], Command | None] | None = None, backoff: Backoff | None = None, control_backoff: Backoff | None = None) -> None:
        self.data_dir, self.clock = data_dir, clock
        self._finder = finder or find                                # the shipped program (mercuryhelper.find); a test gives its own
        self.backoff = backoff or Backoff()                          # between two starts of a program that died
        self._control_backoff = control_backoff
        self.changed: Signal[[]] = Signal("mercury.changed")        # the state, the keying, the busy channel: the page's radio topic is told again
        self.frequencies: list[Frequency] = [Frequency(band, dial) for band, dial in SUGGESTED]       # the frequencies the HF box suggests (versions.suggested: the project's list, else the version page's dial, else these two)
        self.ports_changed: Signal[[]] = Signal("mercury.ports_changed")      # a program started again had to take other ports: the owner points the HF Tnc at them
        self._held = HeldPorts()                                     # the pair of ports of this start, kept across the relaunches of a program that died
        self.state = "stopped"                                       # one of STATES: `starting` is the program started (or an attached one not yet answering on its control port), `running` its control port answering, `waiting` a problem
        self.problem, self.reason = "", ""                           # why it is not running, in English for the log; empty while it is. And the same as a code of REASONS, for the page's words (only `waiting` has one)
        self.broadcast_port, self.control_port = BROADCAST_PORT, BROADCAST_PORT + CONTROL_OFFSET
        self.attached = ""                                           # the address of a Mercury that something else runs; empty for one of ours
        self.speaker = False                                         # started as the speaker of the Dummy HF radio: nothing keyed, the frames of the dummy line played
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
        self._audio = SpeakerAudio(data_dir)
        self._test_task: asyncio.Task[None] | None = None
        self._tasks = TaskSet(log, "mercury")
        self._generation = 0
        self._config: Config | None = None

    # ---- life
    async def start(self, config: Config, attach: str = "", speaker: bool = False) -> None:
        """Starts the program for these settings, or, for a Mercury something else runs (`attach`, the port given for this run; never `serial/port`, which is the FM radio's), only listens to its control port; as `speaker`, starts it on the computer's
        own sound output for the Dummy HF radio."""
        await self.stop()
        self._generation += 1
        self._config = config
        self.speaker = speaker
        self.tx_gain_db = clamp_gain(config.mercury_tx_gain_db)
        self.backoff.reset()
        self._held.forget()
        if not speaker and attach:
            self.attached = attach
            _, port = _address(self.attached)
            self.broadcast_port, self.control_port = port, port + CONTROL_OFFSET
            if config.mercury_keying:
                self.keying = keying_of(config.mercury_keying)         # (the keying of the program something else runs is not ours to know: the setting is the best word there is, for what the keying test sends)
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
        self.attached = ""
        self.speaker = False
        self._clear_channel()
        self.snr = None
        self._set("stopped", "")

    async def _launch(self) -> None:
        """One start of the program: found, a Mercury of ours left behind ended, the sound card and the keying chosen, the configuration written, the ports chosen
        last and the program started. A failure that may pass is tried again after the back-off; one that cannot (no program, a speaker without pipes) is said and left."""
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
        ini, pid_file = self.data_dir / INI_FILE, self.data_dir / PID_FILE
        await asyncio.to_thread(end_stale, pid_file)                   # (first: a program of ours left behind holds the sound card and the ports)
        audio: list[str] = []
        if self.speaker:
            self.sound_card, self.keying = "", Keying("vox")           # (the speaker keys nothing and plays through the system's own player; the choosers are for a radio)
            log.info("Mercury is started as the speaker of the Dummy HF radio: it keys nothing and plays through the computer's sound output")
            if not await asyncio.to_thread(self._audio.prepare):
                log.info("the Dummy HF radio's speaker is not started: this system has no named pipes for Mercury's audio, and the modem on the default sound devices would be heard, or hear, for real")
                self._set("stopped", "")
                return
            audio = speaker_audio(str(self._audio.capture), str(self._audio.playback))
        else:
            self.sound_card, self.keying = await asyncio.to_thread(choose_setup, program, config.mercury_sound_card, config.mercury_keying, self.ports, left_out(config))
        keying = self.keying
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
            self._program.start(argv, self.data_dir, pid_file)
        except OSError as e:
            return self._failed(f"Mercury could not be started: {os_error_text(e)}", "not_started")
        self.starts += 1
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
        self._tasks.spawn(self._relaunch_after(self.backoff.next_delay_sec(), self._generation), "mercury-restart")

    def _choose_ports(self) -> None:
        """The pair of ports of this start (mercuryhelper.HeldPorts: kept for a program started again in the place of one that died, so that the HF Tnc finds the modem where it left it); when something else took
        the pair meanwhile the owner is told to point the Tnc at the new one. OSError when no pair is free."""
        taken, (self.broadcast_port, self.control_port) = self._held.choose(free_ports), self._held.pair          # (chosen first, then read)
        log.info("Mercury ports: %d for KISS, %d for control", self.broadcast_port, self.control_port)
        if taken is not None:
            log.warning("Mercury's ports %d and %d were taken while it was down: it is started on %d and %d, and the HF radio is pointed at them", *taken, *self._held.pair)
            self.ports_changed.emit()

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
        self._tasks.spawn(self._relaunch_after(self.backoff.next_delay_sec(), self._generation), "mercury-restart")

    async def _relaunch_after(self, delay_sec: float, generation: int) -> None:
        log.info("Mercury is started again in %g s", delay_sec)
        await asyncio.sleep(delay_sec)
        if generation == self._generation and self.state == "waiting":
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

    # ---- the speaker of the Dummy HF radio
    def play(self, data: bytes) -> None:
        """A frame of the Dummy HF radio, as KISS bytes, handed to the program to be heard (mercuryspeaker.py); nothing while the program is not there."""
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

    def _set(self, state: str, problem: str, reason: str = "") -> None:
        if (state, problem, reason) != (self.state, self.problem, self.reason):
            self.state, self.problem, self.reason = state, problem, reason
            log.log(logging.WARNING if problem else logging.INFO, "Mercury: %s%s", state, f": {problem}" if problem else "")
        self.changed.emit()
