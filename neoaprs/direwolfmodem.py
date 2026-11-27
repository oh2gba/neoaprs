"""Direwolf as a part of the daemon, for a radio of the Sound card type.

Starts the shipped program, watches its output, restarts it after a back-off; holds the claims.
Tune and the keying test are its `-x` runs: stop the modem, run, start it again on the same port.
"""

import asyncio
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from . import direwolfprogram, nodevices, usbtie, winmm
from .claims import Claim, Claims
from .clock import Clock, utcnow
from .direwolf import (
    CONF_FILE,
    FIRST_PORT,
    MODE,
    PID_FILE,
    PORT_TRIES,
    DeviceLists,
    adevice,
    audio_open_error,
    bind_failed,
    choose_keying,
    command,
    conf_text,
)
from .direwolf import (
    dcd_of,
    keying_open_error,
    kiss_from_client,
    level_of,
    own_card,
    ptt_of,
    ready_port,
    several_cm108,
    wrong_device,
)
from .direwolftune import Tuning, clamp
from .mercury import CONTROL_OFFSET, Keying, SerialPort, SoundCard, keying_of, propose_sound_card
from .mercuryclaims import MODEM_KINDS, HeldPorts, card_claim, held_card, keying_claim
from .mercuryhelper import Command, foreign_listeners, free_ports, list_sound_cards, next_modem_ports
from .mercuryhelper import find as mercury_program
from .mercurymodem import system_serial_ports
from .radiotype import RadioId
from .reading import NO_READING, Reading
from .serialprobe import PortInfo, claim_value, holder_words
from .modemstate import ModemLife
from .signal import Signal
from .source import Backoff, os_error_text
from .tasks import TaskSet

log = logging.getLogger("neoaprs.direwolf")

NOT_INSTALLED = (
    "Direwolf is not in this installation of NeoAPRS (the AppImage, the .deb and the Windows installer carry it)"
)
OPEN_TO_NETWORK = (
    "Direwolf listens on the network and is not run: the Direwolf NeoAPRS ships listens on this computer only"
)
SOUND_CARD_FAILED = "the sound card could not be opened: choose another one in the Sound card field"
NO_SOUND_CARD = "no sound card that could be the radio's was found: choose one in the Sound card field"
SOUND_CARD_NOT_FOUND = (
    "the sound card is not among the devices Windows lists for Direwolf: choose another one in the Sound card field"
)
KEYING_FAILED = "the keying device could not be opened: choose another way of keying"
SEVERAL_CM108 = "several sound chips could be keyed by CM108: choose another way of keying"
PORT_TAKEN = "the KISS port was taken by another program: another one is chosen"
STATES = ("stopped", "starting", "running", "waiting")
REASONS = ("", "not_installed", "stopped", "network", "no_port", "not_started", "sound_card", "keying")


class DirewolfModem(Tuning, ModemLife):
    PROGRAM, LOG, STARTING = "Direwolf", log, ("starting", "running")

    def __init__(
        self,
        folder: Path,
        clock: Clock = utcnow,
        finder: Callable[[], Command | None] | None = None,
        backoff: Backoff | None = None,
        *,
        claims: Claims | None = None,
        holder: RadioId,
        lister: Callable[[], Command | None] | None = None,
    ) -> None:
        self.home, self.clock = folder, clock
        self.claims, self.holder = claims, holder
        self._finder = finder or direwolfprogram.find  # a test gives its own
        self._lister = lister or mercury_program  # the Mercury program lists the cards (`mercury -z`)
        self.backoff = backoff or Backoff()
        self.changed: Signal[[]] = Signal("direwolf.changed")
        self.ports_changed: Signal[[]] = Signal("direwolf.ports_changed")
        self._held = HeldPorts()  # the KISS port of this start, kept across relaunches
        self.state, self.problem, self.reason = "stopped", "", ""
        self.kiss_port = FIRST_PORT
        self.test = ""  # "tune" or "key" during a calibration run
        self.keyed = self.busy = False
        self.rx_level: int | None = None  # last receive level reported; None while it does not run
        self.frames_keyed = self.starts = 0
        self.sound_card, self.keying, self.tx_gain_db = "", Keying("vox"), 0
        self.snr: float | None = None
        self.tx_peak_dbfs: int | None = None
        self.scope = False
        self.ports: Callable[[], list[SerialPort]] = system_serial_ports
        self.beside: Callable[[str, Sequence[str]], list[str] | None] = usbtie.beside
        self.windows = sys.platform == "win32"
        self._program = direwolfprogram.Program(self._ended, self._line)
        self.level_now = self._program.level_now
        self._settings: tuple[str, str, tuple[str, ...]] = ("", "", ())
        self._numbers: tuple[int, int] | None = None
        self._lists, self._ending, self._after_test = DeviceLists(), "", False
        self._listens = False  # set once this run says it listens on its KISS port
        self._tasks = TaskSet(log, "direwolf")
        self._test_task: asyncio.Task[None] | None = None
        self._generation = self._waits = 0
        self._handed = self._keyed_upto = 0
        self._swapping = asyncio.Lock()  # one swap of the program at a time

    @property
    def running(self) -> bool:
        return self.state == "running"

    @property
    def pid(self) -> int | None:
        return self._program.pid

    # ---- life
    async def start(self, sound_card: str, keying: str, gain_db: int, leave: Sequence[str] = ()) -> None:
        """Start Direwolf for these settings; `leave` lists serial ports that key no radio."""
        await self.stop()
        self._generation += 1
        self._settings, self.tx_gain_db = (sound_card, keying, tuple(leave)), clamp(gain_db)
        self.backoff.reset()
        self._held.forget()
        await self._launch()

    async def stop(self) -> None:
        self._generation += 1
        await self._tasks.cancel_all()
        self._test_task = None
        await asyncio.to_thread(self._program.stop)
        self._release_claims()
        self.test = ""
        self._clear()
        self._set("stopped", "")

    async def _launch(self) -> None:
        """Make one start attempt; a failure that may pass is retried after the back-off."""
        program = self._program_to_run()
        if program is None:
            if not nodevices.on():
                log.warning("no Direwolf program at %s", direwolfprogram.expected_program())
            self._set("waiting", NOT_INSTALLED, "not_installed")
            return
        log.info(
            "Direwolf program: %s%s",
            program[0],
            "" if direwolfprogram.is_shipped(program) else " (not the one NeoAPRS ships)",
        )
        try:
            await asyncio.to_thread(self.home.mkdir, parents=True, exist_ok=True)
        except OSError as e:
            return self._failed(
                f"Direwolf's folder could not be made in the data folder: {os_error_text(e)}", "not_started"
            )
        await asyncio.to_thread(direwolfprogram.end_stale, self.home / PID_FILE)
        problem, reason, names = await self._choose_setup()
        if problem:
            log.warning("Direwolf cannot be started: %s", problem)
            return self._failed(problem, reason)
        if (
            self.windows
            and (numbers := await asyncio.to_thread(_numbers_of, _lone_name(names, self.sound_card))) is None
        ):
            log.warning(
                "Direwolf cannot be started: the sound card %r is not one input and one output among the WinMM devices",
                self.sound_card,
            )
            return self._failed(SOUND_CARD_NOT_FOUND, "sound_card")
        self._numbers = numbers if self.windows else None
        await self._run(program)

    async def _choose_setup(self) -> tuple[str, str, dict[str, str]]:
        """Choose and hold the sound card and keying; return (problem, reason, card names by id)."""
        card_set, keying_set, leave = self._settings
        names: dict[str, str] = {}
        for _ in range(3):
            serial, held_cards = (
                (
                    self.claims.held_by_others(self.holder, "serial"),
                    self.claims.held_by_others(self.holder, "sound_card"),
                )
                if self.claims is not None
                else (frozenset[str](), frozenset[str]())
            )
            cards = await asyncio.to_thread(self._cards) if not card_set or not keying_set or self.windows else []
            names = {c.id: c.name for c in cards}
            self.sound_card = card_set or own_card([c for c in cards if c.id not in held_cards]) or own_card(cards)
            if not self.sound_card:
                log.info(
                    "Direwolf: no sound card stood out among %s",
                    ", ".join(f"{c.name!r} ({c.id})" for c in cards) or "none listed",
                )
                return NO_SOUND_CARD, "sound_card", names
            ports = [
                p
                for p in await asyncio.to_thread(self.ports)
                if (key := claim_value(p.device)) not in leave and (not serial or key not in serial)
            ]
            tied = (
                None if keying_set else await asyncio.to_thread(self.beside, self.sound_card, [p.device for p in ports])
            )
            self.keying = (
                keying_of(keying_set) if keying_set else choose_keying(names.get(self.sound_card, ""), ports, tied)
            )
            log.info(
                "Direwolf sound card %r, keyed by %s%s",
                self.sound_card,
                self.keying.text,
                "" if keying_set else " (chosen by NeoAPRS)",
            )
            other = hold_setup(self.claims, self.holder, self.sound_card, self.keying, self.windows)
            if other is None:
                return "", "", names
            if card_set if other.kind == "sound_card" else keying_set:
                break
        assert other is not None
        what = f"the sound card {self.sound_card}" if other.kind == "sound_card" else f"the keying {self.keying.text}"
        return (
            f"{what} is held by {self.claims.words(other.holder) if self.claims is not None else holder_words(other.holder)}",
            "not_started",
            names,
        )

    def _cards(self) -> list[SoundCard]:
        program = self._lister()
        return [] if program is None else list_sound_cards(program)

    async def _run(self, program: Command, test: str = "") -> None:
        """Choose the KISS port, write the configuration and start the program (or a `test` run)."""
        try:
            self._choose_port()
        except OSError as e:
            log.warning("Direwolf cannot be started: %s", e)
            return self._failed("no free port for Direwolf; the log says which were tried", "no_port")
        conf = self.home / CONF_FILE
        try:
            conf.write_text(
                conf_text(adevice(self.sound_card, self._numbers), self.keying, self.kiss_port), encoding="utf-8"
            )
        except OSError as e:
            return self._failed(
                f"Direwolf's configuration could not be written in the data folder: {os_error_text(e)}", "not_started"
            )
        except ValueError as e:
            return self._failed(str(e), "not_started")
        self._lists, self._ending, self._listens = DeviceLists(), "", False
        self._handed = self._keyed_upto = 0
        try:
            self._program.start(
                command(program, str(conf), self.tx_gain_db, test, self.keying.kind == "vox"),
                direwolfprogram.working_folder(program, self.home),
                self.home / PID_FILE,
            )
        except OSError as e:
            return self._failed(f"Direwolf could not be started: {os_error_text(e)}", "not_started")
        if test or self._after_test:
            return
        self.starts += 1
        if self.state == "waiting":
            self.changed.emit()
        else:
            self._set("starting", "")

    def _choose_port(self) -> None:
        """Choose and hold the KISS port; tell the line to follow if the last one was taken."""
        taken = self._held.choose(self._free_port)
        self.kiss_port = self._held.pair[0]
        if self.claims is not None:
            self.claims.release(self.holder, "modem_ports")
            self.claims.hold(Claim("modem_ports", str(self.kiss_port), self.holder))
        log.info("Direwolf's KISS port: %d", self.kiss_port)
        if taken is not None:
            log.warning(
                "Direwolf's KISS port %d was taken while it was down: it is started on %d, and its radio is pointed at it",
                taken[0],
                self.kiss_port,
            )
            self.ports_changed.emit()

    def _free_port(self) -> tuple[int, int]:
        """Return a free KISS port from FIRST_PORT up, not held by another radio's modem."""
        port = (
            free_ports(FIRST_PORT, PORT_TRIES)[0]
            if self.claims is None
            else next_modem_ports(self.claims, self.holder, first=FIRST_PORT, tries=PORT_TRIES)
        )
        return port, port + CONTROL_OFFSET

    def _release_claims(self) -> None:
        if self.claims is not None:
            for kind in sorted(MODEM_KINDS):
                self.claims.release(self.holder, kind)

    def held(self) -> list[Claim]:
        """Return what the modem holds: its sound card, keying line and KISS port."""
        return (
            []
            if self.claims is None
            else [c for c in self.claims.all() if c.holder == self.holder and c.kind in MODEM_KINDS]
        )

    # ---- what the program says
    def _line(self, line: str) -> None:
        """Handle one line of the program, on the loop."""
        if self.state == "stopped" or self._ending:
            return
        if self.windows and self._windows_line(line):
            return
        if (port := ready_port(line)) is not None:
            self._ready(port)
        elif bind_failed(line):
            self._end_run(PORT_TAKEN, "no_port", line)
        elif audio_open_error(line):
            self._end_run(SOUND_CARD_FAILED, "sound_card", line)
        elif keying_open_error(line):
            self._end_run(KEYING_FAILED, "keying", line)
        elif kiss_from_client(line):
            self._handed += 1  # a frame held until the channel is clear: a test waits
        elif (keyed := ptt_of(line)) is not None:
            if keyed and not self.keyed:
                self.frames_keyed += 1
                self._keyed_upto = self._handed
            self.keyed = keyed
            self.changed.emit()
        elif (busy := dcd_of(line)) is not None:
            self.busy = busy
            self.changed.emit()
        elif (level := level_of(line)) is not None and level != self.rx_level:
            self.rx_level = level
            self.changed.emit()

    def _windows_line(self, line: str) -> bool:
        """Windows: return whether the line ended the run (another device chosen, several CM108)."""
        self._lists.feed(line)
        if wrong_device(line) or (self._numbers is not None and self._lists.wrong(self._numbers)):
            self._end_run(SOUND_CARD_NOT_FOUND, "sound_card", line)
        elif several_cm108(line):
            self._end_run(SEVERAL_CM108, "keying", line)
        return bool(self._ending)

    def _ready(self, port: int) -> None:
        """Handle "Ready to accept KISS TCP client": running, unless it listens beyond the loopback.

        Only the first such line of a run counts; Direwolf repeats it on every client change."""
        if self._listens:
            return
        self._listens = True
        if found := foreign_listeners([port]):
            log.warning("Direwolf listens on the network (%s): it is ended and not run", ", ".join(found))
            self._generation += 1
            self._stop_run_later("direwolf-refuse")
            self._clear()
            self._set("waiting", OPEN_TO_NETWORK, "network")
            return
        self.backoff.connected()
        self._after_test = False
        self._starting_since = 0.0
        self._set("running", "")
        self.ports_changed.emit()  # the line connects now: Direwolf is already listening

    def _end_run(self, problem: str, reason: str, line: str) -> None:
        """End the run at once because the program cannot do its job; restart it later."""
        if self._ending:
            return
        self._ending = reason
        log.warning("Direwolf: %s (it said: %s)", problem, line)
        self._stop_run_later("direwolf-end")
        self._gone(problem, reason)

    def _ended(self, code: int | None, lines: list[str]) -> None:
        """Called from the reader thread when the program ended by itself: restart it."""
        if self.state == "stopped" or self._ending:
            return
        log.warning(
            "Direwolf ended (exit %s) after %d keyings; its last lines: %s",
            code,
            self.frames_keyed,
            " | ".join(lines[-3:]) or "(nothing)",
        )
        self._gone(f"Direwolf stopped (exit {code}); the log says why", "stopped")

    def _gone(self, problem: str, reason: str) -> None:
        self._clear()
        self.test, self._after_test = "", False
        self._set("waiting", problem, reason)
        self._relaunch_later()

    def _failed(self, problem: str, reason: str) -> None:
        self.test = ""
        self._set("waiting", problem, reason)
        self._relaunch_later()

    # ---- what the Tnc and the page ask
    @property
    def deaf(self) -> bool:
        return False  # no stall watch: Direwolf reports no stalled receive side

    def take_reading(self) -> Reading:
        return NO_READING

    def play(self, data: bytes) -> None:
        """Do nothing: Direwolf has no speaker."""

    def wire(self) -> dict[str, Any]:
        """Return the modem as the radio's row tells it (web/tncwire.py `ModemState`)."""
        return {
            "state": self.state,
            "reason": self.reason,
            "mode": MODE,
            "keyed": self.keyed or bool(self.test),
            "busy": self.busy,
            "test": self.test,
            "snr": None,
            "frames_keyed": self.frames_keyed,
            "max_frame": None,
            "sound_card": self.sound_card,
            "frequencies": [],
            "keying": self.keying.text,
            "scope": False,
            "tx_gain_db": self.tx_gain_db,
            "tx_peak_dbfs": None,
            "rx_level": self.rx_level,
        }

    def sound_cards(self) -> list[SoundCard]:
        """Return the HF modem's sound cards; none with no devices or no program. For a thread."""
        return [] if nodevices.refused("the sound cards are not listed for Direwolf", logging.INFO) else self._cards()

    def _program_to_run(self) -> Command | None:
        """Return the Direwolf of this installation; none under the no-devices switch."""
        return None if nodevices.refused("Direwolf is not started") else self._finder()

    def _clear(self) -> None:
        self.keyed = self.busy = False
        self.rx_level = None  # a stopped program hears nothing: the bar is empty


def port_chosen(modem: DirewolfModem) -> bool:
    """Return whether the modem has chosen its KISS port for this start (HeldPorts.chosen)."""
    return modem._held.chosen


def levels_card(modem: DirewolfModem) -> str:
    """Return the sound card whose levels are the radio's: the one its modem runs on."""
    return held_card(modem.claims, modem.holder, modem.sound_card)


def _numbers_of(card_name: str) -> tuple[int, int] | None:
    """Return the WinMM numbers of the named card (winmm.py); None if not one in and one out."""
    inputs, outputs = winmm.devices()
    return winmm.match(card_name, inputs, outputs) if card_name else None


def _lone_name(names: dict[str, str], card: str) -> str:
    """Return the listed name of the card, or "" when another listed card has the same name."""
    name = names.get(card, "")
    return name if list(names.values()).count(name) == 1 else ""


def proposal(
    cards: Sequence[SoundCard],
    ports: Sequence[PortInfo],
    leave: Sequence[str] = (),
    *,
    claims: Claims | None = None,
    holder: RadioId,
    beside: Callable[[str, Sequence[str]], list[str] | None] | None = None,
) -> tuple[str, str]:
    """Return the card and keying the page proposes while the settings are empty. For a thread."""
    beside = beside or usbtie.beside
    serial, held_cards = (
        (claims.held_by_others(holder, "serial"), claims.held_by_others(holder, "sound_card"))
        if claims is not None
        else (frozenset[str](), frozenset[str]())
    )
    card = propose_sound_card([c for c in cards if c.id not in held_cards])
    free = [
        SerialPort(p.device, p.vid, p.pid)
        for p in ports
        if (key := claim_value(p.device)) not in leave and (not serial or key not in serial)
    ]
    return card, choose_keying(
        next((c.name for c in cards if c.id == card), ""), free, beside(card, [p.device for p in free])
    ).text if cards else ""


def hold_setup(claims: Claims | None, holder: RadioId, sound_card: str, keying: Keying, windows: bool) -> Claim | None:
    """Hold the sound card and keying for the radio; return the claim that blocks it, if any."""
    if claims is None:
        return None
    claims.release(holder, "sound_card")
    claims.release(holder, "keying")
    line = keying_claim(keying, claim_value(keying.device) if keying.device else None, windows)
    for claim in (card_claim(sound_card, holder), *([Claim("keying", line, holder)] if line else [])):
        if (other := claims.hold(claim)) is not None:
            claims.release(holder, "sound_card")
            return other
    return None
