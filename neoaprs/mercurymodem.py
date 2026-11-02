"""The Mercury HF modem as a part of the daemon: started with the Tnc when the radio type is Mercury (the program on this computer, mercuryhelper.py, with the configuration written from the two settings, the
sound card and the keying), listened to on its control port (mercurycontrol.py), started again after the back-off when it dies, stopped with the Tnc, and asked by the Tnc (tnc.py, the `Modem` protocol) why a
frame is not to go now and what to say in the radio's status line.

The hold is the carrier sense this plane lacks: while Mercury keys the radio (`PTT ON` until `PTT OFF`, about four seconds for a frame) no frame is handed to it, so that our own frames go one at a time and
the services' pace (10 s between two of ours) counts from a frame that has really left; while Mercury's busy detector hears a signal (`BUSY ON` until `BUSY OFF`) no frame goes either, for at most
BUSY_HOLD_MAX_SEC, because the detector takes a step in the noise for a signal for a minute or two and traffic must not be stranded by it. A hold is a reason the Tnc gives (`why_unusable`): the beacon, the
messages, the acks and the answers wait, as they wait for a radio that is silent, and go when it is over.

A Mercury that something else runs (the `tcp://` address in `serial/port`, or the port given for this run) is not started or stopped here, only listened to on the control port 200 above its KISS port."""
import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path

from .clock import Clock, utcnow
from .config import Config
from .mercury import BROADCAST_PORT, BUSY_HOLD_MAX_SEC, CONTROL_OFFSET, FRAME_SEC, MODE, ControlEvent, SoundCard, command, ini_text, keying_of
from .mercurycontrol import ControlLine
from .mercuryhelper import Command, Program, end_stale, find, free_ports, list_sound_cards
from .signal import Signal
from .source import Backoff, os_error_text
from .tasks import TaskSet
from .tncprofile import names_tcp

log = logging.getLogger("neoaprs.mercury")

HOST = "127.0.0.1"
INI_FILE = "mercury.ini"
PID_FILE = "mercury.pid"
NOT_INSTALLED = "the Mercury program is not installed (see docs/RADIOS.md)"
TRANSMITTING = "the radio is transmitting"
CHANNEL_BUSY = "the channel is busy"
KEYED_MAX_SEC = 2 * FRAME_SEC + 5.0          # a `PTT ON` with no `PTT OFF` after this long is not believed: a transmitter that stayed keyed is Mercury's safety timer's business, and ours is not to wait for ever
STATES = ("stopped", "starting", "running", "waiting")


def _address(url: str) -> tuple[str, int]:
    """The host and port of a `socket://host:port` or `tcp://host:port`."""
    rest = url.strip().split("://", 1)[1]
    host, _, port = rest.rpartition(":")
    return host.strip("[]") or HOST, int(port)


class Mercury:
    def __init__(self, data_dir: Path, clock: Clock = utcnow, finder: Callable[[], Command | None] | None = None, backoff: Backoff | None = None, control_backoff: Backoff | None = None) -> None:
        self.data_dir = data_dir
        self.clock = clock
        self._finder = finder or (lambda: find(data_dir))
        self.backoff = backoff or Backoff()                          # between two starts of a program that died
        self._control_backoff = control_backoff
        self.changed: Signal[[]] = Signal("mercury.changed")        # the state, the keying, the busy channel: the page's radio topic is told again
        self.state = "stopped"                                       # one of STATES: `starting` is the program started (or an attached one not yet answering on its control port), `running` its control port answering, `waiting` a problem
        self.problem = ""                                            # why it is not running; empty while it is
        self.broadcast_port, self.control_port = BROADCAST_PORT, BROADCAST_PORT + CONTROL_OFFSET
        self.attached = ""                                           # the address of a Mercury that something else runs; empty for one of ours
        self.keyed = False                                           # Mercury has keyed the radio (PTT ON)
        self.busy = False                                            # Mercury's busy detector hears a signal (BUSY ON)
        self.snr: float | None = None                                # the signal-to-noise ratio of the latest frame decoded, dB
        self.frames_keyed = 0                                        # how many times the radio was keyed since the start
        self.starts = 0                                              # how many times the program was started
        self._keyed_at = self._busy_at = 0.0
        self._program = Program(self._ended)
        self._control: ControlLine | None = None
        self._tasks = TaskSet(log, "mercury")
        self._generation = 0
        self._config: Config | None = None

    # ---- life
    async def start(self, config: Config, attach: str = "") -> None:
        """Starts the program for these settings, or, for a Mercury something else runs (`attach`, or a `tcp://` address in serial/port), only listens to its control port."""
        await self.stop()
        self._generation += 1
        self._config = config
        self.backoff.reset()
        if attach or names_tcp(config.serial_port):
            self.attached = attach or config.serial_port
            _, port = _address(self.attached)
            self.broadcast_port, self.control_port = port, port + CONTROL_OFFSET
            self._set("starting", "")
            self._start_control()
            return
        await self._launch()

    async def stop(self) -> None:
        self._generation += 1
        await self._tasks.cancel_all()
        control, self._control = self._control, None
        if control is not None:
            await control.stop()
        await asyncio.to_thread(self._program.stop)
        self.attached = ""
        self.keyed = self.busy = False
        self.snr = None
        self._set("stopped", "")

    async def _launch(self) -> None:
        """One start of the program: found, given free ports and the configuration written for these settings, a Mercury of ours left behind ended first."""
        config = self._config
        assert config is not None
        program = self._finder()
        if program is None:
            self._set("waiting", NOT_INSTALLED)
            return
        try:
            self.broadcast_port, self.control_port = free_ports()
        except OSError as e:
            self._set("waiting", f"no free port for Mercury: {e}")
            return
        keying = keying_of(config.mercury_keying)
        ini, pid_file = self.data_dir / INI_FILE, self.data_dir / PID_FILE
        try:
            ini.write_text(ini_text(keying), encoding="utf-8")
        except OSError as e:
            self._set("waiting", f"Mercury's configuration could not be written to {ini}: {os_error_text(e)}")
            return
        await asyncio.to_thread(end_stale, pid_file)
        argv = command(program, str(ini), config.mercury_sound_card, keying, self.broadcast_port, self.control_port)
        try:
            self._program.start(argv, self.data_dir, pid_file)
        except OSError as e:
            self._set("waiting", f"Mercury could not be started: {os_error_text(e)}")
            return
        self.starts += 1
        self._set("starting", "")
        self._start_control()

    def _ended(self, code: int | None, lines: list[str]) -> None:
        """The program ended by itself (told from its reader thread): started again after the back-off, unless it was stopped."""
        if self.state == "stopped":
            return
        log.warning("Mercury ended (exit %s); its last line: %s", code, lines[-1] if lines else "(nothing)")
        control, self._control = self._control, None
        if control is not None:
            self._tasks.spawn(control.stop(), "mercury-control-stop")
        self.keyed = self.busy = False
        self._set("waiting", f"Mercury stopped (exit {code}); the log says why")
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
            self.backoff.connected()
            self._set("running", "")
        else:
            self.keyed = self.busy = False
            if self.state == "running":
                log.info("Mercury's control port: %s", why)
                self._set("starting", "")

    def _event(self, event: ControlEvent) -> None:
        now = time.monotonic()
        if event.kind == "ptt":
            if event.on and not self.keyed:
                self.frames_keyed += 1
            self.keyed, self._keyed_at = event.on, now
        elif event.kind == "busy":
            self.busy, self._busy_at = event.on, now
            log.debug("Mercury: the channel is %s", "busy" if event.on else "clear")
        elif event.kind == "snr" and event.value is not None:
            self.snr = event.value
        else:
            return
        self.changed.emit()

    # ---- what the Tnc and the page ask
    def hold(self) -> str:
        """Why no frame is to go now: the radio is keyed, or the channel is busy (and has been for less than BUSY_HOLD_MAX_SEC); "" when one may."""
        now = time.monotonic()
        if self.keyed and now - self._keyed_at < KEYED_MAX_SEC:
            return TRANSMITTING
        if self.busy and now - self._busy_at < BUSY_HOLD_MAX_SEC:
            return CHANNEL_BUSY
        return ""

    def describe(self) -> str:
        """The modem in a few words, for the radio's status line: "Mercury DATAC3 at 127.0.0.1:8100, listening, SNR 3 dB"."""
        where = self.attached.split("://", 1)[-1] if self.attached else f"{HOST}:{self.broadcast_port}"
        if self.state == "waiting":
            return f"Mercury {MODE}: {self.problem}"
        if self.state != "running":
            return f"Mercury {MODE} at {where}, {self.state}"
        held = self.hold()
        words = "transmitting" if held == TRANSMITTING else "channel busy" if held == CHANNEL_BUSY else "listening"
        snr = f", SNR {self.snr:.0f} dB" if self.snr is not None else ""
        return f"Mercury {MODE} at {where}, {words}{snr}"

    @property
    def running(self) -> bool:
        return self.state == "running"

    @property
    def pid(self) -> int | None:
        return self._program.pid

    def sound_cards(self) -> list[SoundCard]:
        """The sound cards Mercury lists; none when it is not installed. Runs the program: for a thread, not the loop."""
        program = self._finder()
        return [] if program is None else list_sound_cards(program)

    def _set(self, state: str, problem: str) -> None:
        if (state, problem) != (self.state, self.problem):
            self.state, self.problem = state, problem
            log.log(logging.WARNING if problem else logging.INFO, "Mercury: %s%s", state, f": {problem}" if problem else "")
        self.changed.emit()
