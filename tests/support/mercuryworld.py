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
# A world may also have an FM side (`add(..., fm=True)`): one FM air of its own (`FmAir`, every frame a station's FM radio sends is heard by every other FM radio at once, no digipeaters), so that a station with
# both radios (fm=True, hf=True), one with FM alone and one with HF alone sit in one scenario: the beacon on both radios, a message on the radio the station was last heard on, the ack back the way it came.

from collections.abc import Callable
from pathlib import Path

from neoaprs import kiss
from tests.support.env import Env, remember_stop, until
from tests.support.fakemercury import Air
from tests.support.fakeradio import FakeRadio

HELSINKI = (60.17, 24.94)
TICK_SEC = 0.02


class FmStation(FakeRadio):
    """A station's FM radio on the world's FM air: a KISS TNC whose every frame every other FM radio hears at once."""

    def __init__(self, air: "FmAir") -> None:
        super().__init__()
        self.air = air
        self._decoder = kiss.KissDecoder()
        self.frames_in: list[bytes] = []            # what this radio was given to send

    def heard_bytes(self, data: bytes) -> None:
        super().heard_bytes(data)
        for frame in self._decoder.feed(data):
            if frame.command == 0:
                self.frames_in.append(frame.payload)
                self.air.transmit(self, frame.payload)


class FmAir:
    """The FM air of a world: no collisions, no digipeaters, every frame delivered to every other station at once (the VHF network's part is tested elsewhere; here it is the other radio)."""

    def __init__(self) -> None:
        self.stations: list[FmStation] = []
        self.delivered: list[tuple[FmStation, FmStation, bytes]] = []

    def station(self) -> FmStation:
        radio = FmStation(self)
        self.stations.append(radio)
        return radio

    def transmit(self, sender: FmStation, payload: bytes) -> None:
        for other in self.stations:
            if other is not sender:
                other.feed(kiss.encode(payload))
                self.delivered.append((sender, other, payload))


class World:
    def __init__(self, tmp_path: Path, frame_sec: float = 0.2, busy_detect: bool = True) -> None:
        self.dir = tmp_path
        self.air = Air(frame_sec=frame_sec, busy_detect=busy_detect)
        self.fm_air = FmAir()
        self.stations: dict[str, Env] = {}
        remember_stop(self.air.aclose)

    async def add(self, call: str, lat: float = HELSINKI[0], lon: float = HELSINKI[1], fm: bool = False, hf: bool = True, **settings: str) -> Env:
        """A station with this call at this place, on the HF air (and on the FM air with `fm`; `hf=False` for one with the FM radio alone), not yet started."""
        rows = {"station/call": call, "station/lat": str(lat), "station/lon": str(lon), "beacon/interval_min": "0", "messages/alert": "false", **settings}        # (no timed beacon unless a test asks for one: it would key in the middle of what the test watches)
        e = Env(self.dir / call.replace("-", "_"), radio=self.fm_air.station() if fm else False, hf=self.air.station() if hf else None, settings=rows)
        e.ctl.messaging.tick_sec = TICK_SEC
        e.ctl.messaging.pace.spacing_sec = 0.0
        e.ctl.ownobjects.tick_sec, e.ctl.sender.spacing_sec = TICK_SEC, 0.0           # (our objects go at the test's pace too)
        for beacon in (e.ctl.beacon, e.ctl.hf_beacon):
            beacon.tick_sec, beacon.retry_sec = TICK_SEC, 0.05
        self.stations[call] = e
        return e

    async def start(self) -> None:
        await self.air.start()
        for e in self.stations.values():
            await e.start()
        for e in self.stations.values():
            if e.hf_radio is not None:
                await until(lambda e=e: e.hf.usable and e.ctl.mercury.running)        # type: ignore[misc]
            if e.radio is not None:
                await until(lambda e=e: e.tnc.usable)        # type: ignore[misc]

    def pass_time(self, seconds: float) -> None:
        """Every station's clock moves on."""
        for e in self.stations.values():
            e.now.advance(seconds)       # type: ignore[attr-defined]

    async def settled(self, call: str, timeout_sec: float = 15.0) -> None:
        """Until the station's HF radio is free and its retry ticker has seen it so. A wait of the retry schedule that runs while the radio is held is moved on by the time it was held (services/retries.py:
        on the air our own frame holds it for 3.8 s), and the ticker learns of the hold's end only at its next tick, so a test that moves the clock before that would have the whole jump counted as time
        the radio was held, and its retry would fall due a clock jump later than the schedule says. The budget is for a slow machine; it is settled in a tick here."""
        e = self.stations[call]
        await until(lambda: e.hf.usable and e.ctl.messaging.retries._down_since is None, timeout_sec)

    def __getitem__(self, call: str) -> Env:
        return self.stations[call]

    async def until(self, condition: Callable[[], object], timeout_sec: float = 5.0) -> None:
        await until(condition, timeout_sec)
