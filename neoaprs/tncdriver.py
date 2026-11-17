"""The driver of a radio whose line is a TNC (neoaprs/radiodriver.py; plan §2, "Type"): a TNC on a serial line, KISS over TCP, the Dummy radio. How the radio's settings and the station's become its Tnc's
(`line_settings`), its words for the log (`radio_words`), and the port its search found, which the composition root remembers (`TncDriver.found_port`).

The radio's own settings are read from its spec (the port, the speed, the TCP server); what stays the station's from the station's settings: the globs of the search and the ports it never opens
(serial/pattern, serial/skip), and the port the search found last time, which is radio 1's (serial/last_port). The port given for this run (`RunOverrides.port`) is
radio 1's."""
import asyncio
import logging
from typing import Any, NamedTuple

from .claims import Claim, Claims
from .clock import Clock, utcnow
from .config import Config
from .dummyline import DUMMY_PATH
from .radiodriver import RunOverrides
from .radiospec import FM_ID, RadioId, RadioSpec
from .radiotypes import kind_field
from .serialprobe import claim_value, named_ports, search_pattern
from .source import Source
from .tnc import Tnc
from .tncprofile import EVERY_BY_KEY, Profile, names_tcp, tcp_url

log = logging.getLogger("neoaprs.tncdriver")

PROFILES: dict[str, Profile] = EVERY_BY_KEY      # what a type's line is told (RadioType.profile is a key of tncprofile.py)


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
    connects to the radio's TCP server (or to the `tcp://` address in its port), opens nothing while that server has no address, and never searches. The Dummy radio opens nothing, and no port is chosen for it."""
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
        host = _own(spec, "tcp_host")                           # (empty on a LoRa board on the network until its address is typed: then it opens nothing and waits)
        return TncSettings(port if names_tcp(port) else tcp_url(host, _own(spec, "tcp_port", 0)) if host else "", baud, profile, False, station.serial_skip_paths, pattern)
    named = port or (_remembered(station, spec.id) if first else "")
    return TncSettings(named, baud, profile, profile.search, station.serial_skip_paths, pattern)      # (a LoRa board is never searched for; what the other radios hold or are set to, the search leaves out by the station's table: Claims.others)


def _remembered(station: Config, mine: RadioId) -> str:
    """The port radio 1's search found last time, tried first while radio 1 has no port of its own; "" once another enabled radio is set to that device (a USB name that moved to another radio's adapter at a replug)
    or the GPS receiver reads it."""
    last, gps = station.serial_last_port, claim_value(station.gps_device) if station.gps_source == "serial" else None
    others = {c.value for c in named_ports(station) if c.holder != mine} | ({gps} if gps else set())
    return "" if last and claim_value(last) in others else last


def remembered(spec: RadioSpec, station: Config, run: RunOverrides) -> bool:
    """Whether the line's port is only the one radio 1's search found last time (serial/last_port), not the radio's own nor the run's: held by another, it is searched past, not waited for (Tnc.remembered)."""
    return not run.port and profile_of(spec).transport == "serial" and not _own(spec, "port") and bool(line_settings(spec, station, run).port)     # (only radio 1 has one with no port of its own)


def radio_words(settings: TncSettings) -> str:
    """A radio's settings for the log: what it is and where it is reached (a port, a device path, an address: nothing secret)."""
    where = settings.port or (f"the first port that matches {settings.pattern} and {'prints heard packets' if settings.profile.framing == 'text' else 'talks KISS'}" if settings.profile.search and settings.profile.transport == "serial" else "no port chosen yet")
    return f"{settings.profile.name},{where}{'' if settings.profile.transport != 'serial' else f' at {settings.baud} baud'}"


def apply_tnc_settings(tnc: Tnc, settings: TncSettings) -> None:
    """For a Tnc that is stopped."""
    tnc.port, tnc.baud, tnc.profile, tnc.fallback_probe, tnc.skip, tnc.pattern = settings


class TncDriver:
    def __init__(self, spec: RadioSpec, claims: Claims, clock: Clock = utcnow, line: Tnc | None = None, *, search_lock: asyncio.Lock | None = None) -> None:
        self.id = spec.id
        self.claims = claims
        self.search_lock = search_lock if search_lock is not None else asyncio.Lock()   # the registry's: one radio searches the ports at a time (the line takes it with the claims)
        self._line = line if line is not None else Tnc(clock=clock)        # (a line made elsewhere: the process's own for radio 1, a test's)
        self._line.radio_id = spec.id
        self._line.claims, self._line.search_lock = claims, self.search_lock       # (the line leaves out what the others hold, waits for its turn to search, and holds the port it opens)

    @property
    def line(self) -> Tnc:
        return self._line

    @property
    def modem(self) -> None:
        return None

    @property
    def card(self) -> None:
        return None

    def configure(self, spec: RadioSpec, station: Config, run: RunOverrides) -> None:
        apply_tnc_settings(self._line, line_settings(spec, station, run))
        self._line.remembered = remembered(spec, station, run)
        self._line.set_check(run.check_sec)

    def restart_key(self, spec: RadioSpec, station: Config, run: RunOverrides) -> tuple[object, ...]:
        """Its line's settings: a change of the port, the speed, the type, the search's pattern or the ports to skip restarts it; of another radio's settings none (its search reads what the others are set to
        whenever it lists the ports and lets go of one a radio's settings name: Claims.others, tncsearch.let_go), but for radio 1 a port another radio is set to, or the GPS receiver reads, that is the one radio 1's
        search remembered. Whether the port is only the remembered one is not in it: it changes alone only when the radio is set to the port it has open already."""
        return (line_settings(spec, station, run),)

    def words(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        return radio_words(line_settings(spec, station, run))

    async def start(self) -> None:
        await self._line.start()

    async def stop(self) -> None:
        await self._line.stop()

    def held(self) -> list[Claim]:
        """What the station's table says this radio holds (the Tnc claims the port it found or opened)."""
        return [claim for claim in self.claims.all() if claim.holder == self.id]

    def found_port(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        """The port the search found, to be tried first next time; "" while the line is not connected, for a port that was named (the settings, or the run's) and opened, for the one already remembered, and for a
        type that is no serial line."""
        if self._line.state is not Source.State.CONNECTED or (spec.id == FM_ID and run.port) or profile_of(spec).transport != "serial":
            return ""
        path = self._line.path
        return path if path and path not in (_own(spec, "port"), station.serial_last_port) else ""
