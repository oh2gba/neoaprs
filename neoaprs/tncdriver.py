"""The driver of a radio whose line is a TNC: a serial TNC, KISS over TCP, or the Dummy radio.

`line_settings` turns the radio's and the station's settings into its Tnc's; the port the search
found is radio 1's (serial/last_port), like the port given for this run.
"""

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

PROFILES: dict[str, Profile] = EVERY_BY_KEY


class TncSettings(NamedTuple):
    port: str  # where to open the radio; "" to listen to the ports for it
    baud: int
    profile: Profile
    fallback_probe: bool  # when the port cannot be opened, search for the radio
    skip: tuple[str, ...]  # serial/skip
    pattern: str  # serial/pattern


def profile_of(spec: RadioSpec) -> Profile:
    return PROFILES[spec.rtype.profile]


def _own(spec: RadioSpec, key: str, default: Any = "") -> Any:
    return spec.value(key) if kind_field(spec.kind, key) is not None else default


def line_settings(spec: RadioSpec, station: Config, run: RunOverrides) -> TncSettings:
    """Return what the radio's Tnc is started with.

    A port given for this run is the only one tried; else the radio's port, else the last found.
    """
    pattern = run.pattern or search_pattern(station.serial_pattern)
    profile = profile_of(spec)
    baud = _own(spec, "baud", None) or profile.baud or 9600
    first = spec.id == FM_ID
    if first and run.port and profile.transport != "dummy":
        return TncSettings(run.port, baud, profile, False, station.serial_skip_paths, pattern)
    if profile.transport == "dummy":
        return TncSettings(DUMMY_PATH, baud, profile, False, station.serial_skip_paths, pattern)
    port = _own(spec, "port")
    if profile.transport == "tcp":
        # empty until the board's address is typed: the radio then opens nothing
        host = _own(spec, "tcp_host")
        return TncSettings(port if names_tcp(port) else tcp_url(host, _own(spec, "tcp_port", 0)) if host else "", baud, profile, False, station.serial_skip_paths, pattern)
    named = port or (_remembered(station, spec.id) if first else "")
    # the search leaves out what other radios hold or are set to (Claims.others)
    return TncSettings(named, baud, profile, profile.search, station.serial_skip_paths, pattern)


def _remembered(station: Config, mine: RadioId) -> str:
    """Return the port radio 1's search found last time; "" once another radio or GPS uses it."""
    last, gps = station.serial_last_port, claim_value(station.gps_device) if station.gps_source == "serial" else None
    others = {c.value for c in named_ports(station) if c.holder != mine} | ({gps} if gps else set())
    return "" if last and claim_value(last) in others else last


def remembered(spec: RadioSpec, station: Config, run: RunOverrides) -> bool:
    """Return whether the port is only the one radio 1's search found (serial/last_port)."""
    return not run.port and profile_of(spec).transport == "serial" and not _own(spec, "port") and bool(line_settings(spec, station, run).port)


def radio_words(settings: TncSettings) -> str:
    """Return a radio's settings for the log: what it is and where it is reached."""
    where = settings.port or (f"the first port that matches {settings.pattern} and {'prints heard packets' if settings.profile.framing == 'text' else 'talks KISS'}" if settings.profile.search and settings.profile.transport == "serial" else "no port chosen yet")
    return f"{settings.profile.name},{where}{'' if settings.profile.transport != 'serial' else f' at {settings.baud} baud'}"


def apply_tnc_settings(tnc: Tnc, settings: TncSettings) -> None:
    tnc.port, tnc.baud, tnc.profile, tnc.fallback_probe, tnc.skip, tnc.pattern = settings


class TncDriver:
    def __init__(self, spec: RadioSpec, claims: Claims, clock: Clock = utcnow, line: Tnc | None = None, *, search_lock: asyncio.Lock | None = None) -> None:
        self.id = spec.id
        self.claims = claims
        # the registry's lock: one radio searches the ports at a time
        self.search_lock = search_lock if search_lock is not None else asyncio.Lock()
        self._line = line if line is not None else Tnc(clock=clock)
        self._line.radio_id = spec.id
        self._line.claims, self._line.search_lock = claims, self.search_lock

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
        """Return the line's settings: a change restarts the line.

        Other radios' settings do not count; the search reads them when it lists the ports.
        """
        return (line_settings(spec, station, run),)

    def words(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        return radio_words(line_settings(spec, station, run))

    async def start(self) -> None:
        await self._line.start()

    async def stop(self) -> None:
        await self._line.stop()

    def held(self) -> list[Claim]:
        return [claim for claim in self.claims.all() if claim.holder == self.id]

    def found_port(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        """Return the port the search found, to try first next time, or "" if there is none."""
        if self._line.state is not Source.State.CONNECTED or (spec.id == FM_ID and run.port) or profile_of(spec).transport != "serial":
            return ""
        path = self._line.path
        return path if path and path not in (_own(spec, "port"), station.serial_last_port) else ""
