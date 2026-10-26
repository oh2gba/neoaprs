"""MapRig: the map download service (neoaprs/services/mapfetch.py) on a fake pmtiles tool, with the statuses it announced; the base of the Rig of test_mapfetch.py and test_mapstall.py.

    class Rig(MapRig):
        def __init__(self, data: Path, fake: FakePmtiles) -> None:
            super().__init__(data, fake, lambda: CONFIG)
    rig.status()                       # the status now
    await rig.idle()                   # the download or the estimate is over
    rig.seen                           # the status after every `changed`
"""
from collections.abc import Callable
from pathlib import Path

from neoaprs.config import Config
from neoaprs.mapstate import MapStatus
from neoaprs.services.mapfetch import PATIENCE, WORLD, MapFetch, Patience
from tests.support.clock import FixedClock
from tests.support.env import remember_stop, until
from tests.support.fakepmtiles import FakePmtiles


def own_world(data: Path) -> Path | None:
    """The world map of the data folder only: the one that ships with the program is not there for the tests that make the world map."""
    return data / WORLD if (data / WORLD).exists() else None


class MapRig:
    def __init__(self, data: Path, fake: FakePmtiles, config: Callable[[], Config], patience: Patience = PATIENCE, idle_sec: float = 5.0) -> None:
        self.data, self.fake, self.idle_sec = data, fake, idle_sec
        self.service = MapFetch(data, config, FixedClock(), patience=patience, world=own_world)
        self.seen: list[MapStatus] = []
        self.service.changed.connect(lambda: self.seen.append(self.service.status()))
        remember_stop(self.service.stop)

    def status(self) -> MapStatus:
        return self.service.status()

    async def idle(self) -> None:
        await until(lambda: self.status().state not in ("estimating", "downloading"), self.idle_sec)
