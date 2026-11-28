"""What a Mercury modem holds of the station: its folder, its ports, its sound card and keying line.

The claims half of `Mercury`. Without the claims table a modem holds nothing and probes for ports.
"""

import logging
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from . import nodevices, soundserver
from .claims import Claim, Claims
from .mercurycards import stable_alsa_id
from .mercuryhelper import Command, alsa_card_names, expected_program, free_ports, pair_free
from .mercurystale import end_stale
from .mercury import BROADCAST_PORT, CONTROL_OFFSET, PTT_WITH_DEVICE, Keying
from .mercuryspeaker import CAPTURE_FIFO, PLAYBACK_FIFO
from .radiotype import RadioId, ResourceKind
from .signal import Signal
from .soundserver import Node
from .source import os_error_text

log = logging.getLogger("neoaprs.mercury")

INI_FILE = "mercury.ini"
PID_FILE = "mercury.pid"
RADIOS_FOLDER = "radios"  # per-radio folders in the data folder
# What a modem holds; its radio's line holds the serial port.
MODEM_KINDS: frozenset[ResourceKind] = frozenset({"sound_card", "keying", "modem_ports"})


def keying_claim(keying: Keying, device: str | None, windows: bool = sys.platform == "win32") -> str | None:
    """Return what a modem's keying holds: a serial port, or "cm108" for the station on Windows.

    On Windows Direwolf keys the last of several CM108 chips, so one radio at a time may use it.
    """
    if device and keying.kind in PTT_WITH_DEVICE:
        return device
    return "cm108" if keying.kind == "cm108" and windows else None


def held_card(claims: Claims | None, holder: RadioId, card: str) -> str:
    """Return the modem's sound card while its radio holds one in the table, else ""."""
    if claims is None or not card:
        return card
    return card if any(c.kind == "sound_card" and c.holder == holder for c in claims.all()) else ""


def radio_folder(data_dir: Path, radio: RadioId) -> Path:
    return data_dir / RADIOS_FOLDER / str(radio)


def take_folder(data_dir: Path, folder: Path, inherit: bool = True, program: Command | None = None) -> None:
    """Make the radio's folder and, if `inherit`, take over the files an old layout left in the data dir.

    A file that cannot be moved is logged. Raise OSError when the folder cannot be made.
    """
    if folder == data_dir:
        return
    folder.mkdir(parents=True, exist_ok=True)
    for name in (INI_FILE, PID_FILE, CAPTURE_FIFO, PLAYBACK_FIFO) if inherit else ():
        old, new = data_dir / name, folder / name
        try:
            if not os.path.lexists(old):
                continue
            if name == PID_FILE:
                end_stale(old, data_dir / INI_FILE, program or [str(expected_program())])
            elif name == INI_FILE and not new.exists():
                os.replace(old, new)
            else:
                old.unlink()
        except OSError as e:
            log.warning(
                "Mercury's old %s in the data folder could not be moved to %s: %s", name, folder, os_error_text(e)
            )


def end_left_behind(data_dir: Path) -> None:
    """End every Mercury that an unclean stop left running; blocks, so run it in a thread.

    Do nothing under the no-devices switch.
    """
    if nodevices.on():
        return
    program = [str(expected_program())]
    for pid_file in sorted((data_dir / RADIOS_FOLDER).glob(f"*/{PID_FILE}")):
        end_stale(pid_file, pid_file.parent / INI_FILE, program)
    end_stale(data_dir / PID_FILE, data_dir / INI_FILE, program)


class HeldPorts:
    """The pair of ports of one start, kept for a restart unless something else took it."""

    def __init__(self) -> None:
        self.pair: tuple[int, int] = (BROADCAST_PORT, BROADCAST_PORT + CONTROL_OFFSET)
        self._held = False

    def forget(self) -> None:
        self._held = False

    @property
    def chosen(self) -> bool:
        return self._held

    def choose(self, free: Callable[[], tuple[int, int]] = free_ports) -> tuple[int, int] | None:
        """Keep the held pair if still free, else a fresh one from `free`.

        Return the pair that was taken, else None. Raise OSError when none is free.
        """
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
    sound_card: str
    nodes: tuple[Node, ...]
    state: str
    ports_changed: Signal[[]]
    _held: HeldPorts

    def _free_pair(self) -> tuple[int, int]:
        raise NotImplementedError

    @property
    def home(self) -> Path:
        """The folder of the program's files: the radio's own, else the data folder."""
        return self.data_dir if self.folder is None else self.folder

    @property
    def ports_chosen(self) -> bool:
        return self._held.chosen

    def held_card(self) -> str:
        return held_card(self.claims, self.holder, soundserver.behind(self.sound_card, self.nodes, alsa_card_names()))

    def held(self) -> list[Claim]:
        return (
            []
            if self.claims is None
            else [c for c in self.claims.all() if c.holder == self.holder and c.kind in MODEM_KINDS]
        )

    def _choose_ports(self) -> None:
        """Choose and hold the pair of ports; raise OSError when none is free."""
        first = not self._held.chosen
        taken, (self.broadcast_port, self.control_port) = self._held.choose(self._free_pair), self._held.pair
        log.info("Mercury ports: %d for KISS, %d for control", self.broadcast_port, self.control_port)
        self._hold_pair()
        if taken is not None:
            log.warning(
                "Mercury's ports %d and %d were taken while it was down: it is started on %d and %d, and the Mercury radio is pointed at them",
                *taken,
                *self._held.pair,
            )
            self.ports_changed.emit()
        elif first and self.state == "waiting":
            self.ports_changed.emit()

    def _hold_pair(self) -> None:
        pair = Claim("modem_ports", str(self.broadcast_port), self.holder)
        if self.claims is None or pair in self.claims.all():
            return
        self.claims.release(self.holder, "modem_ports")
        # Only a Mercury run elsewhere can sit on a held pair.
        if self.claims.hold(pair) is not None:
            log.warning(
                "Mercury's ports %d and %d are held by another radio's modem", self.broadcast_port, self.control_port
            )

    def _hold_setup(self, sound_card: str, keying_port: str | None) -> Claim | None:
        """Hold the sound card and keying line; return another radio's claim on one, holding neither."""
        if self.claims is None:
            return None
        self.claims.release(self.holder, "sound_card")
        self.claims.release(self.holder, "keying")
        for claim in (
            *card_claims(sound_card, self.holder, self.nodes),
            *([Claim("keying", keying_port, self.holder)] if keying_port else []),
        ):
            if (other := self.claims.hold(claim)) is not None:
                self.claims.release(self.holder, "sound_card")
                return other
        return None

    def _release_claims(self) -> None:
        if self.claims is not None:
            for kind in sorted(MODEM_KINDS):
                self.claims.release(self.holder, kind)


def card_claim(sound_card: str, holder: RadioId) -> Claim:
    return Claim("sound_card", stable_alsa_id(sound_card, alsa_card_names()), holder)


def card_claims(
    sound_card: str, holder: RadioId, nodes: Sequence[Node] = (), card_names: Mapping[int, str] | None = None
) -> list[Claim]:
    """Return what a sound card setting holds; a sound server's device holds its ALSA card, else itself."""
    names = alsa_card_names() if card_names is None else card_names
    return [Claim("sound_card", stable_alsa_id(v, names), holder) for v in soundserver.claims(sound_card, nodes, names)]
