"""The driver of a radio whose modem is the Mercury program (Mercury HF or the Dummy HF radio).

The modem starts before the line because it chooses the ports the line connects to.
"""

import logging
from dataclasses import replace
from pathlib import Path
from typing import NamedTuple

from . import nodevices
from .cardlevels import CardLevels, wanted
from .claims import Claim, Claims
from .clock import Clock, utcnow
from .config import DEFAULTS, Config
from .dummyline import DUMMY_PATH
from .mercury import BROADCAST_PORT, HOST
from .mercurymodem import Mercury
from .radiodriver import RunOverrides
from .radiospec import RadioSpec
from .soundmixer import Mixer
from .tnc import Tnc
from .tncprofile import HF_BY_KEY, LINE_SPEED, MERCURY, Profile, tcp_url

log = logging.getLogger("neoaprs.controller")  # radio starts are logged by the controller

NO_MERCURY = "the Mercury radio has no line to a Mercury: none is started, and none was given for this run (--hf-port)"


class ModemSettings(NamedTuple):
    port: str  # "" if none
    profile: Profile
    # sound card and keying; empty for the Dummy radio
    modem: tuple[str, str] = ("", "")


def _attached(spec: RadioSpec, run: RunOverrides) -> str:
    """Return the external Mercury given for this run, for the radio it belongs to."""
    return run.hf_port if spec.id == run.attach_to else ""


def modem_settings(spec: RadioSpec, run: RunOverrides, modem_port: int = BROADCAST_PORT, unchosen: bool = False) -> ModemSettings:
    """Return the line's settings; with no devices or `unchosen` ports there is no port unless given."""
    profile = HF_BY_KEY[spec.rtype.profile]
    if profile.transport == "dummy":
        return ModemSettings(DUMMY_PATH, profile)
    attached = _attached(spec, run)
    no_line = not attached and ((nodevices.refused(NO_MERCURY, logging.INFO) if spec.enabled else nodevices.on()) or unchosen)
    return ModemSettings(attached or ("" if no_line else tcp_url(HOST, modem_port)), profile, (spec.value("sound_card"), spec.value("keying")))


def modem_words(spec: RadioSpec, run: RunOverrides) -> str:
    """Return the started radio's words for the log."""
    if HF_BY_KEY[spec.rtype.profile].transport == "dummy":
        return "the Dummy Mercury radio, made-up stations" + ("" if nodevices.on() else ", and the modem played through the speakers")
    if attached := _attached(spec, run):
        return f"the Mercury modem, one something else runs at {attached}"
    return "the Mercury modem, which is not started" if nodevices.on() else "the Mercury modem, started by NeoAPRS"


def chosen_as_set(before: RadioSpec, after: RadioSpec, state: str, sound_card: str, keying: str) -> RadioSpec:
    """Return `before` with the sound card and keying a running modem chose taken as set.

    The page stores the daemon's proposal as the setting; that must not restart the modem.
    """
    if state not in ("starting", "running"):
        return before
    card, key = before.value("sound_card"), before.value("keying")
    card = sound_card if card == "" and after.value("sound_card") == sound_card else card
    key = keying if key == "" and after.value("keying") == keying else key
    return replace(before, settings={**before.settings, "sound_card": card, "keying": key})


class MercuryDriver:
    def __init__(self, spec: RadioSpec, claims: Claims, folder: Path, clock: Clock = utcnow, line: Tnc | None = None, *, modem: Mercury | None = None, data_dir: Path | None = None,
                 mixer: Mixer | None = None) -> None:
        self.id = spec.id
        self.claims = claims
        self._line = line if line is not None else Tnc(clock=clock, profile=MERCURY)
        self._modem = modem if modem is not None else Mercury(data_dir or folder, clock, claims=claims, holder=spec.id, folder=folder)
        self._line.radio_id = spec.id
        self._line.modem = self._modem
        self._spec, self._station, self._run = spec, DEFAULTS, RunOverrides()
        self._card = CardLevels(self._own_card, lambda: self._modem.starts, mixer, own=self._has_card)

    @property
    def line(self) -> Tnc:
        return self._line

    @property
    def modem(self) -> Mercury:
        return self._modem

    @property
    def card(self) -> CardLevels:
        return self._card

    def _own_card(self) -> str:
        """Return the card whose levels belong to the radio; none for the Dummy or an external Mercury."""
        return self._modem.held_card() if self._has_card() else ""

    def _has_card(self) -> bool:
        """Return whether the radio has its own sound card."""
        return not (self._spec.rtype.dummy or _attached(self._spec, self._run))

    def configure(self, spec: RadioSpec, station: Config, run: RunOverrides) -> None:
        self._spec, self._station, self._run = spec, station, run
        self._point()
        self._line.set_check(run.check_sec)

    def _point(self) -> None:
        """Give the stopped line its settings."""
        settings = modem_settings(self._spec, self._run, self._modem.broadcast_port, not self._modem.ports_chosen)
        self._line.port, self._line.baud, self._line.profile, self._line.fallback_probe, self._line.skip, self._line.pattern = settings.port, LINE_SPEED, settings.profile, False, (), ""

    def restart_key(self, spec: RadioSpec, station: Config, run: RunOverrides) -> tuple[object, ...]:
        """Return the settings whose change restarts the radio."""
        return (modem_settings(spec, run, self._modem.broadcast_port), None if self._modem.live_gain else spec.value("tx_gain_db"))

    def made_explicit(self, before: RadioSpec, after: RadioSpec) -> RadioSpec:
        """Return `before` with the sound card and keying the running modem chose taken as set."""
        return chosen_as_set(before, after, self._modem.state, self._modem.sound_card, self._modem.keying.text)

    def words(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        return modem_words(spec, run)

    def _modem_config(self) -> Config:
        """Return the station's settings with this radio as `configure` gave it."""
        station = self._station
        if station.radio(self._spec.id) == self._spec:
            return station
        return replace(station, radios=tuple(sorted((*(s for s in station.radios if s.id != self._spec.id), self._spec), key=lambda s: s.id)))

    async def start(self) -> None:
        try:
            await self._modem.start(self._modem_config(), _attached(self._spec, self._run), speaker=self._spec.rtype.dummy)
        except Exception:
            log.exception("the Mercury modem could not be started")
        self._point()
        await self._line.start()
        await self._card.start(*wanted(self._spec))

    async def stop(self) -> None:
        await self._card.stop()
        await self._line.stop()
        await self._modem.stop()

    def held(self) -> list[Claim]:
        """Return the claims the station's table lists for this radio."""
        return [claim for claim in self.claims.all() if claim.holder == self.id]
