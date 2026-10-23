"""Env: the daemon (the Controller) on test data, with the clock in the test's hand and a radio that is a fake TCP radio on the loopback (tests/support/fakeradio.py), the same on every system. Every integration
test builds its world with it; `stop_all` is called when a test is over and also closes the Db of the Stores the tests opened.

    e = Env(tmp_path)                    # the radio is a FakeRadio (e.radio; e.link is its url, socket://127.0.0.1:PORT); the data folder is tmp_path
    await e.start()                      # the Controller is up and the Tnc is connected to the radio
    e.feed(kiss_bytes)                   # the radio speaks
    await e.heard(n)                     # ... and what the daemon wrote to it (bytes); `said(e, n)` of tests/support/air.py gives the frames
    await e.play()                       # ... the whole live capture, and waits until it is all through the database
    await e.packets(), await e.stations()    # what the database holds
    e.unplug(); await e.plug()           # the cable pulled (the connection closed, new ones refused) and put back
    await e.new_radio()                  # another fake radio (to switch the port to); `new_pty(name)` another pty
    Env(tmp_path, radio=False)           # no radio: the Tnc finds no port (a test that wants a device file calls `new_pty`)
    Env(tmp_path, radio="pty")           # the radio on a pseudo-terminal behind the path e.link (POSIX only; for the tests that are about a device file); e.master is its master descriptor
    Env(tmp_path, operator=False)        # a fresh install: no call and no position (the default); every other Env has the operator's station in its settings, as an install that was set up has
    Env(tmp_path, web=True)              # the page's server too, on a free port (`e.port`): `page = await e.ws()` is a tab (tests/support/wsclient.py), `await e.fetch("/path")` an HTTP request

The Tnc is the real one with quick timers; its search pattern is a folder of the test, never /dev/brainbox_*. The keep-alive (which writes to the radio when it is quiet, and at the open) is off in the settings of the Env (`tnc/check_sec` 0), so that the line is usable as soon as it is open; a test about it sets `tnc/check_sec`. The settings of an Env with an operator name the Kenwood TNC-2 profile (`tnc/profile`), the TNC the tests are about; a fresh install's (`operator=False`) have no rows, so its TNC is sent nothing."""
import asyncio
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from tornado.httpclient import AsyncHTTPClient, HTTPClientError, HTTPRequest, HTTPResponse

from neoaprs.clock import Clock
from neoaprs.config import DEFAULTS, Config
from neoaprs.controller import Controller
from neoaprs.db import Db
from neoaprs.kiss import KissDecoder
from neoaprs.packet import Packet
from neoaprs.source import Backoff, Source
from neoaprs.stationbook import Station
from neoaprs.tnc import Tnc
from tests.support.clock import FixedClock
from tests.support.files import fixture_bytes
from tests.support.fakeradio import FakeRadio
from tests.support.ptyline import close_pty, feed as feed_pty, heard as heard_pty, make_pty
from tests.support.wsclient import WsClient, connect
from neoaprs.web.server import WebServer

_live: list["Env"] = []
_dbs: list[Db] = []                                       # the Db of every Store the tests opened (tests/support/storedb.py): closed when the test is over
_stops: list[Callable[[], Awaitable[None]]] = []          # the stop of every part a test started by itself (a service on a stub): called when the test is over, before the databases are closed

CAPTURE = "kiss/thd7-2026-10-21.bin"
OPERATOR = {"station/call": "OH2GBA", "station/lat": "60.17", "station/lon": "24.94", "tnc/profile": "kenwood-tnc2", "tnc/check_sec": "0", "beacon/interval_min": "0"}       # the station of the tests, with the TNC the tests are about: with no call set nothing is transmitted (config.can_transmit)
ON_AIR: Config = replace(DEFAULTS, station_call="OH2GBA", station_lat=60.17, station_lon=24.94, tnc_profile="kenwood-tnc2", tnc_check_sec=0, beacon_interval_min=0)      # the same as a Config, for the tests that hold one: the defaults are a station with no call and a TNC that is sent nothing


def remember(db: Db) -> None:
    """A Db that a test opened is closed by stop_all() when the test is over, so that a test that forgets to close it does not leak a thread."""
    _dbs.append(db)


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None                                       # an Env made by a test that is not async: nothing is running, nothing to stop


def remember_stop(stop: Callable[[], Awaitable[None]]) -> None:
    """A part that a test starts without an Env (a service on a stub Tnc) is stopped by stop_all() when the test is over, so that a test that forgets to does not leak its task."""
    _stops.append(stop)


async def stop_all() -> None:
    """Stops the daemons of the Envs made on this loop, whether or not their tests did (stop() can be called again, so those that did are not touched), and closes their radios. Called
    when a test is over, so that a test that failed on the way, or forgot, does not leave a daemon running. The Envs of other loops are forgotten."""
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


async def until(condition: Callable[[], object], timeout_sec: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_sec
    while not condition():
        assert asyncio.get_running_loop().time() < deadline, "the condition did not come true"
        await asyncio.sleep(0.01)


class Env:
    def __init__(self, tmp_path: Path, clock: Clock | None = None, radio: bool | str = True, ports: Path | None = None, web: bool = False, operator: bool = True, settings: dict[str, str] | None = None, **tnc_options: Any) -> None:
        self.dir = tmp_path
        self.settings = {**OPERATOR, **(settings or {})}          # the rows of the operator's data folder at the first start: a test about the keep-alive turns it on here (`tnc/check_sec`)
        self.operator = operator
        self.loop = _running_loop()
        _live.append(self)
        self.now: Clock = clock or FixedClock()
        self._own_ports = ports is None
        self.ports = ports or Path(tempfile.mkdtemp(prefix="neoaprs-ports-"))      # the "/dev" of the test: the radio's path and the places the probe looks in (`ports`: the one of an Env before)
        self._masters: list[int] = []
        self.master = -1                                      # the master descriptor of the radio's pty (radio="pty")
        self.link = ""                                        # the port the daemon opens: the radio's url, or the path of its pty
        self.radio: FakeRadio | None = None
        self._extra_radios: list[FakeRadio] = []
        options: dict[str, Any] = {"pattern": str(self.ports / "probe_*"), "check_sec": 0.0, "settle_sec": 0.15, "probe_seconds": 0.3, "backoff": Backoff([0.05, 0.05])}
        self.tnc = Tnc(clock=self.now, **{**options, **tnc_options})
        if radio == "pty":
            self.master, self.link = self.new_pty("radio")
        elif radio:
            self.radio = FakeRadio()
            self.link = self.radio.url
        self.server: WebServer | None = None                 # the page's server, once the Controller made it
        self.pages: list[WsClient] = []                       # the tabs `ws()` opened: closed when the test is over
        self.ctl = Controller(tmp_path, clock=self.now, tnc=self.tnc, port=self.link, pattern=self.tnc.pattern, web=self._page if web else None)

    def _page(self, ctl: Controller, config: Config) -> WebServer:
        self.server = WebServer(ctl, replace(config, web_port=0))         # a free port: the tests run side by side
        return self.server

    # ---- the radio
    def new_pty(self, name: str) -> tuple[int, str]:
        """Another pseudo-terminal, reachable at `<ports>/<name>` (a name `probe_N` is found by the Tnc's search); its master descriptor and that path. POSIX only."""
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

    async def heard(self, count: int = 1, timeout_sec: float = 2.0) -> bytes:
        """What the daemon has written to the radio since the last call: waits for `count` bytes (or the time) and returns all that came."""
        if self.radio is not None:
            return await self.radio.said(count, timeout_sec)
        return await asyncio.to_thread(heard_pty, self.master, count, timeout_sec)

    def unplug(self) -> None:
        """The cable is pulled: the connection is closed and a new one refused (a pty: its radio's side is closed, the path stays)."""
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

    # ---- life
    async def start(self, connected: bool = True) -> None:
        if self.radio is not None:
            await self.radio.start()
        if self.operator:
            self.ctl.data_dir.mkdir(parents=True, exist_ok=True)
            await self.ctl.open_database()
            if await self.ctl.store.setting("station/call") is None:      # (a data folder that was set up before keeps its own call)
                await self.ctl.store.put_settings(self.settings)
        await self.ctl.start()
        await until(lambda: self.tnc.state is not Source.State.STOPPED)      # (the Tnc is started in a task)
        if connected and self.link:
            await self.until_connected()

    async def stop(self) -> None:
        await self.ctl.stop()

    async def until_connected(self) -> None:
        await until(lambda: self.tnc.state is Source.State.CONNECTED)
        if self.radio is not None:
            await self.radio.connected()                      # (the radio has accepted the connection the Tnc made)

    # ---- the page's server
    @property
    def port(self) -> int:
        """The port the page's server listens on (Env(web=True), once started)."""
        assert self.server is not None and self.ctl.web is not None, "the web server is not running: Env(tmp_path, web=True)"
        return self.server.bound_port()

    async def ws(self, host: str | None = None, origin: str | None = None, cookie: str | None = None) -> WsClient:
        """A tab: connected to /ws, closed when the test is over. `host`, `origin` and `cookie` are the headers it says (the defaults: the address, none, none)."""
        page = await connect(self.port, host, origin, cookie)
        self.pages.append(page)
        return page

    async def fetch(self, path: str, headers: dict[str, str] | None = None, method: str = "GET", body: str | None = None) -> HTTPResponse:
        """An HTTP request to the page's server; an answer of 400 or more is returned, not raised."""
        request = HTTPRequest(f"http://127.0.0.1:{self.port}{path}", method=method, headers=headers, body=body if body is not None else (b"" if method == "POST" else None), follow_redirects=False)
        try:
            return await AsyncHTTPClient().fetch(request)
        except HTTPClientError as e:
            assert e.response is not None
            return e.response

    # ---- what the daemon did
    async def settled(self) -> None:
        """Everything asked of the database so far is done (the packets and stations queued are committed)."""
        assert self.ctl.db is not None
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
        """Feeds a capture of the radio and waits until its packets have been through the Tnc and the database; how many frames it had."""
        data = fixture_bytes(name)
        frames = len(KissDecoder().feed(data))
        before = self.tnc.stats.packets
        self.feed(data)
        await until(lambda: self.tnc.stats.packets >= before + frames)
        await self.settled()
        return frames

