"""The daemon (the Controller) on test data, with a clock the test holds and a fake TCP radio on the
loopback.

Every integration test builds its world with `Env`; `stop_all` ends it. Radio 1 is the FM radio,
radio 2 the HF radio; the Tnc is the real one with quick timers and the keep-alive off.
"""

import asyncio
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from tornado.httpclient import AsyncHTTPClient, HTTPClientError, HTTPRequest, HTTPResponse

from neoaprs.clock import Clock
from neoaprs.config import LAST_PORT, Config
from neoaprs.configtypes import boolean
from neoaprs.controller import Controller
from neoaprs.db import Db
from neoaprs.kiss import KissDecoder
from neoaprs.mercurymodem import Mercury
from neoaprs.radioregistry import LiveRadio
from neoaprs.radiospec import FM_ID, HF_ID, RadioId
from neoaprs.radiotype import Kind
from neoaprs.radiotypes import BY_KEY as TYPES, DEFAULT_TYPE
from neoaprs.sendonrule import kept_in_force
from neoaprs.services.beacon import Beacon
from neoaprs.packet import Packet
from neoaprs.source import Backoff, Source
from neoaprs.station import Station
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import MERCURY
from tests.support.webports import next_web_port
from tests.support.patience import PATIENCE_SEC
from tests.support.clock import FixedClock
from tests.support.files import fixture_bytes
from tests.support.fakemercury import FakeMercury
from tests.support.fakeradio import FakeRadio
from tests.support.ptyline import close_pty, feed as feed_pty, heard as heard_pty, make_pty
from tests.support.radioconfig import TWO_RADIOS, with_radio
from tests.support.wsclient import WsClient, connect
from neoaprs.web.server import WebServer

_live: list["Env"] = []
# The Db of every Store the tests opened (tests/support/storedb.py): closed when the test is over
_dbs: list[Db] = []
# The stop of every part a test started by itself (a service on a stub): called when the test is
# over, before the databases are closed
_stops: list[Callable[[], Awaitable[None]]] = []

CAPTURE = "kiss/thd7-2026-10-21.bin"
# The station of the tests, with the TNC the tests are about: with no call set nothing is
# transmitted (config.can_transmit)
OPERATOR = {
    "station/call": "OH2GBA",
    "station/lat": "60.17",
    "station/lon": "24.94",
    "tnc/profile": "kenwood-tnc2",
    "beacon/path": "WIDE1-1,WIDE2-1",
}
# The rows an Env's settings say its radios in, and where each goes: the radio's type or tickbox, or
# its own setting (the HF radio's path as its own too, as migration 31 kept it)
RADIO_ROWS: dict[str, tuple[RadioId, str]] = {
    "tnc/profile": (FM_ID, "type"),
    "fm/enabled": (FM_ID, "enabled"),
    "serial/port": (FM_ID, "port"),
    "serial/baud": (FM_ID, "baud"),
    "tcp/host": (FM_ID, "tcp_host"),
    "tcp/port": (FM_ID, "tcp_port"),
    "beacon/path": (FM_ID, "path"),
    "digi/enabled": (FM_ID, "digipeat"),
    "hf/profile": (HF_ID, "type"),
    "hf/enabled": (HF_ID, "enabled"),
    "mercury/sound_card": (HF_ID, "sound_card"),
    "mercury/keying": (HF_ID, "keying"),
    "mercury/tx_gain_db": (HF_ID, "tx_gain_db"),
}
RADIO_KINDS: dict[RadioId, Kind] = {FM_ID: "fm", HF_ID: "hf"}
# A radio whose tickbox the settings do not say: the FM radio on, the HF radio off
RADIO_ON: dict[RadioId, bool] = {FM_ID: True, HF_ID: False}
# The rows of before that are no station's setting (migration 31 deletes them): never written as the
# station's
GONE = ("tnc/", "hf/", "mercury/", "tcp/")


def first_radios(rows: dict[str, str], hf: bool) -> list[tuple[Kind, str, bool, dict[str, str]]]:
    """The radios an Env's settings say (kind, type, whether it is on, its own settings as text):
    radio 1 always, and radio 2 when `hf` (the Env has its Mercury) or a row names it. A type that
    is no type of the radio's kind is the kind's default, and a tickbox that is no word the radio's
    default, as the settings read them."""
    made: list[tuple[Kind, str, bool, dict[str, str]]] = []
    for id in (FM_ID, *((HF_ID,) if hf or any(key.startswith(("hf/", "mercury/")) for key in rows) else ())):
        kind, homes = (
            RADIO_KINDS[id],
            {
                key: home
                for key, (radio, home) in RADIO_ROWS.items()
                if radio == id or (key == "beacon/path" and id == HF_ID)
            },
        )
        found = {home: rows[key] for key, home in homes.items() if key in rows}
        type = found.pop("type", "")
        rtype = TYPES.get(type.strip())
        try:
            on = boolean(found.pop("enabled")) if "enabled" in found else RADIO_ON[id]
        except ValueError:
            on = RADIO_ON[id]
        made.append((kind, rtype.key if rtype is not None and rtype.kind == kind else DEFAULT_TYPE[kind], on, found))
    return made


# The same as a Config, for the tests that hold one (with radio 2, the HF radio, off): the defaults
# are a station with no call and no radio
ON_AIR: Config = replace(
    with_radio(TWO_RADIOS, FM_ID, "kenwood-tnc2", path="WIDE1-1,WIDE2-1"),
    station_call="OH2GBA",
    station_lat=60.17,
    station_lon=24.94,
)


def _quiet(radio: LiveRadio[Any]) -> None:
    if radio.driver.modem is not None:
        radio.driver.modem.ports = lambda: []


def _quieted(wire: Callable[[LiveRadio[Beacon]], None]) -> Callable[[LiveRadio[Beacon]], None]:
    """The wiring of a radio, which first gives its modem no serial port of the computer to look at."""

    def quiet_then_wire(radio: LiveRadio[Beacon]) -> None:
        _quiet(radio)
        wire(radio)

    return quiet_then_wire


def remember(db: Db) -> None:
    """A Db that a test opened is closed by stop_all() when the test is over, so that a test that
    forgets to close it does not leak a thread."""
    _dbs.append(db)


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        # An Env made by a test that is not async: nothing is running, nothing to stop
        return None


def remember_stop(stop: Callable[[], Awaitable[None]]) -> None:
    """A part that a test starts without an Env (a service on a stub Tnc) is stopped by stop_all()
    when the test is over, so that a test that forgets to does not leak its task."""
    _stops.append(stop)


async def stop_all() -> None:
    """Stops the daemons of the Envs made on this loop, whether or not their tests did (stop() can
    be called again, so those that did are not touched), and closes their radios. Called when a test
    is over, so that a test that failed on the way, or forgot, does not leave a daemon running. The
    Envs of other loops are forgotten."""
    loop = asyncio.get_running_loop()
    mine = [e for e in _live if e.loop is loop]
    _live.clear()
    for e in mine:
        for page in e.pages:
            await page.aclose()
        await e.ctl.stop()
        await e.close_radios()
    stops, _stops[:] = list(_stops), []
    for stop in stops:
        await stop()
    dbs, _dbs[:] = list(_dbs), []
    for db in dbs:
        if db.is_open:
            await db.close()


async def until(condition: Callable[[], object], timeout_sec: float = PATIENCE_SEC) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_sec
    while not condition():
        assert asyncio.get_running_loop().time() < deadline, "the condition did not come true"
        await asyncio.sleep(0.01)


# The longest a test waits for a program it started (the made-up Mercury, a daemon): a busy Windows
# runner takes over 20 s to start one, so this is a limit and not a measure of how long it takes
START_SEC = 60.0


async def until_started(condition: Callable[[], object], timeout_sec: float = START_SEC) -> None:
    """`until` for what depends on a program that was started (its first line, its ports, its
    state): the patience of a start, not of a step of the loop."""
    await until(condition, timeout_sec)


async def until_async(condition: Callable[[], Awaitable[object]], timeout_sec: float = PATIENCE_SEC) -> None:
    """`until` for a condition that has to be awaited (a row of the database)."""
    deadline = asyncio.get_running_loop().time() + timeout_sec
    while not await condition():
        assert asyncio.get_running_loop().time() < deadline, "the condition did not come true"
        await asyncio.sleep(0.01)


async def idle_for(seconds: float) -> None:
    """A wait that is the point: the time in which a timer has had its chance to do something that a
    test then asserts it did not (or in which the loop runs the tasks the test just started). It
    never waits for something that should happen: that is `until`."""
    await asyncio.sleep(seconds)


async def quick_start(
    tmp_path: Path,
    *,
    beacon: bool = False,
    messaging: bool = False,
    rigstatus: bool = False,
    own: bool = False,
    unpaced: bool = False,
    **options: Any,
) -> "Env":
    """A started Env whose Tnc is connected and settled and whose named services tick every 20 ms
    (the beacon, messaging, the status poll, the own objects and bulletins); `unpaced`: and send one
    frame after the other with no pause (the messaging pace, the own sender, and the QRU server's
    wait before its first frame). The other options are the Env's."""
    e = Env(tmp_path, **options)
    if beacon:
        e.beacon.tick_sec, e.beacon.retry_sec = 0.02, 0.05
    if messaging:
        e.ctl.messaging.tick_sec = 0.02
        if unpaced:
            e.ctl.messaging.pace.spacing_sec = 0.0
    if rigstatus:
        e.ctl.rigstatus.poll_sec = e.ctl.rigstatus.tick_sec = 0.02
    if own:
        e.ctl.ownobjects.tick_sec = e.ctl.ownbulletins.tick_sec = 0.02
        if unpaced:
            e.ctl.sender.spacing_sec = 0.0
            e.ctl.qru.first_wait_sec = 0.0
    await e.start()
    await e.until_usable()
    return e


class Env:
    def __init__(
        self,
        tmp_path: Path,
        clock: Clock | None = None,
        radio: bool | str | FakeRadio = True,
        ports: Path | None = None,
        web: bool = False,
        operator: bool = True,
        settings: dict[str, str] | None = None,
        hf: FakeMercury | None = None,
        auto_map: bool = False,
        first_radio: bool = True,
        **tnc_options: Any,
    ) -> None:
        self.dir = tmp_path
        # The rows of the operator's data folder at the first start: a test about the keep-alive
        # turns it on with `check_sec`
        self.settings = {**OPERATOR, **(settings or {})}
        self.operator = operator
        # The Env adds its radios before the first start (False: a new installation before its first
        # radio)
        self.first_radio = first_radio
        self.loop = _running_loop()
        _live.append(self)
        self.now: Clock = clock or FixedClock()
        self._own_ports = ports is None
        # The "/dev" of the test: the radio's path and the places the probe looks in (`ports`: the
        # one of an Env before)
        self.ports = ports or Path(tempfile.mkdtemp(prefix="neoaprs-ports-"))
        self._masters: list[int] = []
        self.master = -1  # the master descriptor of the radio's pty (radio="pty")
        # The port the daemon opens: the radio's url, or the path of its pty
        self.link = ""
        self.radio: FakeRadio | None = None
        # The station of the fake Mercury's air that is this daemon's HF radio (`hf`, or `radio`
        # when that is one: a station with the HF radio alone)
        self.hf_radio: FakeMercury | None = None
        self.hf_link = ""  # what --hf-port is given: the fake Mercury's KISS port
        self._extra_radios: list[FakeRadio] = []
        options: dict[str, Any] = {
            "pattern": str(self.ports / "probe_*"),
            "check_sec": 0.0,
            "settle_sec": 0.15,
            "probe_seconds": 0.3,
            "backoff": Backoff([0.05, 0.05]),
        }
        self.tnc = Tnc(clock=self.now, **{**options, **tnc_options})
        check_sec = float({**options, **tnc_options}["check_sec"])
        # A station of the fake Mercury's air alone: the HF radio, and no FM radio
        if isinstance(radio, FakeMercury):
            hf, radio = radio, False
        if hf is not None:
            self.hf_radio, self.hf_link = hf, hf.url
            self.settings = {**self.settings, "hf/enabled": "true", **({} if radio else {"fm/enabled": "false"})}
        if isinstance(radio, FakeRadio):  # (a radio made elsewhere)
            self.radio = radio
            self.link = radio.url
        elif radio == "pty":
            self.master, self.link = self.new_pty("radio")
        elif radio:
            self.radio = FakeRadio()
            self.link = self.radio.url
        self.server: WebServer | None = None  # the page's server, once the Controller made it
        self.pages: list[WsClient] = []  # the tabs `ws()` opened: closed when the test is over
        # The HF radio's Tnc: radio 2's line (stopped unless the settings tick hf/enabled)
        self.hf = Tnc(clock=self.now, profile=MERCURY)
        self.ctl = Controller(
            tmp_path,
            clock=self.now,
            port=self.link,
            pattern=self.tnc.pattern,
            web=self._page if web else None,
            check_sec=check_sec,
            auto_map=auto_map,
            hf_port=self.hf_link,
            lines={FM_ID: self.tnc, HF_ID: self.hf},
        )
        # A modem's choice of a keying line never reads the operator's serial ports in a test
        self.ctl.radios.wire = _quieted(self.ctl.radios.wire)
        # Radios 1 and 2 of the defaults are there before the start, the HF one off, with their
        # lines, modem and beacons, for a test to set up: the start keeps the ones the database has,
        # and the Env lets go of the others
        self.ctl.radios.sync(TWO_RADIOS)
        for made in self.ctl.radios.all():
            _quiet(made)

    def _page(self, ctl: Controller, config: Config) -> WebServer:
        # a port of this worker's own block: the tests run side by side
        self.server = WebServer(ctl, replace(config, web_port=next_web_port()))
        return self.server

    # ---- the radio
    def new_pty(self, name: str) -> tuple[int, str]:
        """Another pseudo-terminal at `<ports>/<name>` (`probe_N` is found by the Tnc search):
        master fd and path. POSIX only."""
        master, slave_path = make_pty()
        self._masters.append(master)
        link = self.ports / name
        link.symlink_to(slave_path)
        return master, str(link)

    async def new_radio(self) -> FakeRadio:
        """Another fake radio, started; closed when the test is over."""
        radio = FakeRadio()
        await radio.start()
        self._extra_radios.append(radio)
        return radio

    def feed(self, data: bytes) -> None:
        """The radio sends these bytes."""
        if self.radio is not None:
            self.radio.feed(data)
        else:
            feed_pty(self.master, data)

    async def heard(self, count: int = 1, timeout_sec: float = PATIENCE_SEC) -> bytes:
        """What the daemon has written to the radio since the last call: waits for `count` bytes (or
        the time) and returns all that came."""
        if self.radio is not None:
            return await self.radio.said(count, timeout_sec)
        return await asyncio.to_thread(heard_pty, self.master, count, timeout_sec)

    def unplug(self) -> None:
        """The cable is pulled: the connection is closed and a new one refused (a pty: its radio's
        side is closed, the path stays)."""
        if self.radio is not None:
            self.radio.refuse()
            self.radio.drop()
        else:
            close_pty(self.master)

    async def plug(self) -> None:
        """The cable is back: the radio listens again (a pty: a new one behind the same path)."""
        if self.radio is not None:
            await self.radio.accept()
            return
        Path(self.link).unlink(missing_ok=True)
        self.master, slave_path = make_pty()
        self._masters.append(self.master)
        Path(self.link).symlink_to(slave_path)

    async def close_radios(self) -> None:
        for radio in [*([self.radio] if self.radio is not None else []), *self._extra_radios]:
            await radio.aclose()
        self._extra_radios.clear()
        for master in self._masters:
            close_pty(master)
        self._masters.clear()
        if self._own_ports:
            shutil.rmtree(self.ports, ignore_errors=True)

    # ---- radios 1 and 2
    def _radio(self, id: RadioId) -> LiveRadio[Beacon]:
        radio = self.ctl.radios.get(id)
        assert radio is not None, f"the daemon has no radio {id}"
        return radio

    @property
    def beacon(self) -> Beacon:
        """Radio 1's beacon."""
        return self._radio(FM_ID).beacon

    @property
    def beacon_2(self) -> Beacon:
        """Radio 2's beacon."""
        return self._radio(HF_ID).beacon

    @property
    def mercury(self) -> Mercury:
        """Radio 2's modem (a Mercury radio's or the Dummy HF radio's)."""
        modem = self._radio(HF_ID).driver.modem
        assert isinstance(modem, Mercury), "radio 2 has no modem"
        return modem

    # ---- life
    @property
    def active(self) -> Tnc:
        """The radio a test of one radio means: the FM one while it is on, else the HF one."""
        return self.tnc if self.settings.get("fm/enabled", "true") != "false" else self.hf

    async def start(self, connected: bool = True) -> None:
        if self.radio is not None:
            await self.radio.start()
        if self.hf_radio is not None:
            await self.hf_radio.start()
        self.ctl.data_dir.mkdir(parents=True, exist_ok=True)
        await self.ctl.open_database()
        # A data folder that was set up before keeps its own call
        if self.operator and await self.ctl.store.setting("station/call") is None:
            rows = {
                LAST_PORT if key == "serial/last_port" else key: value
                for key, value in self.settings.items()
                if key not in RADIO_ROWS and not key.startswith(GONE)
            }
            await self.ctl.store.put_settings(rows)
        if self.first_radio and await self.ctl.store.read_radios() == ():
            await self.add_first_radios()
        await self.ctl.start()
        for id in (FM_ID, HF_ID):
            if self.ctl.radios.get(id) is None:
                # A radio made ready before the start that the database lacks is dropped, as for a
                # radio the settings no longer have.
                await self.ctl.radios.restart(id)
        if self.ctl.config.enabled_radios:
            await until(lambda: self.active.state is not Source.State.STOPPED)  # (the Tnc is started in a task)
        if connected and (self.link or self.hf_link):
            await self.until_connected()

    async def stop(self) -> None:
        await self.ctl.stop()

    async def add_first_radios(self) -> None:
        """The radios of the Env's settings (`first_radios`; a fresh install's have no rows), added
        to a database that has none, before the daemon's first start: radio 1, and radio 2 where
        they name it."""
        for position, (kind, type, on, own) in enumerate(
            first_radios(self.settings if self.operator else {}, bool(self.hf_link)), 1
        ):
            before = await self.ctl.store.radios()
            added = await self.ctl.store.add_radio(kind, type, "", on, position, settings=own)
            assert added == position, f"the database gave the {kind} radio the id {added}, not {position}"
            # What the controller's add_radio writes beside a radio that comes on: radio 1's ticks
            # when radio 2 comes
            kept = kept_in_force(before, await self.ctl.store.radios(), {}, {}, None)
            for id, key in kept.ticks:
                assert await self.ctl.store.put_radio_settings(id, {key: "true"})

    async def until_usable(self) -> None:
        """The Tnc is connected and settled: past the wait after KISS ON, so that what the daemon
        sends from here on is not thrown away."""
        await until(lambda: self.active.usable)

    async def until_connected(self) -> None:
        if self.settings.get("fm/enabled", "true") != "false":
            await until(lambda: self.tnc.state is Source.State.CONNECTED)
        if self.hf_link:
            await until(lambda: self.hf.state is Source.State.CONNECTED)
        for radio in (self.radio, self.hf_radio):
            if radio is not None:
                await radio.connected()  # (the radio has accepted the connection its Tnc made)

    # ---- the page's server
    @property
    def port(self) -> int:
        """The port the page's server listens on (Env(web=True), once started)."""
        assert self.server is not None and self.ctl.web is not None, (
            "the web server is not running: Env(tmp_path, web=True)"
        )
        return self.server.bound_port()

    async def ws(self, host: str | None = None, origin: str | None = None, cookie: str | None = None) -> WsClient:
        """A tab: connected to /ws, closed when the test is over. `host`, `origin` and `cookie` are
        the headers it says (the defaults: the address, none, none)."""
        page = await connect(self.port, host, origin, cookie)
        self.pages.append(page)
        return page

    async def fetch(
        self, path: str, headers: dict[str, str] | None = None, method: str = "GET", body: str | None = None
    ) -> HTTPResponse:
        """An HTTP request to the page's server; an answer of 400 or more is returned, not raised."""
        request = HTTPRequest(
            f"http://127.0.0.1:{self.port}{path}",
            method=method,
            headers=headers,
            body=body if body is not None else (b"" if method == "POST" else None),
            follow_redirects=False,
        )
        try:
            return await AsyncHTTPClient().fetch(request)
        except HTTPClientError as e:
            assert e.response is not None
            return e.response

    # ---- what the daemon did
    async def settled(self) -> None:
        """Everything asked of the database so far is done (the packets and stations queued are
        committed; the station rows that changed are written first, as the controller's timer
        would)."""
        assert self.ctl.db is not None
        self.ctl.packetlog.flush_stations()
        await self.ctl.db.barrier()

    async def packets(self, count: int = 1000) -> list[Packet]:
        """The packets in the database, the newest first."""
        await self.settled()
        return await self.ctl.packetlog.recent(count)

    async def stations(self) -> list[Station]:
        """The station rows in the database, the latest heard first."""
        await self.settled()
        return await self.ctl.packetlog.stations()

    async def play(self, name: str = CAPTURE) -> int:
        """Feeds a capture of the radio and waits until its packets have been through the Tnc and
        the database; how many frames it had."""
        data = fixture_bytes(name)
        frames = len(KissDecoder().feed(data))
        before = self.tnc.stats.packets
        self.feed(data)
        await until(lambda: self.tnc.stats.packets >= before + frames)
        await self.settled()
        return frames
