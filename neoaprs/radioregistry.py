"""The radios of the station at run time, any number of them (plan §2): a `LiveRadio` for every radio of the settings that is not removed, with the driver of its type (neoaprs/radiodriver.py), the line the
driver gives the packets on, and its own beacon timer; and the `RadioRegistry`, which makes and drops them as the settings change (`sync`), brings each up and down by the one lifecycle of every type
(`restart`: stop, take the settings, start while it is enabled), and is the one place that chooses between them: the radio a message to a station goes out on
(neoaprs/messagerule.py) with the operator's own choice for the station, the radio a packet came on for what answers it, and the radio an email goes out on (neoaprs/emailrule.py). It is what the services
see as `RadioPick` and its radios as `AirRadio` (neoaprs/services/radioset.py).

A radio that is not enabled has its LiveRadio all the same, stopped, and is never chosen. What restarts a radio is its driver's word (`RadioDriver.restart_key`) and its tickbox, read for the settings in
force and for the ones a save brings, so that a save restarts the radio it belongs to and no other. The station's table of resources (neoaprs/claims.py) and the lock that lets one radio search at a time
are here, for the drivers and the search.

The registry connects no signal (that is the wiring's alone): `wire` is called for a radio when it is made, and when it is given another driver, and neoaprs/wiring.py connects its line, its modem and its
beacon there. The operator's radio by station is neoaprs/stationchoices.py's: by the radio's id in the state row, any radio of the settings that is not removed."""
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
from .radiospec import FM_ID, HF_ID, RadioId, RadioSpec, live, log_name, transmits
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

log = logging.getLogger("neoaprs.controller")        # what the start and the restart of a radio say is the controller's, as it was

DRIVERS: dict[str, Callable[[RadioSpec, Claims, Clock, Path, Tnc | None, Mercury | None, asyncio.Lock], RadioDriver]] = {      # the driver of a type, by RadioType.driver (the data folder; the last: one radio searches at a time)
    "tnc": lambda spec, claims, clock, data_dir, line, modem, lock: TncDriver(spec, claims, clock, line, search_lock=lock),
    "mercury": lambda spec, claims, clock, data_dir, line, modem, lock: MercuryDriver(spec, claims, radio_folder(data_dir, spec.id), clock, line, modem=modem, data_dir=data_dir),
    "direwolf": lambda spec, claims, clock, data_dir, line, modem, lock: DirewolfDriver(spec, claims, radio_folder(data_dir, spec.id), clock, line),
}
CARRIED: dict[str, Callable[[], bool]] = {"direwolf": lambda: direwolfprogram.find() is not None}     # whether this installation carries the program a driver starts, by RadioType.driver (a wheel installed with pip, a checkout: no Direwolf); a driver not named needs none
_SHOWN = {"skip": "ports to skip", "pattern": "search pattern", "fallback_probe": "search when the port fails"}       # a field of a line's settings as the log names it, where its own name does not say it


def known_type(spec: RadioSpec) -> RadioType | None:
    """The radio's type; None for a type this build does not have (a row a newer NeoAPRS wrote), which runs nothing."""
    try:
        return spec.rtype
    except RadioTypeError:
        return None


def is_dummy(spec: RadioSpec) -> bool:
    """Whether the radio is of a Dummy type, which makes up its traffic; a radio of a type that is none is no Dummy."""
    return (rtype := known_type(spec)) is not None and rtype.dummy


def unavailable_types() -> tuple[str, ...]:
    """The keys of the types this installation cannot run, which the page does not offer and a radio is not added or changed to: those of another system (radiotypes.unavailable_types) and those whose program
    it does not carry. Under the no-devices switch the system alone counts: a bench shows the type's box, and starts no program."""
    by_system = radiotypes.unavailable_types()
    return by_system if nodevices.on() else (*by_system, *(t.key for t in radiotypes.TYPES if t.key not in by_system and t.driver in CARRIED and not CARRIED[t.driver]()))


def driver_key(spec: RadioSpec) -> str:
    """The key in DRIVERS of the radio's driver: its type's."""
    return spec.rtype.driver


def make_driver(spec: RadioSpec, claims: Claims, clock: Clock, data_dir: Path, line: Tnc | None = None, modem: Mercury | None = None, *, search_lock: asyncio.Lock | None = None) -> RadioDriver:
    """The driver of the radio's type, with the radio's own folder (`radios/<id>` in the data folder); `line` and `modem` are ones made elsewhere (a test's); `search_lock` the registry's."""
    key = driver_key(spec)
    if key not in DRIVERS:
        raise RadioTypeError(f"the type {spec.type!r} names the driver {key!r}, which is none (the drivers are {', '.join(DRIVERS)})", "failed")
    return DRIVERS[key](spec, claims, clock, data_dir, line, modem, search_lock or asyncio.Lock())


def _shown(value: object) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, tuple):
        return ", ".join(str(v) or "default" for v in value) or "none"
    return str(getattr(value, "name", value)) or "none"          # (a profile by its name)


def changed_words(before: tuple[object, ...], after: tuple[object, ...]) -> str:
    """What differs between the settings a radio ran on and the ones it is to run on, for the log: `port /dev/ttyUSB0 -> /dev/ttyUSB1, baud 9600 -> 57600`. Each is a driver's `restart_key` with whether
    the radio is on after it: the first of the key is its line's settings by name (tncdriver.TncSettings, mercurydriver.ModemSettings), whose `modem` is the sound card and the keying."""
    old, new = before[0], after[0]
    fields: tuple[str, ...] = getattr(old, "_fields", ()) if type(old) is type(new) else ()
    parts: list[str] = []
    for field in fields:
        was, now = getattr(old, field), getattr(new, field)
        if field == "modem":                                    # (the last field: the modem's sound card and keying, each by its name)
            parts += [f"{what} {a or 'default'} -> {b or 'default'}" for what, a, b in zip(("sound card", "keying"), was, now, strict=True) if a != b]
        elif was != now:
            parts.append(f"{_SHOWN.get(field, field)} {_shown(was)} -> {_shown(now)}")
    if before[-1] != after[-1]:
        parts.append(f"switched on or off: {_shown(before[-1])} -> {_shown(after[-1])}")
    return ", ".join(parts) or "nothing the radio shows"


class RadioBeacon(Protocol):
    """What the registry asks of a radio's beacon timer (services/beacon.py, which the composition root makes: this layer builds no service)."""
    @property
    def sent(self) -> Signal[[ax25.Frame]]: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def settings_changed(self) -> None: ...


@runtime_checkable
class ChoosesForItself(Protocol):
    """A driver whose radio chooses for itself what its settings leave empty (the Mercury modem: its sound card, its keying)."""
    def made_explicit(self, before: RadioSpec, after: RadioSpec) -> RadioSpec:
        """`before` with what the running radio chose for itself taken as set where `after` sets exactly that: storing its choice is no reason to restart it."""
        ...


B = TypeVar("B", bound=RadioBeacon)


class LiveRadio(Generic[B]):
    """One radio at run time: what the services see of it (services/radioset.AirRadio) and what the lifecycle and the page need (its spec in force, its type, its driver, its line, its beacon)."""
    beacon: B                                        # its own timer, made by the composition root when the radio is

    def __init__(self, spec: RadioSpec, driver: RadioDriver, specs: Callable[[], tuple[RadioSpec, ...]]) -> None:
        self.id: RadioId = spec.id
        self.driver = driver
        self.driver_key = driver_key(spec)           # the key of DRIVERS it was made by: a type of another driver gets another one at its next restart
        self._made_as = spec                         # the spec it was made or last synced with: what it is until the settings in force have it
        self._specs = specs                          # the radios of the settings in force

    @property
    def spec(self) -> RadioSpec:
        """The radio as the settings in force have it."""
        return next((s for s in self._specs() if s.id == self.id), self._made_as)

    @property
    def rtype(self) -> RadioType:
        return self.spec.rtype

    @property
    def line(self) -> Tnc:
        """The Source the packets come from and frames go to."""
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
        """What the log calls it (radiospec.log_name): the name typed, else `FM`, `HF 2`."""
        return log_name(self.spec, self._specs())

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
        """Its line's reason, with this radio's id and name among its values: a refusal made of it says which radio."""
        why = self.line.why_unusable()
        return why.but(radio=self.id, name=self.name) if isinstance(why, Reason) else why


class RadioRegistry(StationChoices, Generic[B]):
    def __init__(self, claims: Claims, make_driver: Callable[[RadioSpec], RadioDriver], make_beacon: Callable[[LiveRadio[B]], B], config: Callable[[], Config], book: StationBook,
                 remember: Callable[[str], None] = lambda text: None, flush: Callable[[], Awaitable[None]] | None = None, *, clock: Clock = utcnow,
                 run: Callable[[], RunOverrides] = RunOverrides) -> None:
        super().__init__(book, remember, flush, known=lambda id: any(spec.id == id for spec in config().live_radios))     # (the operator's radio by station: any radio that is not removed)
        self.claims = claims                                                      # the station's one table of resources: what each radio and the GPS receiver hold
        claims.named, claims.name_of = lambda: named_ports(self._config()), self.name_of     # (and what the enabled radios are set to, which the others leave out: claims.py; the radios by their names)
        self.search_lock = asyncio.Lock()                                         # one radio searches the ports at a time
        self._make_driver, self._make_beacon = make_driver, make_beacon
        self._config, self._clock, self._run = config, clock, run
        self._radios: dict[RadioId, LiveRadio[B]] = {}
        self._leaving: dict[RadioId, LiveRadio[B]] = {}                           # the radios the settings no longer have, until their restart has stopped them
        self.why: dict[RadioId, str] = {}                                         # why each radio of the last `sync` is to be restarted, in words for the log
        self.wire: Callable[[LiveRadio[B]], None] = lambda radio: None            # connects a radio's signals (set by the wiring, which alone connects): called when a radio is made or given another driver
        self._unknown: set[tuple[RadioId, str]] = set()                          # the radios of a type this build does not have, told in the log once each

    # ---- the radios there are
    def all(self) -> list[LiveRadio[B]]:
        """Every radio of the settings that is not removed, enabled or not, by position."""
        return sorted(self._radios.values(), key=lambda radio: (radio.spec.position, radio.id))

    def get(self, id: RadioId) -> LiveRadio[B] | None:
        return self._radios.get(id)

    def enabled(self) -> list[LiveRadio[B]]:
        """The radios that are enabled, by position."""
        return [radio for radio in self.all() if radio.spec.enabled]

    def senders(self) -> list[LiveRadio[B]]:
        """The radios that are enabled and can send (radiospec.senders), by position: what a service sends on; a receive-only radio is never among them."""
        return [radio for radio in self.enabled() if transmits(radio.spec)]

    def _of(self, id: RadioId | None) -> LiveRadio[B] | None:
        return None if id is None else self._radios.get(id)

    def name_of(self, id: RadioId) -> str:
        """What the log calls the radio, one the settings no longer have too (until its restart has stopped it)."""
        radio = self._radios.get(id) or self._leaving.get(id)
        return radio.name if radio is not None else f"radio {id}"

    # ---- the choice of a radio
    def for_station(self, call: str) -> LiveRadio[B] | None:
        """The radio a message of ours to the station goes out on (messagerule.message_radio, on what each radio heard of it and the operator's choice for it). A message asks it at its first attempt and keeps
        that radio until it ends, unless the operator's choice for the station in force changes, that radio is switched off, or it only stood in for the station's own (services/messageradio.py)."""
        config, station = self._config(), self._book.get(call)
        return self._of(messagerule.message_radio(self.choice(call), station.heard_by if station is not None else {}, config.radios, self._clock()))

    def station_of(self, call: str) -> Station | None:
        """The station as the book has it: what each radio heard of it, by which a message tells a radio that only stood in for the station's own (services/messageradio.py)."""
        return self._book.get(call)

    def for_packet(self, packet: Packet) -> LiveRadio[B] | None:
        """The radio to answer a packet on: the one it came on, while it is enabled; else none (a radio switched off or removed since the packet came answers nothing: a query is then not answered,
        `radioset.answerable`, and an ack goes on the radio a message to the station takes, `radioset.ack_radio`). A packet from the internet is answered by nothing (`Packet.on_air` is false), and asking
        is a fault. A receive-only radio it came on is given all the same: it takes no frame (`usable` is false, and why says RX only), so a query heard on it alone is not answered either."""
        if not packet.on_air:
            raise ValueError("a packet from the internet is answered on no radio")
        came = self._of(packet.radio_id)
        return came if came is not None and came.spec.enabled else None

    def beaconing(self) -> list[LiveRadio[B]]:
        """The radios the beacon goes out on, by position (beaconrule.beacon_radios: the enabled ones whose Send on is ticked; with one radio on, that one): what Beacon now sends on."""
        config = self._config()
        on = set(beaconrule.beacon_radios(config.radios))
        return [radio for radio in self.enabled() if radio.id in on]

    def email(self) -> LiveRadio[B] | None:
        """The radio an email goes out on (emailrule.email_radio: the operator's choice `email/radio` among the radios that can send); None while no radio that can send is on."""
        config = self._config()
        return self._of(emailrule.email_radio(config.radios, config.email_choice))

    # ---- the lifecycle
    def sync(self, config: Config) -> list[RadioId]:
        """Makes and drops radios to match the live radios of `config`, the settings about to be put in force (or just put: then nothing differs), and says which are to be restarted: a new one, one that
        is gone (its restart stops it for good), and one whose driver's restart key or tickbox differs from the settings in force. `why` has the words of each. A radio of a type this build does not
        have (a row a newer NeoAPRS wrote) is none of them: it is not made, nothing is sent on it, and the daemon writes nothing of its row or its own settings, for the build that knows the type."""
        before, run = self._config(), self._run()
        wanted = {spec.id: spec for spec in live(config.radios) if self._runs(spec)}
        self.why = {}
        for id in [id for id in self._radios if id not in wanted]:
            self._leaving[id] = self._radios.pop(id)
            self.why[id] = "it is removed"
        for id, spec in wanted.items():
            radio = self._radios.get(id)
            if radio is None:
                self._radios[id] = self._leaving.pop(id) if id in self._leaving else self._made(spec)      # (one that was dropped and is back before its restart stopped it is the same radio, its line and beacon with it)
                self.why[id] = "it is new"
            elif (reason := self._change(radio, before.radio(id) or radio.spec, before, spec, config, run)) is not None:
                self.why[id] = reason
        for id, spec in wanted.items():
            self._radios[id]._made_as = spec
            self._radios[id].line.radio_name = "" if id in (FM_ID, HF_ID) else log_name(spec, config.radios)      # (what its line's own log lines begin with: for radios 1 and 2 today's words, `tnc` and `hf radio`, which the line says by its kind)
        return list(self.why)

    def _runs(self, spec: RadioSpec) -> bool:
        if known_type(spec) is not None:
            return True
        if (spec.id, spec.type) not in self._unknown:
            self._unknown.add((spec.id, spec.type))
            log.warning("radio %d is of the type %s, which this NeoAPRS does not have: it is left off", spec.id, spec.type)
        return False

    def _made(self, spec: RadioSpec) -> LiveRadio[B]:
        radio: LiveRadio[B] = LiveRadio(spec, self._make_driver(spec), lambda: self._config().radios)
        radio.beacon = self._make_beacon(radio)
        self.wire(radio)
        return radio

    def _change(self, radio: LiveRadio[B], old: RadioSpec, before: Config, new: RadioSpec, after: Config, run: RunOverrides) -> str | None:
        """Why the radio is to be restarted for the new settings, in words; None when nothing of it changed."""
        if driver_key(new) != radio.driver_key:
            return f"type {old.rtype.name} -> {new.rtype.name}"
        driver = radio.driver
        if isinstance(driver, ChoosesForItself):
            old = driver.made_explicit(old, new)
        was, now = (*driver.restart_key(old, before, run), old.enabled), (*driver.restart_key(new, after, run), new.enabled)
        return changed_words(was, now) if was != now else None

    def restart_key(self, id: RadioId, config: Config) -> tuple[object, ...]:
        """What a change of restarts the radio, for these settings: its driver's key and whether it is on."""
        radio, spec = self._radios[id], config.radio(id)
        assert spec is not None, f"radio {id} is in the settings"
        return (*radio.driver.restart_key(spec, config, self._run()), spec.enabled)

    def configure(self) -> None:
        """Every radio, which is stopped, takes the settings in force (what the parts ask of a radio, such as whether it is a Dummy, is true before any is started)."""
        config, run = self._config(), self._run()
        for radio in self.all():
            self._of_its_type(radio)                              # (a radio made before these settings, of a type of another driver now, gets its type's)
            radio.driver.configure(radio.spec, config, run)

    async def restart(self, id: RadioId) -> None:
        """The one lifecycle of every type: the radio is stopped (its line, and its modem with it), takes the settings in force and is started while it is enabled; one whose tickbox is off stays stopped,
        and one the settings no longer have is stopped for good, its beacon with it. No other radio is touched. The beacons are put as the radios are by `beacons_as_set`, which the controller calls after this."""
        await self._let_go(id)
        radio = self._radios.get(id)
        if radio is None:
            return
        await radio.driver.stop()
        spec, config, run = radio.spec, self._config(), self._run()
        self._of_its_type(radio)
        radio.driver.configure(spec, config, run)
        if spec.enabled:
            log.info("the %s radio is started: %s", radio.name, radio.driver.words(spec, config, run))
            await radio.driver.start()
        else:
            log.info("the %s radio is off in the settings", radio.name)

    def _of_its_type(self, radio: LiveRadio[B]) -> None:
        """A radio, stopped, whose type is now one of another driver gets a new driver made around its settings (the old one is stopped)."""
        if driver_key(radio.spec) != radio.driver_key:
            radio.driver, radio.driver_key = self._make_driver(radio.spec), driver_key(radio.spec)
            self.wire(radio)

    async def repoint(self, id: RadioId) -> None:
        """The radio's modem was started again on other ports: its line alone is stopped, takes the settings again (the modem's port as it is now) and is started."""
        radio = self._radios.get(id)
        if radio is None:
            return
        await radio.line.stop()
        radio.driver.configure(radio.spec, self._config(), self._run())
        await radio.line.start()

    async def beacons_as_set(self) -> None:
        """Each radio's beacon runs while that radio is on and not otherwise (a beacon of a radio that is off would only say, at every due time, why nothing goes). One whose Send on is not ticked runs
        too and sends nothing (its interval in force is 0: services/beacon.py), so that ticking it again, which restarts no radio, puts it on the air at the next save of the settings."""
        for radio in self.all():
            await (radio.beacon.start() if radio.spec.enabled else radio.beacon.stop())

    async def _let_go(self, id: RadioId) -> None:
        """A radio the settings no longer have is stopped for good, its beacon with it, and what it held is let go. It stays among the leaving until all of that is done, so that a daemon stopped
        while its restart is still at it (the restart is cancelled) stops it in `stop_all`."""
        gone = self._leaving.get(id)
        if gone is None:
            return
        await gone.driver.stop()
        if self._leaving.get(id) is not gone:                    # (wanted again while its line stopped: `sync` took it back, its beacon and claims with it)
            return
        await gone.beacon.stop()
        if self._leaving.get(id) is gone:
            self.claims.release(id)
            del self._leaving[id]

    async def stop_all(self) -> None:
        """Every radio is stopped: its line, and its modem with it; one the settings no longer have whose restart did not get so far is stopped for good (`_let_go`)."""
        for radio in self.all():
            await radio.driver.stop()
        for id in list(self._leaving):
            await self._let_go(id)
