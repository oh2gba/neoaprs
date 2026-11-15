"""The driver of a radio whose modem is the Mercury program (neoaprs/radiodriver.py; plan §2, "Type"): the Mercury HF modem, and the Dummy HF radio, which the same program is the speaker of. The modem is
started before the line, because it chooses the ports the line then connects to (a port given for this run is a Mercury something else runs; for the Dummy HF radio the program plays the frames and the line
opens nothing); a modem that cannot be started is said in the log and the line is started all the same: it keeps trying its port. The two are stopped together.

How the radio's settings become its line's is `modem_settings` (and `hf_settings` for radio 2 of today's flat settings), its words for the log `modem_words` (`hf_words`). A change of the sound card, the keying,
the type or the modem's port restarts the radio, and a change of the transmit gain only while nothing can set it live (`Mercury.live_gain`); the sound card and the keying the running modem chose for itself are
no change when the settings come to name exactly those (`MercuryDriver.made_explicit`). The port given for this run (`RunOverrides.hf_port`) is radio 2's."""
import logging
from dataclasses import replace
from pathlib import Path
from typing import NamedTuple

from . import nodevices
from .claims import Claim, Claims
from .clock import Clock, utcnow
from .config import DEFAULTS, Config
from .dummyline import DUMMY_PATH
from .mercury import BROADCAST_PORT
from .mercurymodem import HOST, Mercury
from .radiodriver import RunOverrides
from .radiospec import HF_ID, RadioSpec
from .tnc import Tnc
from .tncprofile import HF_BY_KEY, MERCURY, Profile, tcp_url

log = logging.getLogger("neoaprs.controller")        # what the start of a radio says is the controller's, whoever does it

NO_MERCURY = "the HF radio has no line to a Mercury: none is started, and none was given for this run (--hf-port)"       # what the no-devices switch says of the HF radio's port (modem_settings)
SPEED = 9600                                         # the line's speed, which a TCP line and the dummy line do not use


class ModemSettings(NamedTuple):
    port: str                               # the modem's KISS port as the line opens it; "" when there is none to open
    profile: Profile
    modem: tuple[str, str] = ("", "")       # what the modem is given: the sound card and the keying; empty for the Dummy HF radio


def _attached(spec: RadioSpec, run: RunOverrides) -> str:
    """The Mercury that something else runs, given for this run: radio 2's."""
    return run.hf_port if spec.id == HF_ID else ""


def modem_settings(spec: RadioSpec, run: RunOverrides, modem_port: int = BROADCAST_PORT) -> ModemSettings:
    """What the radio's line is started with: its type's profile, reached on `modem_port` (the broadcast port the modem chose for the program it starts), or at the `socket://` address given for this run (a
    Mercury that something else runs, the benches'); its sound card and keying go with it, so that a change of them restarts the modem. It never searches. The Dummy HF radio opens nothing. Under the no-devices
    switch the daemon starts no Mercury, so without an address given for this run the radio has no port at all: whatever listens where a Mercury of ours would have been, the operator's own modem on this
    computer's port 8100 for one, is not ours and is never connected to."""
    profile = HF_BY_KEY[spec.rtype.profile]
    if profile.transport == "dummy":
        return ModemSettings(DUMMY_PATH, profile)
    attached = _attached(spec, run)
    no_line = not attached and (nodevices.refused(NO_MERCURY, logging.INFO) if spec.enabled else nodevices.on())       # (said in the log only while there is an HF radio to say it of)
    return ModemSettings(attached or ("" if no_line else tcp_url(HOST, modem_port)), profile, (spec.value("sound_card"), spec.value("keying")))


def _hf(config: Config) -> RadioSpec:
    spec = config.radio(HF_ID)
    assert spec is not None, "the flat settings have radio 2"
    return spec


def hf_settings(config: Config, port_override: str = "", modem_port: int = BROADCAST_PORT) -> ModemSettings:
    """What the HF radio of today's flat settings is started with: `modem_settings` of radio 2."""
    return modem_settings(_hf(config), RunOverrides(hf_port=port_override), modem_port)


def modem_words(spec: RadioSpec, run: RunOverrides) -> str:
    """The radio that is started, for the log: the Mercury modem (the daemon's own, which under the no-devices switch is not started, or one something else runs at the address given for this run) or the
    Dummy HF radio."""
    if HF_BY_KEY[spec.rtype.profile].transport == "dummy":
        return "the Dummy HF radio, made-up stations" + ("" if nodevices.on() else ", and the modem played through the speakers")
    if attached := _attached(spec, run):
        return f"the Mercury modem, one something else runs at {attached}"
    return "the Mercury modem, which is not started" if nodevices.on() else "the Mercury modem, started by NeoAPRS"


def hf_words(config: Config, port_override: str) -> str:
    """The HF radio of today's flat settings, for the log: `modem_words` of radio 2."""
    return modem_words(_hf(config), RunOverrides(hf_port=port_override))


class MercuryDriver:
    def __init__(self, spec: RadioSpec, claims: Claims, folder: Path, clock: Clock = utcnow, line: Tnc | None = None, *, modem: Mercury | None = None, data_dir: Path | None = None) -> None:
        self.id = spec.id
        self.claims = claims
        self._line = line if line is not None else Tnc(clock=clock, profile=MERCURY)                                              # (a line and a modem made elsewhere: a test's)
        self._modem = modem if modem is not None else Mercury(data_dir or folder, clock, claims=claims, holder=spec.id, folder=folder)       # (its files in the radio's own folder; what an older NeoAPRS left in the data folder is radio 2's)
        self._line.radio_id = spec.id
        self._line.modem = self._modem                 # (the line asks it why no frame is to go now; the Dummy HF radio's line plays its frames through it)
        self._spec, self._station, self._run = spec, DEFAULTS, RunOverrides()       # what `configure` gave last: `start` starts the modem with it

    @property
    def line(self) -> Tnc:
        return self._line

    @property
    def modem(self) -> Mercury:
        return self._modem

    def configure(self, spec: RadioSpec, station: Config, run: RunOverrides) -> None:
        self._spec, self._station, self._run = spec, station, run
        self._point()
        self._line.set_check(run.check_sec)

    def _point(self) -> None:
        """The line, which is stopped, takes its settings: the modem's port as it is now."""
        settings = modem_settings(self._spec, self._run, self._modem.broadcast_port)
        self._line.port, self._line.baud, self._line.profile, self._line.fallback_probe, self._line.skip, self._line.pattern = settings.port, SPEED, settings.profile, False, (), ""

    def restart_key(self, spec: RadioSpec, station: Config, run: RunOverrides) -> tuple[object, ...]:
        """Its line's settings with the sound card and the keying, and the transmit gain while nothing can set it live (the modem then has it from its ini, at a start)."""
        return (modem_settings(spec, run, self._modem.broadcast_port), None if self._modem.live_gain else spec.value("tx_gain_db"))

    def made_explicit(self, before: RadioSpec, after: RadioSpec) -> RadioSpec:
        """`before`, with the sound card and the keying that the running modem has chosen for itself (the settings were empty) taken as set where `after` sets exactly those: the page stores the daemon's proposal
        as the setting, which changes nothing the modem does, so it is no reason to restart it."""
        if self._modem.state not in ("starting", "running"):
            return before
        card, keying = before.value("sound_card"), before.value("keying")
        if card == "" and after.value("sound_card") == self._modem.sound_card:
            card = self._modem.sound_card
        if keying == "" and after.value("keying") == self._modem.keying.text:
            keying = self._modem.keying.text
        return replace(before, settings={**before.settings, "sound_card": card, "keying": keying})

    def words(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        return modem_words(spec, run)

    def _modem_config(self) -> Config:
        """The station's settings with this radio's own as the modem reads them (its sound card, its keying, its gain)."""
        station, own = self._station, (self._spec.value("sound_card"), self._spec.value("keying"), self._spec.value("tx_gain_db"))
        if own == (station.mercury_sound_card, station.mercury_keying, station.mercury_tx_gain_db):
            return station                             # (radio 2 of today's flat settings: they are the station's own)
        return replace(station, mercury_sound_card=own[0], mercury_keying=own[1], mercury_tx_gain_db=own[2])

    async def start(self) -> None:
        try:
            await self._modem.start(self._modem_config(), _attached(self._spec, self._run), speaker=self._spec.rtype.dummy)       # (the modem first: it chooses the ports the line then connects to)
        except Exception:
            log.exception("the Mercury modem could not be started")        # (the radio is started all the same: it keeps trying its port)
        self._point()
        await self._line.start()

    async def stop(self) -> None:
        await self._line.stop()
        await self._modem.stop()

    def held(self) -> list[Claim]:
        """What the station's table says this radio holds (the modem claims its sound card, its keying line and its pair of ports)."""
        return [claim for claim in self.claims.all() if claim.holder == self.id]
