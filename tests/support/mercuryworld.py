"""Two or three NeoAPRS stations on one HF frequency with the Mercury HF modem, for the tests of the whole exchange (a beacon, a message and its ack, a retry after a collision, an iGate on one of them): each station is a
daemon (an `Env`, tests/support/env.py) on its own data folder and clock, its radio a station of the fake Mercury's air (tests/support/fakemercury.py), with the profile `mercury`, no path and quick tickers.

    w = World(tmp_path, frame_sec=0.2)                       # a frame is 0.2 s on the air instead of 3.9
    a = await w.add("OH2A")                                  # a station at Helsinki; `add(call, lat=..., lon=..., **settings)` for another place or setting
    b = await w.add("OH2B", lat=61.5, lon=23.8)
    await w.start()                                          # the air listens, the daemons are up, every Tnc is connected and every modem part hears its control port
    w.pass_time(33)                                          # every clock moves (a retry falls due)
    await w.until(lambda: ...)
    w.air.delivered, w.air.collisions                        # what the air carried and lost

The Envs are stopped by `stop_all` when the test is over, as every Env is; the air is closed with them (`remember_stop`)."""
from collections.abc import Callable
from pathlib import Path

from tests.support.env import Env, remember_stop, until
from tests.support.fakemercury import Air

HELSINKI = (60.17, 24.94)
TICK_SEC = 0.02


class World:
    def __init__(self, tmp_path: Path, frame_sec: float = 0.2, busy_detect: bool = True) -> None:
        self.dir = tmp_path
        self.air = Air(frame_sec=frame_sec, busy_detect=busy_detect)
        self.stations: dict[str, Env] = {}
        remember_stop(self.air.aclose)

    async def add(self, call: str, lat: float = HELSINKI[0], lon: float = HELSINKI[1], **settings: str) -> Env:
        """A station with this call at this place, on the air, not yet started."""
        rows = {"station/call": call, "station/lat": str(lat), "station/lon": str(lon), "tnc/profile": "mercury", "hf/beacon_interval_min": "0", **settings}        # (no timed beacon unless a test asks for one: it would key in the middle of what the test watches)
        e = Env(self.dir / call.replace("-", "_"), radio=self.air.station(), settings=rows)
        e.ctl.messaging.tick_sec = TICK_SEC
        e.ctl.messaging.pace.spacing_sec = 0.0
        e.ctl.beacon.tick_sec, e.ctl.beacon.retry_sec = TICK_SEC, 0.05
        self.stations[call] = e
        return e

    async def start(self) -> None:
        await self.air.start()
        for e in self.stations.values():
            await e.start()
        for e in self.stations.values():
            await until(lambda e=e: e.tnc.usable and e.ctl.mercury.running)        # type: ignore[misc]

    def pass_time(self, seconds: float) -> None:
        """Every station's clock moves on."""
        for e in self.stations.values():
            e.now.advance(seconds)       # type: ignore[attr-defined]

    def __getitem__(self, call: str) -> Env:
        return self.stations[call]

    async def until(self, condition: Callable[[], object], timeout_sec: float = 5.0) -> None:
        await until(condition, timeout_sec)
