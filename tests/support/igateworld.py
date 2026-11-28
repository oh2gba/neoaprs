"""A receive-only iGate for the tests: the service on a real connection to a fake APRS-IS
(tests/support/fakeaprsis.py), a clock the test holds, and packets as the radio would have heard
them.
"""

from dataclasses import replace

from neoaprs import ax25
from neoaprs.aprsis import AprsIs
from neoaprs.config import Config
from neoaprs.packet import Packet
from neoaprs.services.igate import Igate
from neoaprs.source import Backoff
from neoaprs.tncmode import packet_of
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, remember_stop, until
from tests.support.fakeaprsis import FakeAprsIs

POSITION = b"=6010.00N/02456.00EdNeoAPRS"
PLACE = (60.17, 24.94)


def frame_of(
    source: str = "OH2XYZ-9",
    destination: str = "APZ123",
    path: str = "WIDE1-1*,WIDE2-1",
    info: bytes = b"!6010.00N/02456.00E>Test",
) -> ax25.Frame:
    return ax25.Frame(
        ax25.Address.parse(destination),
        ax25.Address.parse(source),
        tuple(ax25.Address.parse(hop) for hop in path.split(",") if hop),
        info=info,
    )


class IWorld:
    def __init__(self, server: FakeAprsIs, place: tuple[float, float] | None = PLACE, **changes: object) -> None:
        self.server = server
        self.clock = FixedClock()
        self.config_now: Config = replace(
            ON_AIR,
            **{  # type: ignore[arg-type]
                "station_call": "OH2GBA-10",
                "igate_enabled": True,
                "igate_gate": True,
                "igate_server": server.address,
                "igate_password": "19628",
                **changes,
            },
        )
        self.position_info: bytes | None = POSITION
        self.link = AprsIs(
            self.clock, Backoff([0.05]), connect_sec=1.0, greeting_sec=0.5, login_sec=0.5, lost_sec=5.0, quiet_sec=5.0
        )
        # Where we are: the filter of the connection is round it
        self.place = place
        self.igate = Igate(self.link, self._settings, self._position, lambda: self.place, self.clock, tick_sec=3600.0)
        self.link.changed.connect(self.igate.link_changed)
        self.link.written.connect(self.igate.written)  # (wiring.py ties them)
        remember_stop(self.igate.stop)

    def _settings(self) -> Config:
        return self.config_now

    def _position(self) -> bytes:
        if self.position_info is None:
            raise ValueError("set your position first")
        return self.position_info

    def save(self, **changes: object) -> None:
        self.config_now = replace(self.config_now, **changes)  # type: ignore[arg-type]
        self.igate.settings_changed()

    def hear(
        self,
        source: str = "OH2XYZ-9",
        destination: str = "APZ123",
        path: str = "WIDE1-1*,WIDE2-1",
        info: bytes = b"!6010.00N/02456.00E>Test",
        direction: str = "in",
    ) -> Packet:
        f = frame_of(source, destination, path, info)
        packet = packet_of(direction, ax25.encode(f), f, self.clock())  # type: ignore[arg-type]
        self.igate.on_packet(packet)
        return packet

    async def until_sent(self, count: int) -> None:
        await until(lambda: len(self.server.packets) >= count)


async def iworld(
    server: FakeAprsIs, wait: bool = True, place: tuple[float, float] | None = PLACE, **changes: object
) -> IWorld:
    w = IWorld(server, place, **changes)
    await w.igate.start()
    if wait:
        await until(lambda: w.igate.state in ("connected", "listening", "unverified"))
    return w
