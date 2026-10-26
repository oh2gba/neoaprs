"""`neoaprs map --world [--build YYYYMMDD | --source SRC] [--zoom Z] [--out DIR] [--data DIR]` (and `scripts/fetch-worldmap`): makes the world map that ships with the program (neoaprs/worldmap.py).

It cuts the whole world down to zoom 4 (`--zoom`) out of a Protomaps daily build (`--build`, or the latest one; or `--source`, a web address or a PMTiles file) with the pinned pmtiles tool (neoaprs/pmtilestool.py: the one
of the data folder's `bin/`, fetched and checked against its SHA-256 when it is not there, never one that happens to be on the PATH), into DIR (default `neoaprs/maps/` of this package) as `basemap-world.pmtiles` with
`basemap-world.json` beside it, the build it was cut from. A file over 8 MB is refused: the program carries it in every package. Run it when the map should be refreshed, and commit the two files."""
import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

from neoaprs.clock import utcnow
from neoaprs.mapstate import MapError
from neoaprs.paths import default_data_dir
from neoaprs.pmtilestool import BUILDS, VERSION, ToolError, ensure, extract, latest_build, read_header, replace_file
from neoaprs.worldmap import MAPS_DIR, SHIPPED_ZOOM, WORLD_FILE

MAX_BYTES = 8_000_000


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="neoaprs map --world", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=str(default_data_dir()), help="the data folder whose bin/ holds the pmtiles tool (default %(default)s)")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / MAPS_DIR), help="the folder the map is put in (default %(default)s)")
    parser.add_argument("--zoom", type=int, default=SHIPPED_ZOOM, help="the deepest zoom (default %(default)s)")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--build", metavar="YYYYMMDD", help="the daily build of build.protomaps.com to cut from (default: the latest)")
    where.add_argument("--source", help="a web address or a PMTiles file to cut from")
    return parser.parse_args(argv)


def say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def pinned(program: Path) -> None:
    """ToolError unless the program says it is the pinned version."""
    done = subprocess.run([str(program), "version"], capture_output=True, text=True, timeout=30)
    if VERSION not in done.stdout:
        raise ToolError(f"{program} is not go-pmtiles {VERSION} ({done.stdout.strip()!r})")


async def make(args: argparse.Namespace) -> Path:
    out = Path(args.out)
    program = await ensure(Path(args.data).expanduser() / "bin", search_path="")
    pinned(program)
    if args.source:
        source, build = args.source, ""
    elif args.build:
        source, build = f"{BUILDS}/{args.build}.pmtiles", args.build
    else:
        source, build = await latest_build(utcnow())
    out.mkdir(parents=True, exist_ok=True)
    part, final = out / (WORLD_FILE + ".part"), out / WORLD_FILE
    part.unlink(missing_ok=True)
    try:
        await extract(program, source, part, None, args.zoom, on_percent=lambda percent: print(f"fetching {percent}%", flush=True))
        if read_header(part) is None:
            raise ToolError(f"{part.name} is not a PMTiles file")
        size = part.stat().st_size
        if size > MAX_BYTES:
            raise ToolError(f"the world to zoom {args.zoom} is {size / 1e6:.1f} MB, over the {MAX_BYTES / 1e6:.0f} MB the program may carry: use a lower --zoom")
        replace_file(part, final)
    finally:
        part.unlink(missing_ok=True)
    final.with_suffix(".json").write_text(json.dumps({"build": build}) + "\n")
    return final


def main(argv: list[str]) -> int:
    args = parse(argv)
    try:
        final = asyncio.run(make(args))
    except (MapError, ToolError) as e:
        say(f"worldmap: {e}")
        return 1
    print(f"{final}: {final.stat().st_size / 1e6:.1f} MB, zoom 0 to {args.zoom}")
    return 0
