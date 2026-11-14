"""MapRig: the map download service (neoaprs/services/mapfetch.py) cutting the made-up planet of tests/support/madepmtiles.py from a range server on the loopback (tests/support/rangeserver.py), with the statuses it
announced; the base of the Rig of test_mapfetch.py and test_mapstall.py.

    class Rig(MapRig):
        def __init__(self, data: Path, server: RangeServer) -> None:
            super().__init__(data, server, lambda: CONFIG)
    rig.status()                       # the status now
    await rig.idle()                   # the download or the estimate is over
    rig.seen                           # the status after every `changed`
    data_offset(archive)               # where the tile data of an archive begins: a range server that holds from there holds the tiles and lets the directories through
"""
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from neoaprs.config import Config
from neoaprs.mapstate import MapStatus
from neoaprs.services.mapfetch import PATIENCE, WORLD, MapFetch, Patience
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, remember_stop, until_started
from tests.support.rangeserver import RangeServer
from tests.support.madepmtiles import fields_of


def own_world(data: Path) -> Path | None:
    """The world map of the data folder only: the one that ships with the program is not there for the tests that make the world map."""
    return data / WORLD if (data / WORLD).exists() else None


def data_offset(archive: bytes) -> int:
    return int(fields_of(archive)["data_offset"])


def config_for(server: RangeServer, **fields: Any) -> Config:
    return replace(ON_AIR, map_source=server.url, **fields)


class MapRig:
    def __init__(self, data: Path, server: RangeServer, config: Callable[[], Config], patience: Patience = PATIENCE) -> None:
        self.data, self.server = data, server
        self.service = MapFetch(data, config, FixedClock(), patience=patience, world=own_world)
        self.seen: list[MapStatus] = []
        self.service.changed.connect(lambda: self.seen.append(self.service.status()))
        remember_stop(self.service.stop)

    def status(self) -> MapStatus:
        return self.service.status()

    async def idle(self) -> None:
        await until_started(lambda: self.status().state not in ("estimating", "downloading"))
