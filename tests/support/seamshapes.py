"""The shapes the radio round writes against the seams' Protocols (work/par/round/breakdown.md 1.7 to 1.9), typed like the code so that mypy holds the Protocols to them: a radio of the registry whose
members are views of the spec in force (`LiveShape`), a frozen value of a test (`FrozenAir`), a registry whose `enabled` is a list of its own radios (`RegistryShape`), a driver with no modem and one with a
modem, each with a subclass of the line or the modem as a test's double is (`DriverShape`, `ModemDriverShape`). `as_air`, `as_pick` and `as_driver` are where mypy checks each against its Protocol."""
from dataclasses import dataclass, field
from typing import Any

from neoaprs import ax25
from neoaprs.claims import Claim
from neoaprs.config import Config
from neoaprs.mercurymodem import Mercury
from neoaprs.packet import Packet
from neoaprs.radiodriver import RadioDriver, RunOverrides
from neoaprs.radiospec import RadioSpec, log_name
from neoaprs.radiotype import Allowed, Kind, Limits, RadioId
from neoaprs.services.radioset import AirRadio, RadioPick
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from neoaprs.tncwatchdog import TncStats


class LineOfTest(Tnc):
    """A test's own line: a subclass of Tnc."""


class ModemOfTest(Mercury):
    """A test's own modem: a subclass of Mercury."""


class LiveShape:
    """A radio of the registry as 1.7 has it: its id, kind, name, limits and allowed read from the spec in force (a rename or a change of type replaces the spec), the rest from its line."""
    def __init__(self, spec: RadioSpec, specs: tuple[RadioSpec, ...], line: Tnc) -> None:
        self.spec, self.specs, self.line = spec, specs, line

    @property
    def id(self) -> RadioId:
        return self.spec.id

    @property
    def kind(self) -> Kind:
        return self.spec.kind

    @property
    def name(self) -> str:
        return log_name(self.spec, self.specs)

    @property
    def limits(self) -> Limits:
        return self.spec.rtype.limits

    @property
    def allowed(self) -> Allowed:
        return self.spec.rtype.allowed

    @property
    def stats(self) -> TncStats:
        return self.line.stats

    @property
    def state(self) -> Source.State:
        return self.line.state

    @property
    def usable(self) -> bool:
        return self.line.usable

    @property
    def max_frame(self) -> int | None:
        return self.limits.max_frame

    def why_unusable(self) -> str:
        return self.line.why_unusable()

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        return self.line.send_frame(frame, raw)

    def choice(self, key: str) -> Any:
        return self.spec.value(key)


@dataclass(frozen=True)
class FrozenAir:
    """A radio as a test writes one: a frozen value that sends nothing."""
    spec: RadioSpec
    id: RadioId
    kind: Kind
    name: str
    limits: Limits
    allowed: Allowed
    state: Source.State = Source.State.CONNECTED
    usable: bool = True
    stats: TncStats = field(default_factory=TncStats)

    @property
    def max_frame(self) -> int | None:
        return self.limits.max_frame

    def why_unusable(self) -> str:
        return ""

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        return True

    def choice(self, key: str) -> Any:
        return self.spec.value(key)


def frozen_air(spec: RadioSpec) -> FrozenAir:
    t = spec.rtype
    return FrozenAir(spec, spec.id, spec.kind, t.name, t.limits, t.allowed)


class RegistryShape:
    """The registry as 1.7 has it: `enabled` gives its own radios as a list."""
    def __init__(self, radios: list[LiveShape]) -> None:
        self.radios = radios

    def get(self, id: RadioId) -> LiveShape | None:
        return next((r for r in self.radios if r.id == id), None)

    def enabled(self) -> list[LiveShape]:
        return [r for r in self.radios if r.spec.enabled and not r.spec.removed]

    def senders(self) -> list[LiveShape]:
        return [r for r in self.enabled() if r.spec.rtype.can.transmit]

    @property
    def main(self) -> LiveShape | None:
        on = self.enabled()
        return on[0] if on else None

    def for_station(self, call: str) -> LiveShape | None:
        return self.main

    def for_packet(self, packet: Packet) -> LiveShape | None:
        return self.get(packet.radio_id) if packet.radio_id is not None else None

    def email(self) -> LiveShape | None:
        return self.main


class _Driver:
    """What both drivers of a test have: a test's own line, the settings they were given."""
    def __init__(self, line: LineOfTest) -> None:
        self.line = line
        self.configured: list[tuple[RadioSpec, Config, RunOverrides]] = []

    def configure(self, spec: RadioSpec, station: Config, run: RunOverrides) -> None:
        self.configured.append((spec, station, run))

    def restart_key(self, spec: RadioSpec, station: Config, run: RunOverrides) -> tuple[object, ...]:
        return (spec.type, spec.value("port"), station.serial_skip_paths, station.serial_pattern, run.port)

    def words(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        return f"{spec.type} on {spec.value('port') or 'a port found'}"

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def held(self) -> list[Claim]:
        return []


class DriverShape(_Driver):
    """A driver of a type with no modem."""
    modem = None
    card = None


class ModemDriverShape(_Driver):
    """A driver with a test's own modem, a plain attribute."""
    def __init__(self, line: LineOfTest, modem: ModemOfTest) -> None:
        super().__init__(line)
        self.modem = modem
        self.card = None


def as_air(radio: LiveShape | FrozenAir) -> AirRadio:
    return radio


def as_pick(registry: RegistryShape) -> RadioPick:
    return registry


def as_driver(driver: DriverShape | ModemDriverShape) -> RadioDriver:
    return driver
