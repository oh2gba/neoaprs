"""What the tests of Find my radio share (neoaprs/services/radiofinder.py): a finder over a fixed list of ports with a record of what it did to the radio's own line, and the short timing a fake TNC is searched with."""
from typing import Any

from neoaprs.radiosearch import Trying
from neoaprs.services.radiofinder import RadioFinder
from neoaprs.services.radioprobe import Timing

QUICK = Timing(listen_sec=0.3, answer_sec=0.3, pace=0.001)          # (a fake TNC on the loopback answers at once, but a busy machine may take a while to pass it on)


class Rig:
    """A finder over a fixed list of ports (`finder` goes to it: the `line` of a fake port, ...)."""

    def __init__(self, ports: list[str], timing: Timing = QUICK, **finder: Any) -> None:
        self.events: list[str] = []                        # what was done to the radio's own line: "hold", "release"
        self.tried: list[Trying] = []

        async def listed() -> list[str]:
            return ports

        async def hold() -> None:
            self.events.append("hold")

        self.finder = RadioFinder(listed, hold, lambda: self.events.append("release"), timing, **finder)
