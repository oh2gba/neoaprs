"""The driver of a radio of the Sound card type (neoaprs/radiodriver.py; plan §2, "Type"): Direwolf on the radio's sound card (direwolfmodem.py), and the line to its KISS port. The modem is started before
the line, because it chooses the port the line then connects to; a modem that cannot be started is said in the log and the line is started all the same: it has a port only once the modem has chosen
its KISS port for this start (`port_chosen`), and until then none, and says the modem's problem: a start refused before the choice (no Direwolf, the sound card held) leaves the port where another radio's
Direwolf may be. The two are stopped together.

A change of the sound card, the keying or the type restarts the radio; the transmit level is set in the running modem (it starts its program again with it), and the sound card and the keying the running modem
chose for itself are no change when the settings come to name exactly those (`made_explicit`). Under the no-devices switch the daemon starts no Direwolf, and without a Direwolf in this installation none
runs either: the line then has no port, because whatever listens where a Direwolf of ours would be is not ours and is never connected to; after a start tried again the line follows (`ports_changed`)."""
import logging
from pathlib import Path
from typing import NamedTuple

from . import nodevices
from .cardlevels import CardLevels, wanted
from .claims import Claim, Claims
from .clock import Clock, utcnow
from .config import DEFAULTS, Config
from .direwolf import PROFILE
from .mercury import HOST
from .direwolfmodem import DirewolfModem, levels_card, port_chosen
from .mercurydriver import chosen_as_set
from .mercurymodem import left_out
from .radiodriver import RunOverrides
from .radiospec import RadioSpec
from .soundmixer import Mixer
from .tnc import Tnc
from .tncprofile import LINE_SPEED, tcp_url

log = logging.getLogger("neoaprs.controller")        # what the start of a radio says is the controller's, whoever does it

NO_DIREWOLF = "a Sound card radio has no line to a Direwolf: none is started"       # what the no-devices switch says of the radio's port


class DirewolfSettings(NamedTuple):
    modem: tuple[str, str]                  # the sound card and the keying the modem is given ("" for the daemon's own choice): a change of either restarts the radio


def direwolf_settings(spec: RadioSpec) -> DirewolfSettings:
    return DirewolfSettings((spec.value("sound_card"), spec.value("keying")))


def direwolf_words(spec: RadioSpec) -> str:
    """The radio that is started, for the log."""
    card, keying = direwolf_settings(spec).modem
    started = "which is not started" if nodevices.on() else "started by NeoAPRS"
    return f"Direwolf on the sound card {card or '(the daemon\'s choice)'}, keyed by {keying or '(the daemon\'s choice)'}, {started}"


class DirewolfDriver:
    def __init__(self, spec: RadioSpec, claims: Claims, folder: Path, clock: Clock = utcnow, line: Tnc | None = None, *, modem: DirewolfModem | None = None, mixer: Mixer | None = None) -> None:
        self.id = spec.id
        self.claims = claims
        self._line = line if line is not None else Tnc(clock=clock, profile=PROFILE)
        self._modem = modem if modem is not None else DirewolfModem(folder, clock, claims=claims, holder=spec.id)
        self._line.radio_id = spec.id
        self._line.modem = self._modem                 # (the line asks it why no frame is to go now, and what to say in the status line)
        self._card = CardLevels(lambda: levels_card(self._modem), lambda: self._modem.starts, mixer)       # (the card while the radio holds it: never one another radio holds)
        self._spec, self._station, self._run = spec, DEFAULTS, RunOverrides()

    @property
    def line(self) -> Tnc:
        return self._line

    @property
    def modem(self) -> DirewolfModem:
        return self._modem

    @property
    def card(self) -> CardLevels:
        return self._card

    def configure(self, spec: RadioSpec, station: Config, run: RunOverrides) -> None:
        self._spec, self._station, self._run = spec, station, run
        self._point()
        self._line.set_check(run.check_sec)

    def _point(self) -> None:
        """The line, which is stopped, takes its port: the modem's KISS port as it is now (none under the no-devices switch, nor before the modem has chosen its port for this start)."""
        no_line = (nodevices.refused(NO_DIREWOLF, logging.INFO) if self._spec.enabled else nodevices.on()) or not port_chosen(self._modem)
        self._line.port, self._line.baud, self._line.profile, self._line.fallback_probe, self._line.skip, self._line.pattern = ("" if no_line else tcp_url(HOST, self._modem.kiss_port)), LINE_SPEED, PROFILE, False, (), ""

    def restart_key(self, spec: RadioSpec, station: Config, run: RunOverrides) -> tuple[object, ...]:
        """The sound card and the keying (the transmit level is set live, and so are the card's own levels)."""
        return (direwolf_settings(spec),)

    def made_explicit(self, before: RadioSpec, after: RadioSpec) -> RadioSpec:
        """`before`, with the sound card and the keying that the running modem chose for itself taken as set where `after` sets exactly those: storing the daemon's proposal is no reason to restart it."""
        return chosen_as_set(before, after, self._modem.state, self._modem.sound_card, self._modem.keying.text)

    def words(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        return direwolf_words(spec)

    async def start(self) -> None:
        spec = self._spec
        try:
            await self._modem.start(spec.value("sound_card"), spec.value("keying"), spec.value("tx_gain_db"), left_out(self._station, spec.id))     # (the modem first: it chooses the port the line connects to)
        except Exception:
            log.exception("Direwolf could not be started")
        self._point()
        await self._line.start()
        await self._card.start(*wanted(spec))

    async def stop(self) -> None:
        await self._card.stop()
        await self._line.stop()
        await self._modem.stop()

    def held(self) -> list[Claim]:
        """What the station's table says this radio holds (the modem claims its sound card, its keying line and its KISS port)."""
        return [claim for claim in self.claims.all() if claim.holder == self.id]
