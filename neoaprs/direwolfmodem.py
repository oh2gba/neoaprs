"""Direwolf as a part of the daemon, for a radio of the Sound card type: started with the radio's line (the program this installation carries, direwolfprogram.py, with the configuration written in the radio's own
folder from its sound card and its keying), watched by what it prints, started again after the back-off when it ends, stopped with the line, and asked by the Tnc (tnc.py, the `Modem` protocol) why a frame is
not to go now and what to say in the radio's status line.

What it holds of the station (claims.py): its sound card (the same id the Mercury modem's list gives a card, so an FM radio and an HF modem on one card are refused with the holder's name), its keying line (on
Windows `cm108` is one for the station: Direwolf there keys any CM108-class chip, the last of several), and its KISS port (the kind `modem_ports`, from 8002 up, kept for a program started again in the place of one
that died, as the Mercury modem's pair is). The settings name the card and the keying, or leave them to the daemon: the card the HF modem's list proposes, the keying `direwolf.choose_keying`. On Windows the card's
WinMM numbers are found first (winmm.py), and a Direwolf that says it chose another device is ended at once, before its KISS port exists.

Direwolf says what it does: `Ready to accept KISS TCP client` (running), `Bind failed` (its port taken: another is chosen), a sound card or a keying device that cannot be opened (waiting, with the reason the page
puts in its words), `PTT 0 = 1/0` (keyed), `DCD 0 = 1/0` (busy) and the receive level, every two seconds and at every packet heard (`rx_level`), and ten times a second for the pages that show it (`level_now`). Tune and the keying test are Direwolf's own calibration runs (`-x`): the radio's Direwolf is stopped
cleanly, the run keys the radio for TUNE_SEC or KEY_TEST_SEC, and the radio's Direwolf is started again on the same port; meanwhile the hold is on, so the services wait as they wait for any radio that is not free."""
import asyncio
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from . import direwolfprogram, nodevices, usbtie, winmm
from .claims import Claim, Claims
from .clock import Clock, utcnow
from .direwolf import CONF_FILE, FIRST_PORT, MODE, PID_FILE, PORT_TRIES, DeviceLists, adevice, audio_open_error, bind_failed, choose_keying, command, conf_text
from .direwolf import dcd_of, keying_open_error, kiss_from_client, level_of, own_card, ptt_of, ready_port, several_cm108, wrong_device
from .direwolftune import Tuning, clamp
from .mercury import CONTROL_OFFSET, Keying, SerialPort, SoundCard, keying_of, propose_sound_card
from .mercuryclaims import MODEM_KINDS, HeldPorts, held_card, keying_claim
from .mercuryhelper import Command, foreign_listeners, free_ports, list_sound_cards, next_modem_ports
from .mercuryhelper import find as mercury_program
from .mercurymodem import system_serial_ports
from .radiotype import RadioId
from .reading import NO_READING, Reading
from .serialprobe import PortInfo, claim_value, holder_words
from .modemstate import ModemState
from .signal import Signal
from .source import Backoff, os_error_text
from .tasks import TaskSet

log = logging.getLogger("neoaprs.direwolf")

HOST = "127.0.0.1"
NOT_INSTALLED = "Direwolf is not in this installation of NeoAPRS (the AppImage, the .deb and the Windows installer carry it)"
OPEN_TO_NETWORK = "Direwolf listens on the network and is not run: the Direwolf NeoAPRS ships listens on this computer only"
SOUND_CARD_FAILED = "the sound card could not be opened: choose another one in the Sound card field"
NO_SOUND_CARD = "no sound card that could be the radio's was found: choose one in the Sound card field"
SOUND_CARD_NOT_FOUND = "the sound card is not among the devices Windows lists for Direwolf: choose another one in the Sound card field"
KEYING_FAILED = "the keying device could not be opened: choose another way of keying"
SEVERAL_CM108 = "several sound chips could be keyed by CM108: choose another way of keying"
PORT_TAKEN = "the KISS port was taken by another program: another one is chosen"
STATES = ("stopped", "starting", "running", "waiting")
REASONS = ("", "not_installed", "stopped", "network", "no_port", "not_started", "sound_card", "keying")


class DirewolfModem(Tuning, ModemState):
    PROGRAM, LOG, STARTING = "Direwolf", log, ("starting", "running")     # (modemstate.py: a test or a new level swaps the program while the state stays `running`)

    def __init__(self, folder: Path, clock: Clock = utcnow, finder: Callable[[], Command | None] | None = None, backoff: Backoff | None = None, *, claims: Claims | None = None, holder: RadioId,
                 lister: Callable[[], Command | None] | None = None) -> None:
        self.home, self.clock = folder, clock                        # the radio's own folder (mercuryclaims.radio_folder): the configuration, the process id, and where the program runs
        self.claims, self.holder = claims, holder
        self._finder = finder or direwolfprogram.find                # the shipped Direwolf; a test gives its own
        self._lister = lister or mercury_program                     # the program that lists the sound cards: the Mercury every installation that carries Direwolf carries (`mercury -z`)
        self.backoff = backoff or Backoff()
        self.changed: Signal[[]] = Signal("direwolf.changed")
        self.ports_changed: Signal[[]] = Signal("direwolf.ports_changed")     # the line is to be pointed at the KISS port again: Direwolf listens on it now (another port, or back after a test)
        self._held = HeldPorts()                                     # the KISS port of this start (as the first of a pair: mercuryclaims.HeldPorts), kept across the relaunches
        self.state, self.problem, self.reason = "stopped", "", ""
        self.kiss_port = FIRST_PORT
        self.test = ""                                               # "tune" or "key" while that calibration run is on
        self.keyed = self.busy = False
        self.rx_level: int | None = None                             # the receive level as Direwolf said it last (every STATS_SEC, and at each packet heard), on its scale; none while it does not run
        self.frames_keyed = self.starts = 0
        self.sound_card, self.keying, self.tx_gain_db = "", Keying("vox"), 0
        self.snr: float | None = None                                # (the HF modem's readings, which Direwolf has none of)
        self.tx_peak_dbfs: int | None = None
        self.scope = False
        self.ports: Callable[[], list[SerialPort]] = system_serial_ports
        self.beside: Callable[[str, Sequence[str]], list[str] | None] = usbtie.beside      # the serial ports that are part of the card's interface (None: it cannot be told here)
        self.windows = sys.platform == "win32"
        self._program = direwolfprogram.Program(self._ended, self._line)
        self.level_now = self._program.level_now                    # the receive level every LEVEL_NOW_MS, for the pages that show it (web/levelfeed.py); the row's `rx_level` changes every STATS_SEC
        self._settings: tuple[str, str, tuple[str, ...]] = ("", "", ())        # the sound card and the keying the settings name ("" for the daemon's choice), and the ports that key no radio
        self._numbers: tuple[int, int] | None = None
        self._lists, self._ending, self._after_test = DeviceLists(), "", False
        self._listens = False                                            # this run of the program has said that it listens on its KISS port
        self._tasks = TaskSet(log, "direwolf")
        self._test_task: asyncio.Task[None] | None = None
        self._generation = self._waits = 0
        self._handed = self._keyed_upto = 0                          # the frames the line handed the radio's Direwolf (as it says them: `-d n`), and how many of them had been handed at its latest key
        self._swapping = asyncio.Lock()                              # one swap of the program at a time (a test, its end, a new transmit level): direwolftune.py


    @property
    def running(self) -> bool:
        return self.state == "running"

    @property
    def pid(self) -> int | None:
        return self._program.pid

    # ---- life
    async def start(self, sound_card: str, keying: str, gain_db: int, leave: Sequence[str] = ()) -> None:
        """Starts Direwolf for these settings: the sound card and the keying ("" for the daemon's own choice), the transmit gain, and the serial ports that key no radio (`leave`)."""
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
        """One start: the program found, the radio's folder made, a Direwolf of ours left behind ended, the sound card and the keying chosen and held (on Windows their WinMM numbers found), the KISS port chosen,
        the configuration written and the program started. A failure that may pass is tried again after the back-off; no program is said and left."""
        program = self._program_to_run()
        if program is None:
            if not nodevices.on():
                log.warning("no Direwolf program at %s", direwolfprogram.expected_program())
            self._set("waiting", NOT_INSTALLED, "not_installed")
            return
        log.info("Direwolf program: %s%s", program[0], "" if direwolfprogram.is_shipped(program) else " (not the one NeoAPRS ships)")
        try:
            await asyncio.to_thread(self.home.mkdir, parents=True, exist_ok=True)
        except OSError as e:
            return self._failed(f"Direwolf's folder could not be made in the data folder: {os_error_text(e)}", "not_started")
        await asyncio.to_thread(direwolfprogram.end_stale, self.home / PID_FILE)
        problem, reason, names = await self._choose_setup()
        if problem:
            log.warning("Direwolf cannot be started: %s", problem)
            return self._failed(problem, reason)
        if self.windows and (numbers := await asyncio.to_thread(_numbers_of, names.get(self.sound_card, ""))) is None:
            log.warning("Direwolf cannot be started: the sound card %r is not one input and one output among the WinMM devices", self.sound_card)
            return self._failed(SOUND_CARD_NOT_FOUND, "sound_card")
        self._numbers = numbers if self.windows else None
        await self._run(program)

    async def _choose_setup(self) -> tuple[str, str, dict[str, str]]:
        """The sound card and the keying the program runs with (the settings, else the daemon's choice, leaving out what the others hold), held for the radio; why it cannot start and the reason ("" when it can),
        and the names of the cards listed by id. A choice of the daemon's that another radio took meanwhile is made again without it. No card named and none of the radio's found (`own_card`) is no start: the
        system's default device may be the computer's speakers."""
        card_set, keying_set, leave = self._settings
        names: dict[str, str] = {}
        for _ in range(3):
            serial, held_cards = (self.claims.held_by_others(self.holder, "serial"), self.claims.held_by_others(self.holder, "sound_card")) if self.claims is not None else (frozenset[str](), frozenset[str]())
            cards = await asyncio.to_thread(self._cards) if not card_set or not keying_set or self.windows else []
            names = {c.id: c.name for c in cards}
            self.sound_card = card_set or own_card([c for c in cards if c.id not in held_cards]) or own_card(cards)     # (the radio's card another holds: said below with its holder)
            if not self.sound_card:
                log.info("Direwolf: no sound card stood out among %s", ", ".join(f"{c.name!r} ({c.id})" for c in cards) or "none listed")
                return NO_SOUND_CARD, "sound_card", names
            ports = [p for p in await asyncio.to_thread(self.ports) if (key := claim_value(p.device)) not in leave and (not serial or key not in serial)]     # (`leave` as the table compares a port: mercurymodem.left_out)
            tied = None if keying_set else await asyncio.to_thread(self.beside, self.sound_card, [p.device for p in ports])
            self.keying = keying_of(keying_set) if keying_set else choose_keying(names.get(self.sound_card, ""), ports, tied)
            log.info("Direwolf sound card %r, keyed by %s%s", self.sound_card, self.keying.text, "" if keying_set else " (chosen by NeoAPRS)")
            other = hold_setup(self.claims, self.holder, self.sound_card, self.keying, self.windows)
            if other is None:
                return "", "", names
            if card_set if other.kind == "sound_card" else keying_set:
                break
        assert other is not None
        what = f"the sound card {self.sound_card}" if other.kind == "sound_card" else f"the keying {self.keying.text}"
        return f"{what} is held by {self.claims.words(other.holder) if self.claims is not None else holder_words(other.holder)}", "not_started", names

    def _cards(self) -> list[SoundCard]:
        program = self._lister()
        return [] if program is None else list_sound_cards(program)

    async def _run(self, program: Command, test: str = "") -> None:
        """The KISS port chosen (kept across a test and a relaunch), the configuration written and the program started: the radio's Direwolf, or with `test` its calibration run."""
        try:
            self._choose_port()
        except OSError as e:
            log.warning("Direwolf cannot be started: %s", e)
            return self._failed("no free port for Direwolf; the log says which were tried", "no_port")
        conf = self.home / CONF_FILE
        try:
            conf.write_text(conf_text(adevice(self.sound_card, self._numbers), self.keying, self.kiss_port), encoding="utf-8")
        except OSError as e:
            return self._failed(f"Direwolf's configuration could not be written in the data folder: {os_error_text(e)}", "not_started")
        except ValueError as e:
            return self._failed(str(e), "not_started")
        self._lists, self._ending, self._listens = DeviceLists(), "", False
        self._handed = self._keyed_upto = 0
        try:
            self._program.start(command(program, str(conf), self.tx_gain_db, test, self.keying.kind == "vox"), direwolfprogram.working_folder(program, self.home), self.home / PID_FILE)
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
        """The KISS port of this start, held for the radio; when something else took the one of the last start the line is told to follow (`ports_changed`)."""
        taken = self._held.choose(self._free_port)
        self.kiss_port = self._held.pair[0]
        if self.claims is not None:
            self.claims.release(self.holder, "modem_ports")
            self.claims.hold(Claim("modem_ports", str(self.kiss_port), self.holder))
        log.info("Direwolf's KISS port: %d", self.kiss_port)
        if taken is not None:
            log.warning("Direwolf's KISS port %d was taken while it was down: it is started on %d, and its radio is pointed at it", taken[0], self.kiss_port)
            self.ports_changed.emit()

    def _free_port(self) -> tuple[int, int]:
        """A free KISS port from FIRST_PORT up (with the station's table, one no other radio's modem holds), as the first of a pair as HeldPorts keeps it."""
        port = free_ports(FIRST_PORT, PORT_TRIES)[0] if self.claims is None else next_modem_ports(self.claims, self.holder, first=FIRST_PORT, tries=PORT_TRIES)
        return port, port + CONTROL_OFFSET

    def _release_claims(self) -> None:
        if self.claims is not None:
            for kind in sorted(MODEM_KINDS):
                self.claims.release(self.holder, kind)

    def held(self) -> list[Claim]:
        """What the modem holds now: its sound card, its keying line, its KISS port."""
        return [] if self.claims is None else [c for c in self.claims.all() if c.holder == self.holder and c.kind in MODEM_KINDS]

    # ---- what the program says
    def _line(self, line: str) -> None:
        """One line of the program, on the loop; nothing more of a run that is being ended for what it said."""
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
            self._handed += 1                                        # (a frame of the line's, which Direwolf holds until the channel is clear: a test or a new level waits for it to go)
        elif (keyed := ptt_of(line)) is not None:
            if keyed and not self.keyed:
                self.frames_keyed += 1
                self._keyed_upto = self._handed                      # (what was handed before the key goes out in it)
            self.keyed = keyed
            self.changed.emit()
        elif (busy := dcd_of(line)) is not None:
            self.busy = busy
            self.changed.emit()
        elif (level := level_of(line)) is not None and level != self.rx_level:
            self.rx_level = level
            self.changed.emit()

    def _windows_line(self, line: str) -> bool:
        """Windows: whether the line ended the run, because Direwolf chose another device than the card's (it would run on the system's default) or found several CM108 chips (it would key the last)."""
        self._lists.feed(line)
        if wrong_device(line) or (self._numbers is not None and self._lists.wrong(self._numbers)):
            self._end_run(SOUND_CARD_NOT_FOUND, "sound_card", line)
        elif several_cm108(line):
            self._end_run(SEVERAL_CM108, "keying", line)
        return bool(self._ending)

    def _ready(self, port: int) -> None:
        """Direwolf listens on its KISS port: running, unless the kernel's table says it listens on another address than the loopback (then it is ended and not run again). Only the first such line of a run is
        news: Direwolf says "Ready to accept KISS TCP client application N" again each time a client attaches and each time one leaves, and taking those as a start pointed the line at the port again, which made
        Direwolf say it again: three opens a second, for ever."""
        if self._listens:
            return
        self._listens = True
        if found := foreign_listeners([port]):
            log.warning("Direwolf listens on the network (%s): it is ended and not run", ", ".join(found))
            self._generation += 1
            self._tasks.spawn(asyncio.to_thread(self._program.stop), "direwolf-refuse")
            self._clear()
            self._set("waiting", OPEN_TO_NETWORK, "network")
            return
        self.backoff.connected()
        self._after_test = False
        self._starting_since = 0.0
        self._set("running", "")
        self.ports_changed.emit()                                    # (the line connects now, not at the end of its back-off: Direwolf takes a moment to listen, and a test or a new level had it down)

    def _end_run(self, problem: str, reason: str, line: str) -> None:
        """The program said it cannot do its job (its sound card, its keying, its port): it is ended at once and started again after the back-off; the operator is told where to act."""
        if self._ending:
            return
        self._ending = reason
        log.warning("Direwolf: %s (it said: %s)", problem, line)
        self._tasks.spawn(asyncio.to_thread(self._program.stop), "direwolf-end")
        self._gone(problem, reason)

    def _ended(self, code: int | None, lines: list[str]) -> None:
        """The program ended by itself (told from its reader thread): started again after the back-off, unless it was stopped or a line already said why."""
        if self.state == "stopped" or self._ending:
            return
        log.warning("Direwolf ended (exit %s) after %d keyings; its last lines: %s", code, self.frames_keyed, " | ".join(lines[-3:]) or "(nothing)")
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

    def _relaunch_later(self) -> None:
        self._waits += 1
        self._tasks.spawn(self._relaunch_after(self.backoff.next_delay_sec(), self._generation, self._waits), "direwolf-restart")

    async def _relaunch_after(self, delay_sec: float, generation: int, wait: int) -> None:
        log.info("Direwolf is started again in %g s", delay_sec)
        await asyncio.sleep(delay_sec)
        if generation == self._generation and wait == self._waits and self.state == "waiting":
            await self._launch()

    # ---- what the Tnc and the page ask
    def take_reading(self) -> Reading:
        return NO_READING

    def play(self, data: bytes) -> None:
        """(The HF Dummy's speaker: nothing here.)"""

    def wire(self) -> dict[str, Any]:
        """The modem as the radio's row tells it (web/tncwire.py `ModemState`)."""
        return {"state": self.state, "reason": self.reason, "mode": MODE, "keyed": self.keyed or bool(self.test), "busy": self.busy, "test": self.test, "snr": None,
                "frames_keyed": self.frames_keyed, "max_frame": None, "sound_card": self.sound_card, "frequencies": [], "keying": self.keying.text, "scope": False, "tx_gain_db": self.tx_gain_db,
                "tx_peak_dbfs": None, "rx_level": self.rx_level}

    def sound_cards(self) -> list[SoundCard]:
        """The sound cards the HF modem's program lists; none under the no-devices switch or without that program. Runs the program: for a thread."""
        return [] if nodevices.refused("the sound cards are not listed for Direwolf", logging.INFO) else self._cards()

    def _program_to_run(self) -> Command | None:
        """The Direwolf of this installation; none under the no-devices switch, as in an installation without it."""
        return None if nodevices.refused("Direwolf is not started") else self._finder()

    def _clear(self) -> None:
        self.keyed = self.busy = False
        self.rx_level = None                                             # (a program that does not run hears nothing: the page's bar is empty, not at the last level)


def port_chosen(modem: DirewolfModem) -> bool:
    """Whether the modem has chosen its KISS port for this start (mercuryclaims.HeldPorts.chosen): until then `kiss_port` is only where a Direwolf of ours may be, another radio's for one."""
    return modem._held.chosen


def levels_card(modem: DirewolfModem) -> str:
    """The sound card whose own levels are the radio's: the one the modem runs on while its radio holds it (mercuryclaims.held_card)."""
    return held_card(modem.claims, modem.holder, modem.sound_card)


def _numbers_of(card_name: str) -> tuple[int, int] | None:
    """The WinMM numbers of the card of this name (winmm.py); None when it is not one input and one output there."""
    inputs, outputs = winmm.devices()
    return winmm.match(card_name, inputs, outputs) if card_name else None


def proposal(cards: Sequence[SoundCard], ports: Sequence[PortInfo], leave: Sequence[str] = (), *, claims: Claims | None = None, holder: RadioId,
             beside: Callable[[str, Sequence[str]], list[str] | None] | None = None) -> tuple[str, str]:
    """The sound card and the keying the page proposes for a Sound card radio while its settings are empty: the card the list proposes (leaving out the others'), and `choose_keying` on its name and the serial
    ports no one else holds (and none of `leave`), with those of them that are part of the card's interface (`beside`, else `usbtie.beside` as that module has it now); both empty when no card is listed. Reads
    sysfs: for a thread."""
    beside = beside or usbtie.beside
    serial, held_cards = (claims.held_by_others(holder, "serial"), claims.held_by_others(holder, "sound_card")) if claims is not None else (frozenset[str](), frozenset[str]())
    card = propose_sound_card([c for c in cards if c.id not in held_cards])
    free = [SerialPort(p.device, p.vid, p.pid) for p in ports if (key := claim_value(p.device)) not in leave and (not serial or key not in serial)]
    return card, choose_keying(next((c.name for c in cards if c.id == card), ""), free, beside(card, [p.device for p in free])).text if cards else ""


def hold_setup(claims: Claims | None, holder: RadioId, sound_card: str, keying: Keying, windows: bool) -> Claim | None:
    """The sound card and the keying line held for the radio in the place of what it held: the claim of the other that holds one of them, and then neither is held; None, and nothing held, without the table. The
    keying holds the port of a serial line, and on Windows `cm108` for the station (Direwolf there keys any CM108-class chip, the last of several)."""
    if claims is None:
        return None
    claims.release(holder, "sound_card")
    claims.release(holder, "keying")
    line = keying_claim(keying, claim_value(keying.device) if keying.device else None, windows)
    for claim in (Claim("sound_card", sound_card, holder), *([Claim("keying", line, holder)] if line else [])):
        if (other := claims.hold(claim)) is not None:
            claims.release(holder, "sound_card")
            return other
    return None
