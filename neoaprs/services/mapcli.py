"""The command line of the base map: `neoaprs map [--data DIR] [--radius KM] [--maxzoom Z] [--source SRC] [--lat DEG --lon DEG] [--dry-run]` (also `python -m neoaprs.services.mapfetch` and `scripts/fetch-basemap`).

It does what the page's Estimate and Download buttons do (neoaprs/services/mapfetch.py): the settings of the data folder (the station's position, `map/radius_km`, `map/maxzoom`, `map/source`) unless a flag says
otherwise, then the world map if the program has none (it ships with one) and the detailed map, or with --dry-run only the size. The daemon may be running; the settings are read, not changed.
`neoaprs map --world --help` is the command that makes the world map the program ships with (developers)."""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

from neoaprs.config import MAP_MAXZOOM, MAP_RADIUS_KM, Config
from neoaprs.db import Db
from neoaprs.dberror import DbClosed, SqlError, StoreError
from neoaprs.paths import default_data_dir
from neoaprs.pmtilestool import ToolError
from neoaprs.mapstate import MapError
from neoaprs.services.mapfetch import MapFetch
from neoaprs.store import DB_NAME, Store

READ_WAIT_MS = 3000


def parse(argv: list[str], prog: str = "mapfetch") -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=str(default_data_dir()), help="the data folder (default %(default)s)")
    parser.add_argument("--radius", type=int, metavar="KM", help=f"the distance from the station to the edge of the map, {MAP_RADIUS_KM[0]} to {MAP_RADIUS_KM[1]} (default: map/radius_km)")
    parser.add_argument("--maxzoom", type=int, metavar="Z", help=f"the deepest zoom, {MAP_MAXZOOM[0]} to {MAP_MAXZOOM[1]}: 10 towns, 12 streets, 14 houses (default: map/maxzoom)")
    parser.add_argument("--source", help="a web address or a file to cut the map from (default: map/source, else the latest daily build of build.protomaps.com)")
    parser.add_argument("--lat", type=float, help="the latitude to put the map round (default: station/lat)")
    parser.add_argument("--lon", type=float, help="the longitude (default: station/lon)")
    parser.add_argument("--dry-run", action="store_true", help="say how big the map would be and change nothing")
    return parser.parse_args(argv)


def say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


async def stored_config(data: Path) -> Config:
    """The settings of the data folder; the defaults when there is no database yet."""
    path = data / DB_NAME
    if not path.is_file():
        return Config()
    db = Db.at(path, READ_WAIT_MS)
    try:
        await db.start()
        store = Store()
        store.use(db, path)
        return Config.from_data(await store.settings())
    except (StoreError, SqlError, DbClosed) as e:
        say(f"mapfetch: {path}: {e}")
        return Config()
    finally:
        await db.close()


def with_flags(config: Config, args: argparse.Namespace) -> Config:
    """The settings with the flags put over them, every value checked the way the daemon checks it."""
    values = {key: str(value) for key, value in (("map/radius_km", args.radius), ("map/maxzoom", args.maxzoom), ("map/source", args.source),
                                                  ("station/lat", args.lat), ("station/lon", args.lon)) if value is not None}
    return Config.checked(config, values) if values else config


def describe(job: MapFetch, dry_run: bool) -> str:
    status = job.status()
    if dry_run and status.estimate is not None:
        e = status.estimate
        return f"{e.bytes / 1e6:.0f} MB for {e.radius_km} km round us to zoom {e.maxzoom} ({e.tiles} tiles), from build {e.build or 'of your choice'}"
    detail = status.detail
    return f"{detail.name}: {detail.bytes / 1e6:.0f} MB" if detail else "no map was made"


async def run(args: argparse.Namespace) -> int:
    data = Path(args.data).expanduser()
    try:
        config = with_flags(await stored_config(data), args)
    except ValueError as e:
        say(f"mapfetch: {e}")
        return 2
    job = MapFetch(data, lambda: config)
    work = asyncio.ensure_future(job.estimate() if args.dry_run else job.fetch())
    last = ""
    try:
        while not work.done():
            await asyncio.wait([work], timeout=0.5)
            status = job.status()
            line = f"{status.step or 'working'}: {status.percent}%" if status.percent is not None else status.step
            if status.downloaded:
                line += f" · {status.downloaded / 1e6:.0f} MB"
            if status.note:
                line += f" · {status.note}"
            if line and line != last:
                last = line
                print(line, flush=True)
        await work
    except (MapError, ToolError) as e:
        say(f"mapfetch: {e}")
        return 1
    print(describe(job, args.dry_run))
    return 0


def main(argv: list[str] | None = None, prog: str = "mapfetch") -> int:
    args = parse(sys.argv[1:] if argv is None else argv, prog)
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        say("mapfetch: stopped")
        return 130
