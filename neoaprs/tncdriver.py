"""The driver of a radio whose line is a TNC (neoaprs/radiodriver.py; plan §2, "Type"): a TNC on a serial line, KISS over TCP, the Dummy radio. How the radio's settings and the station's become its Tnc's
(`line_settings`, and `tnc_settings` for radio 1 of today's flat settings), its words for the log (`radio_words`), and the port its search found, which the composition root remembers (`TncDriver.found_port`).

The radio's own settings are read from its spec (the port, the speed, the TCP server); what stays the station's from the station's settings: the globs of the search and the ports it never opens
(serial/pattern, serial/skip), and until the radios are stored (package D1a) the port the search found last time, which is radio 1's (serial/last_port). The port given for this run (`RunOverrides.port`) is
radio 1's."""
import asyncio
import logging
from typing import Any, NamedTuple

from .claims import Claim, Claims
from .clock import Clock, utcnow
from .config import Config
from .dummyline import DUMMY_PATH
from .radiodriver import RunOverrides
from .radiospec import FM_ID, RadioSpec
from .radiotypes import kind_field
from .serialprobe import search_pattern
from .source import Source
from .tnc import Tnc
from .tncprofile import BY_KEY, HF_BY_KEY, Profile, names_tcp, tcp_url

log = logging.getLogger("neoaprs.tncdriver")

PROFILES: dict[str, Profile] = {**BY_KEY, **HF_BY_KEY}      # what a type's line is told (RadioType.profile is a key of tncprofile.py)


class TncSettings(NamedTuple):
    port: str                   # where to open the radio, "" to listen to the ports for it
    baud: int
    profile: Profile            # what the TNC is: how to switch it to KISS, whether it may be asked if it is there
    fallback_probe: bool        # when the port cannot be opened, listen to the ports for the radio
    skip: tuple[str, ...]       # ports the search never opens (serial/skip)
    pattern: str                # the globs of the ports the search listens to (serial/pattern)


def profile_of(spec: RadioSpec) -> Profile:
    """The profile of the radio's type (RadioTypeError for a type that is none)."""
    return PROFILES[spec.rtype.profile]


def _own(spec: RadioSpec, key: str, default: Any = "") -> Any:
    """The radio's own setting of this key; `default` for a kind that has no such setting (a kind with no port has no speed)."""
    return spec.value(key) if kind_field(spec.kind, key) is not None else default


def line_settings(spec: RadioSpec, station: Config, run: RunOverrides) -> TncSettings:
    """What the radio's Tnc is started with. A port given for this run (radio 1's) is the only one tried; otherwise the radio's port, else the one the search found last time (and a port that cannot be
    opened is followed by the search). The search listens to the ports of the run's pattern when the process was given one, else of NEOAPRS_SERIAL_PATTERN when that is set, else of serial/pattern. A TCP type
    connects to the radio's TCP server (or to the `tcp://` address in its port) and never searches. The Dummy radio opens nothing, and no port is chosen for it."""
    pattern = run.pattern or search_pattern(station.serial_pattern)
    profile = profile_of(spec)
    baud = _own(spec, "baud", None) or profile.baud or 9600
    first = spec.id == FM_ID                                    # (radio 1 has the port of the run and, until the radios are stored, the port the search remembered)
    if first and run.port and profile.transport != "dummy":
        return TncSettings(run.port, baud, profile, False, station.serial_skip_paths, pattern)
    if profile.transport == "dummy":
        return TncSettings(DUMMY_PATH, baud, profile, False, station.serial_skip_paths, pattern)
    port = _own(spec, "port")
    if profile.transport == "tcp":
        return TncSettings(port if names_tcp(port) else tcp_url(_own(spec, "tcp_host"), _own(spec, "tcp_port", 0)), baud, profile, False, station.serial_skip_paths, pattern)
    return TncSettings(port or (station.serial_last_port if first else ""), baud, profile, True, station.serial_skip_paths, pattern)


def tnc_settings(config: Config, port_override: str = "", pattern_override: str = "") -> TncSettings:
    """What the FM radio of today's flat settings is started with: `line_settings` of radio 1."""
    spec = config.radio(FM_ID)
    assert spec is not None, "the flat settings have radio 1"
    return line_settings(spec, config, RunOverrides(port=port_override, pattern=pattern_override))


def radio_words(settings: TncSettings) -> str:
    """A radio's settings for the log: what it is and where it is reached (a port, a device path, an address: nothing secret)."""
    where = settings.port or f"the first port that matches {settings.pattern} and talks KISS"
    return f"{settings.profile.name},{where}{'' if settings.profile.transport != 'serial' else f' at {settings.baud} baud'}"


def apply_tnc_settings(tnc: Tnc, settings: TncSettings) -> None:
    """For a Tnc that is stopped."""
    tnc.port, tnc.baud, tnc.profile, tnc.fallback_probe, tnc.skip, tnc.pattern = settings


class TncDriver:
    def __init__(self, spec: RadioSpec, claims: Claims, clock: Clock = utcnow, line: Tnc | None = None, *, search_lock: asyncio.Lock | None = None) -> None:
        self.id = spec.id
        self.claims = claims
        self.search_lock = search_lock if search_lock is not None else asyncio.Lock()   # the registry's: one radio searches the ports at a time (the line takes it with the claims: package C2)
        self._line = line if line is not None else Tnc(clock=clock)        # (a line made elsewhere: the process's own for radio 1, a test's)
        self._line.radio_id = spec.id

    @property
    def line(self) -> Tnc:
        return self._line

    @property
    def modem(self) -> None:
        return None

    def configure(self, spec: RadioSpec, station: Config, run: RunOverrides) -> None:
        apply_tnc_settings(self._line, line_settings(spec, station, run))
        self._line.set_check(run.check_sec)

    def restart_key(self, spec: RadioSpec, station: Config, run: RunOverrides) -> tuple[object, ...]:
        """Its line's settings: a change of the port, the speed, the type, the search's pattern or the ports to skip restarts it, and nothing of another radio's."""
        return (line_settings(spec, station, run),)

    def words(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        return radio_words(line_settings(spec, station, run))

    async def start(self) -> None:
        await self._line.start()

    async def stop(self) -> None:
        await self._line.stop()

    def held(self) -> list[Claim]:
        """What the station's table says this radio holds (the Tnc claims the port it opened: package C2)."""
        return [claim for claim in self.claims.all() if claim.holder == self.id]

    def found_port(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        """The port the search found, to be tried first next time; "" while the line is not connected, for a port that was named (the settings, or the run's) and opened, for the one already remembered, and for a
        type that is no serial line."""
        if self._line.state is not Source.State.CONNECTED or (spec.id == FM_ID and run.port) or profile_of(spec).transport != "serial":
            return ""
        path = self._line.path
        return path if path and path not in (_own(spec, "port"), station.serial_last_port) else ""
