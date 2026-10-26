"""A receive-only iGate for the tests: the service on the real connection to a fake APRS-IS (tests/support/fakeaprsis.py), a clock in the test's hand, and packets as the radio would have heard them.

    w = await iworld(server)                          # started, logged in and verified (`await iworld(server, wait=False)` leaves it connecting)
    w.hear(source="OH2XYZ-9", path="WIDE1-1*", info=b"!6010.00N/02456.00E>x")      # the radio hears a packet; direction="out" is one it sent
    await w.until_sent(n)                             # n lines have reached the server
    w.save(igate_password="1")                        # a change of the settings, told to the service
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


def frame_of(source: str = "OH2XYZ-9", destination: str = "APZ123", path: str = "WIDE1-1*,WIDE2-1", info: bytes = b"!6010.00N/02456.00E>Test") -> ax25.Frame:
    return ax25.Frame(ax25.Address.parse(destination), ax25.Address.parse(source), tuple(ax25.Address.parse(hop) for hop in path.split(",") if hop), info=info)


class IWorld:
    def __init__(self, server: FakeAprsIs, **changes: object) -> None:
        self.server = server
        self.clock = FixedClock()
        self.config_now: Config = replace(ON_AIR, **{"station_call": "OH2GBA-10", "igate_enabled": True, "igate_server": server.address, "igate_password": "19628", **changes})       # type: ignore[arg-type]
        self.position_info: bytes | None = POSITION
        self.link = AprsIs(self.clock, Backoff([0.05]), connect_sec=1.0, greeting_sec=0.5, login_sec=0.5, lost_sec=5.0, quiet_sec=5.0)
        self.igate = Igate(self.link, self._settings, self._position, self.clock, tick_sec=3600.0)
        self.link.changed.connect(self.igate.link_changed)
        remember_stop(self.igate.stop)

    def _settings(self) -> Config:
        return self.config_now

    def _position(self) -> bytes:
        if self.position_info is None:
            raise ValueError("set your position first")
        return self.position_info

    def save(self, **changes: object) -> None:
        self.config_now = replace(self.config_now, **changes)                                      # type: ignore[arg-type]
        self.igate.settings_changed()

    def hear(self, source: str = "OH2XYZ-9", destination: str = "APZ123", path: str = "WIDE1-1*,WIDE2-1", info: bytes = b"!6010.00N/02456.00E>Test", direction: str = "in") -> Packet:
        f = frame_of(source, destination, path, info)
        packet = packet_of(direction, ax25.encode(f), f, self.clock())                              # type: ignore[arg-type]
        self.igate.on_packet(packet)
        return packet

    async def until_sent(self, count: int) -> None:
        await until(lambda: len(self.server.packets) >= count)


async def iworld(server: FakeAprsIs, wait: bool = True, **changes: object) -> IWorld:
    w = IWorld(server, **changes)
    await w.igate.start()
    if wait:
        await until(lambda: w.igate.state == "connected")
    return w
