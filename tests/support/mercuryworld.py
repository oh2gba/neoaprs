"""Two or three NeoAPRS stations on one HF frequency with the Mercury modem, for whole-exchange
tests. Each station is an `Env` on its own data folder and clock, its radio a station of the fake
Mercury's air.
"""
# A world may also have an FM side (`add(..., fm=True)`): one FM air of its own (`FmAir`, every
# frame a station's FM radio sends is heard by every other FM radio at once, no digipeaters), so
# that a station with both radios (fm=True, hf=True), one with FM alone and one with HF alone sit in
# one scenario: the beacon on both radios, a message on the radio the station was last heard on, the
# ack back the way it came.

from collections.abc import Callable
from pathlib import Path

from neoaprs import kiss
from tests.support.env import Env, remember_stop, until
from tests.support.fakemercury import Air
from tests.support.fakeradio import FakeRadio

HELSINKI = (60.17, 24.94)
TICK_SEC = 0.02


class FmStation(FakeRadio):
    """A station's FM radio on the world's FM air: a KISS TNC whose every frame every other FM radio
    hears at once."""

    def __init__(self, air: "FmAir") -> None:
        super().__init__()
        self.air = air
        self._decoder = kiss.KissDecoder()
        self.frames_in: list[bytes] = []  # what this radio was given to send

    def heard_bytes(self, data: bytes) -> None:
        super().heard_bytes(data)
        for frame in self._decoder.feed(data):
            if frame.command == 0:
                self.frames_in.append(frame.payload)
                self.air.transmit(self, frame.payload)


class FmAir:
    """The FM air of a world: no collisions, no digipeaters, every frame delivered to every other
    station at once (the VHF network's part is tested elsewhere; here it is the other radio)."""

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

    async def add(
        self,
        call: str,
        lat: float = HELSINKI[0],
        lon: float = HELSINKI[1],
        fm: bool = False,
        hf: bool = True,
        **settings: str,
    ) -> Env:
        """A station with this call at this place, on the HF air (and on the FM air with `fm`;
        `hf=False` for one with the FM radio alone), not yet started."""
        # No timed beacon unless a test asks for one: it would key in the middle of what the test
        # watches
        rows = {
            "station/call": call,
            "station/lat": str(lat),
            "station/lon": str(lon),
            "beacon/interval_min": "0",
            "messages/alert": "false",
            **settings,
        }
        e = Env(
            self.dir / call.replace("-", "_"),
            radio=self.fm_air.station() if fm else False,
            hf=self.air.station() if hf else None,
            settings=rows,
        )
        e.ctl.messaging.tick_sec = TICK_SEC
        e.ctl.messaging.pace.spacing_sec = 0.0
        # Our objects go at the test's pace too
        e.ctl.ownobjects.tick_sec, e.ctl.sender.spacing_sec = TICK_SEC, 0.0
        for beacon in (e.beacon, e.beacon_2):
            beacon.tick_sec, beacon.retry_sec = TICK_SEC, 0.05
        self.stations[call] = e
        return e

    async def start(self) -> None:
        await self.air.start()
        for e in self.stations.values():
            await e.start()
        for e in self.stations.values():
            if e.hf_radio is not None:
                await until(lambda e=e: e.hf.usable and e.mercury.running)  # type: ignore[misc]
            if e.radio is not None:
                await until(lambda e=e: e.tnc.usable)  # type: ignore[misc]

    def pass_time(self, seconds: float) -> None:
        """Every station's clock moves on."""
        for e in self.stations.values():
            e.now.advance(seconds)  # type: ignore[attr-defined]

    async def settled(self, call: str, timeout_sec: float = 15.0) -> None:
        """Wait until the station's HF radio is free and its retry ticker has seen it so.

        The retry schedule counts the time a radio was held, and the ticker learns the hold ended
        only at its next tick; moving the clock before that would count the whole jump as held time.
        """
        e = self.stations[call]
        await until(lambda: e.hf.usable and not e.ctl.messaging.retries.away(e.hf), timeout_sec)

    def __getitem__(self, call: str) -> Env:
        return self.stations[call]

    async def until(self, condition: Callable[[], object], timeout_sec: float = 5.0) -> None:
        await until(condition, timeout_sec)
