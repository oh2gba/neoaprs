"""What a Mercury modem holds of the station (plan §2, "Resources"; neoaprs/claims.py, the one table the radio registry keeps), the half of the modem part (mercurymodem.py, whose `Mercury` inherits this) that
keeps it: the radio's own folder (`home`: the configuration, the process id, the speaker's pipes and what the program writes where it runs), the pair of ports of a start (`HeldPorts`: chosen once and kept for a program
started again in the place of one that died; from the table when the modem has one, mercuryhelper.next_modem_ports), and the sound card and the keying line the program runs with.

A modem that is given the table holds its pair, its sound card and its keying line in it as the radio it is (`holder`), so that a second radio's modem is started on another pair and the daemon's own choice of its card and
its keying leaves them out; what it holds is let go at its stop, and kept while a program that died is started again. A modem made without the table holds nothing and finds its ports by probing alone; one made without a
folder of its own keeps its files in the data folder. What a NeoAPRS of one HF radio left in the data folder is radio 2's (`take_folder`). A class of its own for its size: it reads and sets the modem's ports and asks
it for a free pair (`_free_pair`, which the modem part provides)."""
import logging
import os
from collections.abc import Callable
from pathlib import Path

from .claims import Claim, Claims
from .mercuryhelper import end_stale, free_ports, pair_free
from .mercury import BROADCAST_PORT, CONTROL_OFFSET
from .mercuryspeaker import CAPTURE_FIFO, PLAYBACK_FIFO
from .radiotype import RadioId, ResourceKind
from .signal import Signal
from .source import os_error_text

log = logging.getLogger("neoaprs.mercury")

INI_FILE = "mercury.ini"
PID_FILE = "mercury.pid"
RADIOS_FOLDER = "radios"                                                         # the radios' own folders in the data folder, one by id: radios/2
MODEM_KINDS: frozenset[ResourceKind] = frozenset({"sound_card", "keying", "modem_ports"})     # what a modem holds (its radio's line holds its serial port, which the modem's line, a socket, has none of)


def radio_folder(data_dir: Path, radio: RadioId) -> Path:
    """The radio's own folder in the data folder, where the files of its modem are (made at the modem's first start)."""
    return data_dir / RADIOS_FOLDER / str(radio)


def take_folder(data_dir: Path, folder: Path, inherit: bool = True) -> None:
    """Makes the radio's own folder for the modem's files and, for the radio that was the HF radio (`inherit`: radio 2), moves into it what a NeoAPRS of one HF radio left in the data folder: the configuration, and the
    process id of a Mercury it may have left running, which the start then ends as one of its own (honoured once: from then on the file is in the radio's folder); the speaker's old pipes are removed. A file that cannot
    be moved is a line in the log, and the start goes on. Nothing when the folder is the data folder. OSError when the folder cannot be made."""
    if folder == data_dir:
        return
    folder.mkdir(parents=True, exist_ok=True)
    for name in (INI_FILE, PID_FILE, CAPTURE_FIFO, PLAYBACK_FIFO) if inherit else ():
        old, new = data_dir / name, folder / name
        try:
            if not os.path.lexists(old):
                continue
            if name in (INI_FILE, PID_FILE) and not new.exists():
                os.replace(old, new)
            elif name == PID_FILE:
                end_stale(old)
            else:
                old.unlink()
        except OSError as e:
            log.warning("Mercury's old %s in the data folder could not be moved to %s: %s", name, folder, os_error_text(e))


class HeldPorts:
    """The pair of ports of one start of the program: chosen once (`choose`), and kept for a program started again in the place of one that died, so that the HF Tnc, which waits on its port with its back-off, finds
    the modem where it left it (the pair is free for the new program: the old connections are in TIME_WAIT, which the probe and Mercury's own bind allow); another pair only when something else took the old one
    meanwhile, which `choose` says by giving the pair that was taken, so that the owner can point the Tnc at the new one. `forget` is a fresh start."""

    def __init__(self) -> None:
        self.pair: tuple[int, int] = (BROADCAST_PORT, BROADCAST_PORT + CONTROL_OFFSET)
        self._held = False

    def forget(self) -> None:
        self._held = False

    def choose(self, free: Callable[[], tuple[int, int]] = free_ports) -> tuple[int, int] | None:
        """The pair to start the program on, kept in `pair`: the one held when it is still free, else a fresh one from `free` (OSError from it when none is); the pair that was taken, when one was, else None."""
        if self._held and pair_free(self.pair[0]):
            return None
        taken, self.pair, self._held = self.pair if self._held else None, free(), True
        return taken


class Holding:
    data_dir: Path
    folder: Path | None
    claims: Claims | None
    holder: RadioId
    broadcast_port: int
    control_port: int
    ports_changed: Signal[[]]
    _held: HeldPorts

    def _free_pair(self) -> tuple[int, int]:
        raise NotImplementedError

    @property
    def home(self) -> Path:
        """The folder of the program's files: the radio's own, else the data folder."""
        return self.data_dir if self.folder is None else self.folder

    def held(self) -> list[Claim]:
        """What the modem holds of the station's resources now: its sound card, its keying line, its pair of ports (nothing without the table), in the order they were held."""
        return [] if self.claims is None else [c for c in self.claims.all() if c.holder == self.holder and c.kind in MODEM_KINDS]

    def _choose_ports(self) -> None:
        """The pair of ports of this start (HeldPorts: kept for a program started again in the place of one that died, so that the HF Tnc finds the modem where it left it), held for the radio; when something else took
        the pair meanwhile the owner is told to point the Tnc at the new one. OSError when no pair is free."""
        taken, (self.broadcast_port, self.control_port) = self._held.choose(self._free_pair), self._held.pair          # (chosen first, then read)
        log.info("Mercury ports: %d for KISS, %d for control", self.broadcast_port, self.control_port)
        self._hold_pair()
        if taken is not None:
            log.warning("Mercury's ports %d and %d were taken while it was down: it is started on %d and %d, and the HF radio is pointed at them", *taken, *self._held.pair)
            self.ports_changed.emit()

    def _hold_pair(self) -> None:
        """The pair in use (its broadcast port, as text) held for the radio in the place of the one it held before."""
        pair = Claim("modem_ports", str(self.broadcast_port), self.holder)
        if self.claims is None or pair in self.claims.all():
            return
        self.claims.release(self.holder, "modem_ports")
        if self.claims.hold(pair) is not None:                                         # (only a Mercury something else runs on a pair another radio's modem holds: the table never hands that pair out twice)
            log.warning("Mercury's ports %d and %d are held by another radio's modem", self.broadcast_port, self.control_port)

    def _hold_setup(self, sound_card: str, keying_port: str | None) -> Claim | None:
        """The sound card and the keying line (its port, for a keying on a serial line) the program is to run with, held for the radio in the place of what it held; the claim of the other radio that holds one of them,
        and then neither is held. None, and nothing held, without the table."""
        if self.claims is None:
            return None
        self.claims.release(self.holder, "sound_card")
        self.claims.release(self.holder, "keying")
        for claim in (Claim("sound_card", sound_card, self.holder), *([Claim("keying", keying_port, self.holder)] if keying_port else [])):
            if (other := self.claims.hold(claim)) is not None:
                self.claims.release(self.holder, "sound_card")
                return other
        return None

    def _release_claims(self) -> None:
        """What the modem holds is let go (the stop)."""
        if self.claims is not None:
            for kind in sorted(MODEM_KINDS):
                self.claims.release(self.holder, kind)

