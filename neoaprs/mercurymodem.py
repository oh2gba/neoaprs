"""The Mercury HF modem as a part of the daemon.

Started with the Tnc when the radio type is Mercury, restarted after a back-off when it dies and
stopped with the Tnc. While Mercury keys the radio or hears a signal no frame is handed to it.
"""

import asyncio
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from . import nodevices
from .claims import Claim, Claims
from .clock import Clock, utcnow
from .config import Config
from .mercury import (
    BROADCAST_PORT,
    CONTROL_OFFSET,
    HOST,
    MODE,
    SUGGESTED,
    TUNE_OFF,
    Keying,
    SerialPort,
    SoundCard,
    command,
    ini_text,
    keying_of,
    ports_from,
    propose_keying,
    propose_sound_card,
    speaker_audio,
)
from .mercurycontrol import ControlLine
from .mercurytune import Tuning
from .mercuryclaims import INI_FILE, PID_FILE, HeldPorts, Holding, keying_claim, take_folder
from .mercuryhelper import (
    Command,
    Program,
    choose_setup,
    expected_program,
    find,
    foreign_listeners,
    free_ports,
    is_shipped,
    list_sound_cards,
    next_modem_ports,
)
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

NOT_INSTALLED = "the Mercury program is not in this installation of NeoAPRS (the AppImage, the .deb and the Windows installer carry it)"
OPEN_TO_NETWORK = (
    "Mercury listens on the network and is not run: the Mercury NeoAPRS ships listens on this computer only"
)
# Mercury runs deaf and mute when its sound card fails, so the program is ended.
SOUND_CARD_FAILED = "the sound card could not be opened: choose another one in the Sound card field"
STATES = ("stopped", "starting", "running", "waiting")
# Why the state is `waiting`, as a code for the page.
REASONS = ("", "not_installed", "stopped", "network", "no_port", "not_started", "sound_card")
TESTS = ("", "tune", "key")


def system_serial_ports() -> list[SerialPort]:
    """Return the machine's serial ports. For a thread."""
    return [SerialPort(p.device, p.vid, p.pid) for p in available_ports()]


def left_out(config: Config, but: RadioId) -> tuple[str, ...]:
    """Return the serial ports that key no radio of `but` (others', remembered, GPS, skipped)."""
    named = tuple(c.value for c in named_ports(config, off_too=True) if c.holder != but)
    return tuple(
        dict.fromkeys(
            v
            for v in (
                *named,
                *(claim_value(p) for p in (config.serial_last_port, config.gps_device, *config.serial_skip_paths)),
            )
            if v
        )
    )


def own_choice(config: Config, holder: RadioId) -> tuple[str, str, int]:
    """Return the radio's own sound card, keying and gain; "", "" and 0 where it has none."""
    spec = config.radio(holder)
    if spec is None or spec.removed or kind_field(spec.kind, "sound_card") is None:
        return "", "", 0
    return str(spec.value("sound_card")), str(spec.value("keying")), int(spec.value("tx_gain_db"))


def proposal(
    cards: Sequence[SoundCard],
    ports: Sequence[PortInfo],
    config: Config,
    *,
    claims: Claims | None = None,
    holder: RadioId = HF_ID,
) -> tuple[str, str]:
    """Return the card (id) and keying the page proposes while the settings are empty."""
    serial, held_cards = (
        (claims.held_by_others(holder, "serial"), claims.held_by_others(holder, "sound_card"))
        if claims is not None
        else (frozenset[str](), frozenset[str]())
    )
    card = propose_sound_card([c for c in cards if c.id not in held_cards])
    leave = left_out(config, holder)
    return card, propose_keying(
        cards,
        card,
        [
            SerialPort(p.device, p.vid, p.pid)
            for p in ports
            if (key := claim_value(p.device)) not in leave and (not serial or key not in serial)
        ],
    )


def _address(url: str) -> tuple[str, int]:
    """Return the host and port of a `socket://host:port` or `tcp://host:port`."""
    rest = url.strip().split("://", 1)[1]
    host, _, port = rest.rpartition(":")
    return host.strip("[]") or HOST, int(port)


class Mercury(Channel, Tuning, Scoping, Holding, ModemState):
    PROGRAM, LOG = "Mercury", log

    def __init__(
        self,
        data_dir: Path,
        clock: Clock = utcnow,
        finder: Callable[[], Command | None] | None = None,
        backoff: Backoff | None = None,
        control_backoff: Backoff | None = None,
        *,
        claims: Claims | None = None,
        holder: RadioId = HF_ID,
        folder: Path | None = None,
    ) -> None:
        self.data_dir, self.clock = data_dir, clock
        self.claims, self.holder, self.folder = claims, holder, folder
        self._finder = finder or find
        self.backoff = backoff or Backoff()
        self._control_backoff = control_backoff
        self.changed: Signal[[]] = Signal("mercury.changed")
        self.frequencies: list[Frequency] = [Frequency(band, dial) for band, dial in SUGGESTED]
        self.ports_changed: Signal[[]] = Signal("mercury.ports_changed")
        self._held = HeldPorts()  # the ports of this start, kept across restarts
        self.state = "stopped"
        self.problem, self.reason = "", ""
        self.broadcast_port, self.control_port = BROADCAST_PORT, BROADCAST_PORT + CONTROL_OFFSET
        self.attached = ""  # address of a Mercury run elsewhere
        self.speaker = False
        self._init_channel()
        self._init_scoping()
        self.test = ""
        self.ports: Callable[[], list[SerialPort]] = system_serial_ports
        self.sound_card = ""  # "": the system's default device
        self.keying = Keying("vox")
        self.frames_keyed = 0
        self.starts = 0
        self._program = Program(self._ended, self._audio_error)
        self._audio_failed = False
        self._control: ControlLine | None = None
        self.speaker_line = SpeakerLine(HOST, lambda: self.broadcast_port, lambda: self._program.running)
        self._audio = SpeakerAudio(self.home)
        self._test_task: asyncio.Task[None] | None = None
        self._tasks = TaskSet(log, "mercury")
        self._generation = 0
        self._waits = 0
        self._config: Config | None = None

    # ---- life
    async def start(self, config: Config, attach: str = "", speaker: bool = False) -> None:
        """Start the program for these settings; with `attach`, only listen to one run elsewhere."""
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
                self.keying = keying_of(keying)
            log.info(
                "Mercury is run by something else at %s; its control port %d is listened to",
                self.attached,
                self.control_port,
            )
            self._set("starting", "")
            self._start_control()
            return
        await self._launch()

    async def stop(self) -> None:
        self._generation += 1
        if self.test:
            self._write(TUNE_OFF)
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
        """Make one start attempt; a failure that may pass is retried after a back-off."""
        config = self._config
        assert config is not None
        program = self._program_to_run()
        self._audio_failed = False
        if program is None:
            if not nodevices.on():
                log.warning("no Mercury program at %s", expected_program())
            self._set("waiting", NOT_INSTALLED, "not_installed")
            return
        log.info("Mercury program: %s%s", program[0], "" if is_shipped(program) else " (not the one NeoAPRS ships)")
        pid_file = self.home / PID_FILE
        try:
            await asyncio.to_thread(take_folder, self.data_dir, self.home, self.holder == HF_ID, program)
        except OSError as e:
            log.warning("Mercury's folder %s could not be made: %s", self.home, os_error_text(e))
            return self._failed(
                f"Mercury's folder could not be made in the data folder: {os_error_text(e)}", "not_started"
            )
        await asyncio.to_thread(end_stale, pid_file, self.home / INI_FILE, program)
        audio = await self._speaker_audio() if self.speaker else []
        if audio is None:
            return
        if not self.speaker and (problem := await self._choose_setup(program, config)):
            log.warning("Mercury cannot be started: %s", problem)
            return self._failed(problem, "not_started")
        await self._run(program, audio, pid_file)

    async def _speaker_audio(self) -> list[str] | None:
        """Return the speaker's fifo backend flags (new pipes); None where there are none."""
        self.sound_card, self.keying = "", Keying("vox")
        log.info(
            "Mercury is started as the speaker of the Dummy Mercury radio: it keys nothing and plays through the computer's sound output"
        )
        self._audio.capture, self._audio.playback = self.home / CAPTURE_FIFO, self.home / PLAYBACK_FIFO
        if not await asyncio.to_thread(self._audio.prepare):
            log.info(
                "the Dummy Mercury radio's speaker is not started: this system has no named pipes for Mercury's audio, and the modem on the default sound devices would be heard, or hear, for real"
            )
            self._set("stopped", "")
            return None
        return speaker_audio(str(self._audio.capture), str(self._audio.playback))

    async def _choose_setup(self, program: Command, config: Config) -> str:
        """Choose and hold the sound card and keying; return why it cannot start, else ""."""
        other: Claim | None = None
        for _ in range(3):
            if (other := await self._chosen_and_held(program, config)) is None:
                return ""
            card, keying, _ = own_choice(config, self.holder)
            if card if other.kind == "sound_card" else keying:
                break
        assert other is not None
        what = (
            (f"the sound card {self.sound_card}" if self.sound_card else "the system's default sound device")
            if other.kind == "sound_card"
            else f"the keying line {self.keying.device}"
        )
        return f"{what} is held by {self.claims.words(other.holder) if self.claims is not None else holder_words(other.holder)}"

    async def _chosen_and_held(self, program: Command, config: Config) -> Claim | None:
        """Choose and hold the card and keying once; return a blocking claim, else None."""
        serial, held_cards = (
            (self.claims.held_by_others(self.holder, "serial"), self.claims.held_by_others(self.holder, "sound_card"))
            if self.claims is not None
            else (frozenset[str](), frozenset[str]())
        )
        ports = self.ports
        self.sound_card, self.keying = await asyncio.to_thread(
            choose_setup,
            program,
            *own_choice(config, self.holder)[:2],
            lambda: [p for p in ports() if not serial or claim_value(p.device) not in serial],
            left_out(config, self.holder),
            held_cards,
            key=claim_value,
        )
        return self._hold_setup(
            self.sound_card, keying_claim(self.keying, claim_value(self.keying.device) if self.keying.device else None)
        )

    async def _run(self, program: Command, audio: list[str], pid_file: Path) -> None:
        """Choose the ports, write the configuration and start the program on them."""
        keying, ini = self.keying, self.home / INI_FILE
        try:
            self._choose_ports()
        except OSError as e:
            log.warning("Mercury cannot be started: %s", e)
            return self._failed("no free port for Mercury; the log says which were tried", "no_port")
        try:
            ini.write_text(ini_text(keying, self.tx_gain_db, self.ui_port), encoding="utf-8")
        except OSError as e:
            log.warning("Mercury's configuration could not be written to %s: %s", ini, os_error_text(e))
            return self._failed(
                f"Mercury's configuration could not be written in the data folder: {os_error_text(e)}", "not_started"
            )
        argv = command(program, str(ini), self.sound_card, keying, self.broadcast_port, self.control_port, audio)
        try:
            self._program.start(argv, self.home, pid_file)
        except OSError as e:
            return self._failed(f"Mercury could not be started: {os_error_text(e)}", "not_started")
        self.starts += 1
        if self.state == "waiting":
            self.changed.emit()
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
        """Report a launch that failed for a reason that may pass, and retry after the back-off."""
        self._set("waiting", problem, reason)
        self._relaunch_later()

    def _free_pair(self) -> tuple[int, int]:
        """Return a free pair of ports: the first the probe finds that no other modem holds."""
        pair = free_ports()
        return pair if self.claims is None else ports_from(next_modem_ports(self.claims, self.holder, first=pair[0]))

    def _ended(self, code: int | None, lines: list[str]) -> None:
        """Called from the reader thread when the program ended by itself: restart it."""
        if self.state == "stopped":
            return
        log.warning(
            "Mercury ended (exit %s) after %d frames keyed; its last lines: %s",
            code,
            self.frames_keyed,
            " | ".join(lines[-3:]) or "(nothing)",
        )
        self._gone(f"Mercury stopped (exit {code}); the log says why", "stopped")

    def _audio_error(self, line: str) -> None:
        """Called from the reader thread when the sound card cannot be opened: end and retry later."""
        if self.state == "stopped" or self._audio_failed:
            return
        log.warning("Mercury could not open its sound card %r: %s", self.sound_card or "the system's default", line)
        self._audio_failed = True
        self._tasks.spawn(asyncio.to_thread(self._program.stop), "mercury-audio-stop")
        self._gone(SOUND_CARD_FAILED, "sound_card")

    def _gone(self, problem: str, reason: str) -> None:
        """The program is gone: close the control line and speaker, and schedule a start."""
        control, self._control = self._control, None
        if control is not None:
            self._tasks.spawn(control.stop(), "mercury-control-stop")
        self.speaker_line.close()
        self._clear_channel()
        self.test = ""
        self._set("waiting", problem, reason)
        self._relaunch_later()

    def _relaunch_later(self) -> None:
        """Schedule a start after the back-off for this wait only; a later wait voids it."""
        self._waits += 1
        self._tasks.spawn(
            self._relaunch_after(self.backoff.next_delay_sec(), self._generation, self._waits), "mercury-restart"
        )

    async def _relaunch_after(self, delay_sec: float, generation: int, wait: int) -> None:
        log.info("Mercury is started again in %g s", delay_sec)
        await asyncio.sleep(delay_sec)
        if generation == self._generation and wait == self._waits and self.state == "waiting":
            await self._launch()

    # ---- the control port
    def _start_control(self) -> None:
        self._control = ControlLine(
            HOST if not self.attached else _address(self.attached)[0],
            self.control_port,
            self._event,
            self._control_state,
            self._control_backoff,
        )
        self._control.start()

    def _control_state(self, up: bool, why: str) -> None:
        if up:
            if not self.attached and (
                found := foreign_listeners(
                    (
                        self.broadcast_port,
                        self.control_port,
                        self.control_port + 1,
                        *([self.ui_port] if self.ui_port else []),
                    )
                )
            ):
                self._tasks.spawn(self._refuse_open(found), "mercury-refuse")
                return
            self.backoff.connected()
            self._set("running", "")
        else:
            self._clear_channel()
            self.test = ""
            if self.state == "running":
                log.info("Mercury's control port: %s", why)
                self._set("starting", "")

    async def _refuse_open(self, found: list[str]) -> None:
        """End a program that listens beyond the loopback and do not restart it.

        Its ports take a TUNE or KISS frame from anyone.
        """
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
        """Hand a Dummy radio frame (KISS bytes) to the program to be heard."""
        self.speaker_line.play(data)

    # ---- what the Tnc and the page ask
    def describe(self) -> str:
        """Return the modem in a few words, e.g. "Mercury DATAC3, listening, SNR 3 dB"."""
        if self.state == "waiting":
            return f"Mercury {MODE}: {self.problem}"
        if self.state != "running":
            return f"Mercury {MODE}, {self.state}"
        held = self.hold()
        words = (
            ("tuning" if self.test == "tune" else "keyed" if self.test == "key" else "transmitting")
            if held == TRANSMITTING
            else "channel busy"
            if held == CHANNEL_BUSY
            else "listening"
        )
        snr = f", SNR {self.snr:.0f} dB" if self.snr is not None else ""
        return f"Mercury {MODE}, {words}{snr}"

    @property
    def running(self) -> bool:
        return self.state == "running"

    @property
    def pid(self) -> int | None:
        return self._program.pid

    def sound_cards(self) -> list[SoundCard]:
        """Return the sound cards Mercury lists; none without a Mercury. For a thread."""
        program = self._program_to_run()
        return [] if program is None else list_sound_cards(program)

    def _program_to_run(self) -> Command | None:
        """Return the Mercury program of this installation; None under the no-devices switch."""
        return (
            None
            if nodevices.refused("the Mercury modem program is not started and its sound cards are not listed")
            else self._finder()
        )

    def _clear_channel(self) -> None:
        """Clear what the program said (mercurychannel.py) and forget the scope rows it fed."""
        super()._clear_channel()
        self.forget_scope()
