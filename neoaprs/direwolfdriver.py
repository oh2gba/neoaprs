"""Driver of a Sound card radio: Direwolf on the radio's sound card and the line to its KISS port.

The modem starts first because it chooses the KISS port. Until it has chosen one the line has no
port, so it never connects to another radio's Direwolf. A card or keying change restarts the radio.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from . import nodevices
from .cardlevels import CardLevels, wanted
from .claims import Claim, Claims
from .clock import Clock, utcnow
from .config import DEFAULTS, Config
from .direwolf import PROFILE, PROFILE_300, modem_baud
from .mercury import HOST
from .direwolfmodem import DirewolfModem, levels_card, port_chosen
from .mercurydriver import chosen_as_set
from .mercurymodem import left_out
from .radiodriver import RunOverrides
from .radiospec import RadioSpec
from .soundmixer import Mixer
from .tnc import Tnc
from .tncprofile import LINE_SPEED, tcp_url

log = logging.getLogger("neoaprs.controller")

PROFILES = {p.key: p for p in (PROFILE, PROFILE_300)}
NO_DIREWOLF = "a Sound card radio has no line to a Direwolf: none is started"


class DirewolfSettings(NamedTuple):
    # Sound card and keying ("" lets the daemon choose), and the speed of the type's modem; a change restarts.
    modem: tuple[str, str]
    baud: int


def direwolf_settings(spec: RadioSpec) -> DirewolfSettings:
    return DirewolfSettings((spec.value("sound_card"), spec.value("keying")), modem_baud(spec.rtype.profile))


def direwolf_words(spec: RadioSpec) -> str:
    """Describe the radio being started, for the log."""
    card, keying = direwolf_settings(spec).modem
    started = "which is not started" if nodevices.on() else "started by NeoAPRS"
    return f"Direwolf on the sound card {card or "(the daemon's choice)"}, keyed by {keying or "(the daemon's choice)"}, {started}"


class DirewolfDriver:
    def __init__(
        self,
        spec: RadioSpec,
        claims: Claims,
        folder: Path,
        clock: Clock = utcnow,
        line: Tnc | None = None,
        *,
        modem: DirewolfModem | None = None,
        mixer: Mixer | None = None,
    ) -> None:
        self.id = spec.id
        self.claims = claims
        self._line = line if line is not None else Tnc(clock=clock, profile=PROFILES.get(spec.rtype.profile, PROFILE))
        self._modem = modem if modem is not None else DirewolfModem(folder, clock, claims=claims, holder=spec.id)
        self._line.radio_id = spec.id
        self._line.modem = self._modem
        # Only the card this radio holds, never one that another radio holds.
        self._card = CardLevels(lambda: levels_card(self._modem), lambda: self._modem.starts, mixer)
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
        """Point the stopped line at the modem's KISS port, or at none without devices."""
        no_line = (
            nodevices.refused(NO_DIREWOLF, logging.INFO) if self._spec.enabled else nodevices.on()
        ) or not port_chosen(self._modem)
        (
            self._line.port,
            self._line.baud,
            self._line.profile,
            self._line.fallback_probe,
            self._line.skip,
            self._line.pattern,
        ) = (
            ("" if no_line else tcp_url(HOST, self._modem.kiss_port)),
            LINE_SPEED,
            PROFILES.get(self._spec.rtype.profile, PROFILE),
            False,
            (),
            "",
        )

    def restart_key(self, spec: RadioSpec, station: Config, run: RunOverrides) -> tuple[object, ...]:
        """Return the sound card, keying and speed; the transmit level and card levels are applied live."""
        return (direwolf_settings(spec),)

    def made_explicit(self, before: RadioSpec, after: RadioSpec) -> RadioSpec:
        """Return `before` with the modem's card and keying marked set where `after` has them."""
        return chosen_as_set(before, after, self._modem.state, self._modem.sound_card, self._modem.keying.text)

    def words(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        return direwolf_words(spec)

    async def start(self) -> None:
        spec = self._spec
        try:
            await self._modem.start(
                spec.value("sound_card"),
                spec.value("keying"),
                spec.value("tx_gain_db"),
                left_out(self._station, spec.id),
                baud=direwolf_settings(spec).baud,
            )
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
        """Return the claims this radio holds: its sound card, keying line and KISS port."""
        return [claim for claim in self.claims.all() if claim.holder == self.id]
