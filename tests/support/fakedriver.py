"""A radio of a test for the radio registry (neoaprs/radioregistry.py): a driver that opens nothing and writes down what it is asked (`FakeDriver`), its line (`FakeLine`: a Tnc whose state the driver sets and
that keeps the frames it is given), a beacon that only knows whether it runs (`FakeBeacon`), radios as the settings would have them (`spec`) and settings that have any number of them (`with_radios`:
`Config.radios` is a view of the two radios of the flat keys until they are stored). `registry_of` builds a registry of such radios on a station book.

    radios = [spec(1), spec(2, "hf", enabled=False), spec(3, port="/dev/ttyUSB3")]
    rig = registry_of(with_radios(ON_AIR, radios))
    rig.registry.sync(rig.config)                    # the three radios are made; rig.drivers[3].calls is what its driver was asked, in order
    rig.put(with_radios(ON_AIR, [...]))              # a save: the registry is synced with the new settings and they are put in force; returns the ids to restart

`as_air`, `as_pick` and `as_driver` are where mypy holds the registry, its radios and the drivers of the daemon to the Protocols the services and the registry are written against (the test files are read with
the checks of a value's type off; this module is typed like the code)."""
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import NamedTuple

from neoaprs import ax25
from neoaprs.claims import Claim, Claims
from neoaprs.clock import Clock
from neoaprs.config import Config
from neoaprs.mercurydriver import MercuryDriver
from neoaprs.radiodriver import RadioDriver, RunOverrides
from neoaprs.radioregistry import LiveRadio, RadioRegistry
from neoaprs.radiospec import RadioId, RadioSpec
from neoaprs.radiotype import Kind
from neoaprs.radiotypes import DEFAULT_TYPE
from neoaprs.services.radioset import AirRadio, RadioPick
from neoaprs.signal import Signal
from neoaprs.source import Source, unusable_because
from neoaprs.stationbook import StationBook
from neoaprs.tnc import Tnc
from neoaprs.tncdriver import TncDriver
from tests.support.clock import FixedClock


def spec(id: RadioId, kind: Kind = "fm", type: str = "", name: str = "", enabled: bool = True, position: int | None = None, removed_at: datetime | None = None, **settings: str) -> RadioSpec:
    """A radio as the settings have it: of the kind's default type unless one is named, at the position of its id unless one is given, its own settings as text."""
    return RadioSpec(id, kind, type or DEFAULT_TYPE[kind], name, enabled, id if position is None else position, removed_at, settings)


def with_radios(config: Config, radios: Iterable[RadioSpec]) -> Config:
    """The settings with these radios in the place of the two of the flat keys (a copy: `Config.radios` is worked out once for each Config, and here it is given)."""
    made = replace(config)
    made.__dict__["radios"] = tuple(radios)
    return made


class FakeLine(Tnc):
    """A line that opens nothing: its state is what its driver sets, it is usable while connected, and it keeps the frames it is given."""

    def __init__(self, clock: Clock) -> None:
        super().__init__(clock=clock)
        self.sent: list[ax25.Frame] = []

    @property
    def usable(self) -> bool:
        return self.state is Source.State.CONNECTED

    def why_unusable(self) -> str:
        return unusable_because(self.state)

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        if self.usable:
            self.sent.append(frame)
        return self.usable


class FakeSettings(NamedTuple):
    """What restarts a fake radio, by name (the registry's words of a change read the names)."""
    port: str
    type: str
    skip: tuple[str, ...]


class FakeDriver:
    """A driver that opens nothing: `calls` is what it was asked, in order (`configure`, `start`, `stop`); its line is CONNECTED from its start to its stop."""
    modem = None

    def __init__(self, made_for: RadioSpec, clock: Clock, line: FakeLine | None = None) -> None:
        self.id = made_for.id
        self.line = line if line is not None else FakeLine(clock)
        self.line.radio_id = made_for.id
        self.calls: list[str] = []
        self.configured: list[tuple[RadioSpec, Config, RunOverrides]] = []

    def configure(self, spec: RadioSpec, station: Config, run: RunOverrides) -> None:
        self.calls.append("configure")
        self.configured.append((spec, station, run))

    def restart_key(self, spec: RadioSpec, station: Config, run: RunOverrides) -> tuple[object, ...]:
        return (FakeSettings(spec.settings.get("port", ""), spec.type, station.serial_skip_paths),)

    def words(self, spec: RadioSpec, station: Config, run: RunOverrides) -> str:
        return f"a fake {spec.type} on {spec.settings.get('port') or 'no port'}"

    async def start(self) -> None:
        self.calls.append("start")
        self.line._set_state(Source.State.CONNECTED)

    async def stop(self) -> None:
        self.calls.append("stop")
        self.line._set_state(Source.State.STOPPED)

    def held(self) -> list[Claim]:
        return []


class FakeBeacon:
    """A beacon timer that only knows whether it runs, and how often it was told that the settings changed."""

    def __init__(self, radio: RadioId) -> None:
        self.radio = radio
        self.sent: Signal[[ax25.Frame]] = Signal("fakebeacon.sent")
        self.running = False
        self.settings_changes = 0

    async def start(self) -> None:
        self.running = True

    async def stop(self) -> None:
        self.running = False

    def settings_changed(self) -> None:
        self.settings_changes += 1


@dataclass
class Rig:
    """A registry of fake radios, with what a test looks at: the settings in force, the drivers and the beacons it made by radio, the radios it handed to the wiring, the rows it was asked to keep."""
    config: Config
    clock: FixedClock = field(default_factory=FixedClock)
    book: StationBook = field(init=False)
    claims: Claims = field(default_factory=Claims)
    drivers: dict[RadioId, FakeDriver] = field(default_factory=dict)
    made: list[tuple[RadioId, str]] = field(default_factory=list)            # every driver made: the radio and the type it was made for
    beacons: dict[RadioId, FakeBeacon] = field(default_factory=dict)
    wired: list[RadioId] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    run: RunOverrides = field(default_factory=RunOverrides)
    registry: RadioRegistry[FakeBeacon] = field(init=False)

    def __post_init__(self) -> None:
        self.book = StationBook(self.clock)
        self.registry = RadioRegistry(self.claims, self._driver, self._beacon, lambda: self.config, self.book, self.kept.append, clock=self.clock, run=lambda: self.run)
        self.registry.wire = lambda radio: self.wired.append(radio.id)

    def _driver(self, made_for: RadioSpec) -> RadioDriver:
        old = self.drivers.get(made_for.id)
        driver = self.drivers[made_for.id] = FakeDriver(made_for, self.clock, old.line if old is not None else None)       # (a radio given another driver keeps its line, as radios 1 and 2 of the daemon do)
        self.made.append((made_for.id, made_for.type))
        return driver

    def _beacon(self, radio: LiveRadio[FakeBeacon]) -> FakeBeacon:
        beacon = self.beacons[radio.id] = FakeBeacon(radio.id)
        return beacon

    def put(self, config: Config) -> list[RadioId]:
        """A save, as the controller does it: the registry is synced with the new settings, then they are put in force; the ids to restart."""
        restart = self.registry.sync(config)
        self.config = config
        return restart

    def calls(self) -> dict[RadioId, list[str]]:
        """What each driver was asked since the last look, by radio; the lists are emptied."""
        seen = {id: list(driver.calls) for id, driver in self.drivers.items()}
        for driver in self.drivers.values():
            driver.calls.clear()
        return seen


def registry_of(config: Config) -> Rig:
    """A registry of fake radios for these settings, synced with them."""
    rig = Rig(config)
    rig.registry.sync(config)
    return rig


def as_air(radio: LiveRadio[FakeBeacon]) -> AirRadio:
    return radio


def as_pick(registry: RadioRegistry[FakeBeacon]) -> RadioPick:
    return registry


def as_driver(driver: FakeDriver | TncDriver | MercuryDriver) -> RadioDriver:
    return driver
