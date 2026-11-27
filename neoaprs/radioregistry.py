"""The radios of the station at run time: `LiveRadio` and the `RadioRegistry` that manages them.

The registry makes and drops radios as the settings change (`sync`), runs one lifecycle for every
type (`restart`) and is the one place that chooses a radio for a message, a packet or an email.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from . import ax25, beaconrule, direwolfprogram, emailrule, messagerule, nodevices, radiotypes
from .claims import Claims
from .clock import Clock, utcnow
from .coded import Reason
from .config import Config
from .direwolfdriver import DirewolfDriver
from .mercuryclaims import radio_folder
from .mercurydriver import MercuryDriver
from .mercurymodem import Mercury
from .packet import Packet
from .radiodriver import RadioDriver, RunOverrides
from .radiospec import RadioId, RadioSpec, live, log_label, log_name, told, transmits
from .radiotype import Allowed, Kind, Limits, RadioType, RadioTypeError
from .signal import Signal
from .source import Source
from .station import Station
from .stationbook import StationBook
from .stationchoices import StationChoices
from .tnc import Tnc
from .serialprobe import named_ports
from .tncdriver import TncDriver
from .tncwatchdog import TncStats

log = logging.getLogger("neoaprs.controller")

# The driver factory by RadioType.driver; the last argument is the shared search lock.
DRIVERS: dict[
    str, Callable[[RadioSpec, Claims, Clock, Path, Tnc | None, Mercury | None, asyncio.Lock], RadioDriver]
] = {
    "tnc": lambda spec, claims, clock, data_dir, line, modem, lock: TncDriver(
        spec, claims, clock, line, search_lock=lock
    ),
    "mercury": lambda spec, claims, clock, data_dir, line, modem, lock: MercuryDriver(
        spec, claims, radio_folder(data_dir, spec.id), clock, line, modem=modem, data_dir=data_dir
    ),
    "direwolf": lambda spec, claims, clock, data_dir, line, modem, lock: DirewolfDriver(
        spec, claims, radio_folder(data_dir, spec.id), clock, line
    ),
}
# Whether this installation carries the driver's program; an unlisted driver needs none.
CARRIED: dict[str, Callable[[], bool]] = {"direwolf": lambda: direwolfprogram.find() is not None}
# The `why` of a radio that the settings no longer have, and of one they have newly.
REMOVED, NEW = "it is removed", "it is new"
# Log names of line settings whose field name does not say enough.
_SHOWN = {"skip": "ports to skip", "pattern": "search pattern", "fallback_probe": "search when the port fails"}


def known_type(spec: RadioSpec) -> RadioType | None:
    """Return the radio's type, or None for a type this build lacks (a newer version's row)."""
    try:
        return spec.rtype
    except RadioTypeError:
        return None


def is_dummy(spec: RadioSpec) -> bool:
    """Return True if the radio is of a Dummy type, which makes up its traffic."""
    return (rtype := known_type(spec)) is not None and rtype.dummy


def unavailable_types() -> tuple[str, ...]:
    """Return the keys of types this installation cannot run (no-devices: by system only)."""
    by_system = radiotypes.unavailable_types()
    return (
        by_system
        if nodevices.on()
        else (
            *by_system,
            *(
                t.key
                for t in radiotypes.TYPES
                if t.key not in by_system and t.driver in CARRIED and not CARRIED[t.driver]()
            ),
        )
    )


def driver_key(spec: RadioSpec) -> str:
    """Return the key in DRIVERS of the radio's driver."""
    return spec.rtype.driver


def make_driver(
    spec: RadioSpec,
    claims: Claims,
    clock: Clock,
    data_dir: Path,
    line: Tnc | None = None,
    modem: Mercury | None = None,
    *,
    search_lock: asyncio.Lock | None = None,
) -> RadioDriver:
    """Return the driver of the radio's type; `line` and `modem` are given by tests."""
    key = driver_key(spec)
    if key not in DRIVERS:
        raise RadioTypeError(
            f"the type {spec.type!r} names the driver {key!r}, which is none (the drivers are {', '.join(DRIVERS)})",
            "failed",
        )
    return DRIVERS[key](spec, claims, clock, data_dir, line, modem, search_lock or asyncio.Lock())


def _shown(value: object) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, tuple):
        return ", ".join(str(v) or "default" for v in value) or "none"
    # A profile is shown by its name.
    return str(getattr(value, "name", value)) or "none"


def changed_words(before: tuple[object, ...], after: tuple[object, ...]) -> str:
    """Describe what differs for the log, e.g. `port COM3 -> COM4`; arguments are restart keys."""
    old, new = before[0], after[0]
    fields: tuple[str, ...] = getattr(old, "_fields", ()) if type(old) is type(new) else ()
    parts: list[str] = []
    for field in fields:
        was, now = getattr(old, field), getattr(new, field)
        if field == "modem":
            parts += [
                f"{what} {a or 'default'} -> {b or 'default'}"
                for what, a, b in zip(("sound card", "keying"), was, now, strict=True)
                if a != b
            ]
        elif was != now:
            parts.append(f"{_SHOWN.get(field, field)} {_shown(was)} -> {_shown(now)}")
    if before[-1] != after[-1]:
        parts.append(f"switched on or off: {_shown(before[-1])} -> {_shown(after[-1])}")
    return ", ".join(parts) or "nothing the radio shows"


class RadioBeacon(Protocol):
    """What the registry asks of a radio's beacon timer."""

    @property
    def sent(self) -> Signal[[ax25.Frame]]: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def settings_changed(self) -> None: ...


@runtime_checkable
class ChoosesForItself(Protocol):
    """A driver whose radio chooses what its settings leave empty (sound card, keying)."""

    def made_explicit(self, before: RadioSpec, after: RadioSpec) -> RadioSpec:
        """Return `before` with the radio's own choices marked set where `after` has them."""
        ...


B = TypeVar("B", bound=RadioBeacon)


class LiveRadio(Generic[B]):
    """One radio at run time, as services (`AirRadio`), the lifecycle and the page see it."""

    # Its own timer, made by the composition root.
    beacon: B

    def __init__(self, spec: RadioSpec, driver: RadioDriver, specs: Callable[[], tuple[RadioSpec, ...]]) -> None:
        self.id: RadioId = spec.id
        self.driver = driver
        # the DRIVERS key it was made by
        self.driver_key = driver_key(spec)
        # the spec at creation or last sync, used until the settings in force have this radio
        self._made_as = spec
        # The radios of the settings in force.
        self._specs = specs

    @property
    def spec(self) -> RadioSpec:
        """The radio as the settings in force have it."""
        return next((s for s in self._specs() if s.id == self.id), self._made_as)

    @property
    def rtype(self) -> RadioType:
        return self.spec.rtype

    @property
    def line(self) -> Tnc:
        """The Source that packets come from and frames go to."""
        return self.driver.line

    def choice(self, key: str) -> Any:
        """The radio's own value of "beacon", "path" or "digipeat"."""
        return self.spec.value(key)

    # ---- what its spec and its type say
    @property
    def kind(self) -> Kind:
        return self.spec.kind

    @property
    def limits(self) -> Limits:
        return self.rtype.limits

    @property
    def max_frame(self) -> int | None:
        return self.limits.max_frame

    @property
    def allowed(self) -> Allowed:
        return self.rtype.allowed

    @property
    def name(self) -> str:
        """The name the page shows and log texts use (radiospec.log_name)."""
        return log_name(self.spec, self._specs())

    @property
    def told(self) -> str:
        """The radio as the log's lines of its life say it: "the LoRa 2 radio (radio 9)"."""
        return told(self.name, self.id)

    # ---- what its line says
    @property
    def stats(self) -> TncStats:
        return self.line.stats

    @property
    def usable(self) -> bool:
        return self.line.usable

    @property
    def state(self) -> Source.State:
        return self.line.state

    def send_frame(self, frame: ax25.Frame, raw: bytes | None = None) -> bool:
        return self.line.send_frame(frame, raw)

    def why_unusable(self) -> str:
        """Return the line's reason with this radio's id and name added."""
        why = self.line.why_unusable()
        return why.but(radio=self.id, name=self.name) if isinstance(why, Reason) else why


class RadioRegistry(StationChoices, Generic[B]):
    def __init__(
        self,
        claims: Claims,
        make_driver: Callable[[RadioSpec], RadioDriver],
        make_beacon: Callable[[LiveRadio[B]], B],
        config: Callable[[], Config],
        book: StationBook,
        remember: Callable[[str], None] = lambda text: None,
        flush: Callable[[], Awaitable[None]] | None = None,
        *,
        clock: Clock = utcnow,
        run: Callable[[], RunOverrides] = RunOverrides,
    ) -> None:
        super().__init__(book, remember, flush, known=lambda id: any(spec.id == id for spec in config().live_radios))
        self.claims = claims
        claims.named, claims.name_of = lambda: named_ports(self._config()), self.name_of
        # One radio searches the ports at a time.
        self.search_lock = asyncio.Lock()
        self._make_driver, self._make_beacon = make_driver, make_beacon
        self._config, self._clock, self._run = config, clock, run
        self._radios: dict[RadioId, LiveRadio[B]] = {}
        # radios the settings no longer have, until their restart has stopped them
        self._leaving: dict[RadioId, LiveRadio[B]] = {}
        self.why: dict[RadioId, str] = {}
        # set by the wiring: connects a radio's signals when it is made or re-driven
        self.wire: Callable[[LiveRadio[B]], None] = lambda radio: None
        self._unknown: set[tuple[RadioId, str]] = set()

    # ---- the radios there are
    def all(self) -> list[LiveRadio[B]]:
        """Return every radio that is not removed, by position."""
        return sorted(self._radios.values(), key=lambda radio: (radio.spec.position, radio.id))

    def get(self, id: RadioId) -> LiveRadio[B] | None:
        return self._radios.get(id)

    def enabled(self) -> list[LiveRadio[B]]:
        """Return the enabled radios by position."""
        return [radio for radio in self.all() if radio.spec.enabled]

    def senders(self) -> list[LiveRadio[B]]:
        """Return the enabled radios that can send, by position."""
        return [radio for radio in self.enabled() if transmits(radio.spec)]

    def _of(self, id: RadioId | None) -> LiveRadio[B] | None:
        return None if id is None else self._radios.get(id)

    def told_of(self, id: RadioId) -> str:
        """Return `LiveRadio.told` of the radio, one leaving included."""
        radio = self._radios.get(id) or self._leaving.get(id)
        return radio.told if radio is not None else f"radio {id}"

    def name_of(self, id: RadioId) -> str:
        """Return the log name of the radio, one leaving included."""
        radio = self._radios.get(id) or self._leaving.get(id)
        return radio.name if radio is not None else f"radio {id}"

    # ---- the choice of a radio
    def for_station(self, call: str) -> LiveRadio[B] | None:
        """Return the radio a message to the station goes out on."""
        config, station = self._config(), self._book.get(call)
        return self._of(
            messagerule.message_radio(
                self.choice(call), station.heard_by if station is not None else {}, config.radios, self._clock()
            )
        )

    def station_of(self, call: str) -> Station | None:
        """Return the station as the book has it, including what each radio heard of it."""
        return self._book.get(call)

    def for_packet(self, packet: Packet) -> LiveRadio[B] | None:
        """Return the radio the packet came on if enabled, else None (ValueError: internet)."""
        if not packet.on_air:
            raise ValueError("a packet from the internet is answered on no radio")
        came = self._of(packet.radio_id)
        return came if came is not None and came.spec.enabled else None

    def beaconing(self) -> list[LiveRadio[B]]:
        """Return the radios the beacon goes out on, by position."""
        config = self._config()
        on = set(beaconrule.beacon_radios(config.radios))
        return [radio for radio in self.enabled() if radio.id in on]

    def email(self) -> LiveRadio[B] | None:
        """Return the radio an email goes out on, or None."""
        config = self._config()
        return self._of(emailrule.email_radio(config.radios, config.email_choice))

    # ---- the lifecycle
    def sync(self, config: Config) -> list[RadioId]:
        """Make and drop radios to match `config`; return the ids to restart (`why` says why)."""
        before, run = self._config(), self._run()
        wanted = {spec.id: spec for spec in live(config.radios) if self._runs(spec)}
        self.why = {}
        for id in [id for id in self._radios if id not in wanted]:
            self._leaving[id] = self._radios.pop(id)
            self.why[id] = REMOVED
        for id, spec in wanted.items():
            radio = self._radios.get(id)
            if radio is None:
                # A radio dropped and back before its restart ran is the same radio, with its line.
                self._radios[id] = self._leaving.pop(id) if id in self._leaving else self._made(spec)
                self.why[id] = NEW
            elif (reason := self._change(radio, before.radio(id) or radio.spec, before, spec, config, run)) is not None:
                self.why[id] = reason
        for id, spec in wanted.items():
            self._radios[id]._made_as = spec
            # the prefix of the line's log lines
            self._radios[id].line.radio_name = log_label(spec, config.radios)
        return list(self.why)

    def _runs(self, spec: RadioSpec) -> bool:
        if known_type(spec) is not None:
            return True
        if (spec.id, spec.type) not in self._unknown:
            self._unknown.add((spec.id, spec.type))
            log.warning(
                "radio %d is of the type %s, which this NeoAPRS does not have: it is left off", spec.id, spec.type
            )
        return False

    def _made(self, spec: RadioSpec) -> LiveRadio[B]:
        radio: LiveRadio[B] = LiveRadio(spec, self._make_driver(spec), lambda: self._config().radios)
        radio.beacon = self._make_beacon(radio)
        self.wire(radio)
        return radio

    def _change(
        self, radio: LiveRadio[B], old: RadioSpec, before: Config, new: RadioSpec, after: Config, run: RunOverrides
    ) -> str | None:
        """Return why the radio must restart for the new settings, or None if nothing changed."""
        if driver_key(new) != radio.driver_key:
            return f"type {old.rtype.name} -> {new.rtype.name}"
        driver = radio.driver
        if isinstance(driver, ChoosesForItself):
            old = driver.made_explicit(old, new)
        was, now = (
            (*driver.restart_key(old, before, run), old.enabled),
            (*driver.restart_key(new, after, run), new.enabled),
        )
        return changed_words(was, now) if was != now else None

    def restart_key(self, id: RadioId, config: Config) -> tuple[object, ...]:
        """Return the radio's driver key and whether it is on, for these settings."""
        radio, spec = self._radios[id], config.radio(id)
        assert spec is not None, f"radio {id} is in the settings"
        return (*radio.driver.restart_key(spec, config, self._run()), spec.enabled)

    def configure(self) -> None:
        """Give every stopped radio the settings in force."""
        config, run = self._config(), self._run()
        for radio in self.all():
            self._of_its_type(radio)
            radio.driver.configure(radio.spec, config, run)

    async def restart(self, id: RadioId) -> None:
        """Stop one radio, take the settings in force, start it if enabled."""
        await self._let_go(id)
        radio = self._radios.get(id)
        if radio is None:
            return
        await radio.driver.stop()
        spec, config, run = radio.spec, self._config(), self._run()
        self._of_its_type(radio)
        radio.driver.configure(spec, config, run)
        if spec.enabled:
            log.info("%s is started: %s", radio.told, radio.driver.words(spec, config, run))
            await radio.driver.start()
        else:
            log.info("%s is off in the settings", radio.told)

    def _of_its_type(self, radio: LiveRadio[B]) -> None:
        """Give a stopped radio a new driver if its type needs another."""
        if driver_key(radio.spec) != radio.driver_key:
            radio.driver, radio.driver_key = self._make_driver(radio.spec), driver_key(radio.spec)
            self.wire(radio)

    async def repoint(self, id: RadioId, *, unless_connected: bool = False) -> None:
        """Restart only the line, after its modem restarted on other ports; an unticked radio's stays."""
        radio = self._radios.get(id)
        if radio is None or not radio.spec.enabled:
            return
        if unless_connected and radio.line.state is Source.State.CONNECTED:
            return
        await radio.line.stop()
        if self._radios.get(id) is not radio or not radio.spec.enabled:
            return
        radio.driver.configure(radio.spec, self._config(), self._run())
        await radio.line.start()

    async def beacons_as_set(self) -> None:
        """Run each radio's beacon while it is on; an unticked one sends nothing."""
        for radio in self.all():
            await (radio.beacon.start() if radio.spec.enabled else radio.beacon.stop())

    async def _let_go(self, id: RadioId) -> None:
        """Stop a removed radio and release what it held; it stays in `_leaving` till done."""
        gone = self._leaving.get(id)
        if gone is None:
            return
        await gone.driver.stop()
        # Wanted again while its line stopped: `sync` took it back.
        if self._leaving.get(id) is not gone:
            return
        await gone.beacon.stop()
        if self._leaving.get(id) is gone:
            self.claims.release(id)
            del self._leaving[id]

    async def stop_all(self) -> None:
        """Stop every radio, including removed ones whose restart did not finish (`_let_go`)."""
        for radio in self.all():
            await radio.driver.stop()
        for id in list(self._leaving):
            await self._let_go(id)
