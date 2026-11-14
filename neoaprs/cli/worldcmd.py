"""`neoaprs map --world [--build YYYYMMDD | --source SRC] [--zoom Z] [--out DIR]` (and `scripts/fetch-worldmap`): makes the world map that ships with the program (neoaprs/worldmap.py).

It cuts the whole world down to zoom 4 (`--zoom`) out of a Protomaps daily build (`--build`, or the latest one; or `--source`, a web address or a PMTiles file; neoaprs/pmtilescut.py) into DIR (default `neoaprs/maps/`
of this package) as `basemap-world.pmtiles` with `basemap-world.json` beside it, the build it was cut from. A file over 8 MB is refused before it is fetched: the program carries it in every package. Run it when the
map should be refreshed, and commit the two files."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from neoaprs.clock import utcnow
from neoaprs.mapstate import MapError
from neoaprs.pmtilesarchive import BUILDS, latest_build
from neoaprs.pmtilescut import CutError, extract
from neoaprs.worldmap import MAPS_DIR, SHIPPED_ZOOM, WORLD_FILE

MAX_BYTES = 8_000_000


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="neoaprs map --world", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / MAPS_DIR), help="the folder the map is put in (default %(default)s)")
    parser.add_argument("--zoom", type=int, default=SHIPPED_ZOOM, help="the deepest zoom (default %(default)s)")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--build", metavar="YYYYMMDD", help="the daily build of build.protomaps.com to cut from (default: the latest)")
    where.add_argument("--source", help="a web address or a PMTiles file to cut from")
    return parser.parse_args(argv)


def say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


async def make(args: argparse.Namespace) -> Path:
    out = Path(args.out)
    if args.source:
        source, build = args.source, ""
    elif args.build:
        source, build = f"{BUILDS}/{args.build}.pmtiles", args.build
    else:
        source, build = await latest_build(utcnow())
    out.mkdir(parents=True, exist_ok=True)
    final = out / WORLD_FILE
    size = (await extract(source, final, None, args.zoom, dry_run=True)).bytes
    if size > MAX_BYTES:
        raise CutError(f"the world to zoom {args.zoom} is {size / 1e6:.1f} MB, over the {MAX_BYTES / 1e6:.0f} MB the program may carry: use a lower --zoom")
    await extract(source, final, None, args.zoom, on_percent=lambda percent: print(f"fetching {percent}%", flush=True))
    final.with_suffix(".json").write_text(json.dumps({"build": build}) + "\n")
    return final


def main(argv: list[str]) -> int:
    args = parse(argv)
    try:
        final = asyncio.run(make(args))
    except (MapError, CutError) as e:
        say(f"worldmap: {e}")
        return 1
    print(f"{final}: {final.stat().st_size / 1e6:.1f} MB, zoom 0 to {args.zoom}")
    return 0
