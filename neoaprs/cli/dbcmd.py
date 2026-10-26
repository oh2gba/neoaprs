"""`neoaprs db COMMAND`: looks at and changes what NeoAPRS keeps in its one database (the settings, the packets, the stations); the daemon may be running, the database thread of this tool waits a few
seconds for it.

    neoaprs db list                      every setting with its value and whether it is stored or the default
    neoaprs db get station/call          one setting
    neoaprs db set station/call OH2GBA-9 a setting, checked like the daemon checks it; the daemon reads settings at its start (or when the page saves them)
    neoaprs db stations                  the stations the daemon knows: call, kind, last heard, position, packets
    neoaprs db packets -n 50             the latest packets, oldest first, as TNC2 line -> what the parser made of it

--data DIR is the data folder (default: the one the daemon uses). Everything but `set` opens the database for reading and changes nothing; `set` is the only write."""
import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from neoaprs.config import BY_KEY, DEFAULTS, STATE_KEYS, Config
from neoaprs.db import Db
from neoaprs.dberror import DbClosed, SqlError, StoreError
from neoaprs.dbopen import open_connection
from neoaprs.migrations import SCHEMA_VERSION, schema_version
from neoaprs.migrations2 import MIGRATION_LOG
from neoaprs.packetcodec import tnc2
from neoaprs.packetlog import PacketLog
from neoaprs.paths import default_data_dir
from neoaprs.store import DB_NAME, Store

from .output import say

PROG = "neoaprs db"
READ_WAIT_MS = 3000
WRITE_WAIT_MS = 5000


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=PROG, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=str(default_data_dir()), help="the data folder (default %(default)s)")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    commands.add_parser("list", help="every setting")
    commands.add_parser("get", help="one setting").add_argument("key")
    setter = commands.add_parser("set", help="change a setting")
    setter.add_argument("key")
    setter.add_argument("value")
    commands.add_parser("stations", help="the stations the daemon knows")
    packets = commands.add_parser("packets", help="the latest packets")
    packets.add_argument("-n", type=int, default=20, help="how many (default 20)")
    return parser.parse_args(argv)


def stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%SZ")


async def show_settings(store: Any, only: str | None) -> int:
    rows = await store.settings()
    defaults = DEFAULTS.to_data()
    if only is not None:
        if only not in BY_KEY:
            say(f"{PROG}: {only}: no such setting (try list)")
            return 2
        print(rows.get(only, defaults[only]))
        if only not in rows:
            say(f"{PROG}: {only} is not stored; this is the default")
        return 0
    shown = Config.from_data(rows).to_data()
    width = max(len(k) for k in defaults)
    for key in defaults:
        print(f"{key:<{width}}  {shown[key]:<18}  {'stored' if key in rows else 'default'}")
    for key in sorted(set(rows) - set(defaults)):
        print(f"{key:<{width}}  {rows[key]:<18}  {'kept by the daemon (when it last sent, how the map stands), not a setting' if key in STATE_KEYS else 'stored, not a setting of this NeoAPRS'}")
    return 0


async def show_stations(log: Any) -> int:
    stations = await log.stations()
    print(f"{'call':<10} {'kind':<8} {'last heard':<21} {'position':<18} {'packets':>7}")
    for s in stations:
        where = f"{s.lat:.4f} {s.lon:.4f}" if s.lat is not None and s.lon is not None else "-"
        print(f"{s.call:<10} {s.kind:<8} {stamp(s.last_heard):<21} {where:<18} {s.packets:>7}")
    say(f"{PROG}: {len(stations)} stations")
    return 0


async def show_packets(log: Any, count: int) -> int:
    for p in reversed(await log.recent(count)):
        print(f"{stamp(p.heard_at)}  {'sent ' if p.direction == 'out' else ''}{tnc2(p)} -> {p.summary}")
    return 0


async def run(args: argparse.Namespace) -> int:
    path = Path(args.data).expanduser() / DB_NAME
    writing = args.command == "set"
    if writing:
        try:
            text = Config.check(args.key, args.value)
        except ValueError as e:
            say(f"{PROG}: {e}")
            return 2
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.is_file():
        say(f"{PROG}: there is no database at {path} (has the daemon run? --data DIR)")
        return 1
    db = Db(lambda: open_connection(path, WRITE_WAIT_MS)) if writing else Db.at(path, READ_WAIT_MS)
    try:
        await db.start()
    except (StoreError, SqlError) as e:
        say(f"{PROG}: {path}: {e}")
        return 1
    store = Store()
    store.use(db, path)
    log = PacketLog(db)
    try:
        version = await db.read(schema_version)
        if version < SCHEMA_VERSION and not writing:
            say(f"{PROG}: {path} is of version {version}, this NeoAPRS needs {SCHEMA_VERSION}: start the daemon once, it migrates the file")
            return 1
        if writing:
            if not await store.put_setting(args.key, text):
                say(f"{PROG}: {args.key} could not be stored")
                return 1
            print(f"{args.key} = {text}")
            return 0
        if args.command in ("list", "get"):
            return await show_settings(store, args.key if args.command == "get" else None)
        if args.command == "stations":
            return await show_stations(log)
        return await show_packets(log, args.n)
    except (SqlError, DbClosed) as e:
        say(f"{PROG}: {path}: {e}")
        return 1
    finally:
        await db.close()


def main(argv: list[str]) -> int:
    args = parse(argv)
    logger = logging.getLogger(MIGRATION_LOG)
    said = logging.StreamHandler()                           # `set` may be the first to open a file of an older version: what its migrations did is said here, where nothing else logs
    said.setFormatter(logging.Formatter("%(message)s"))
    if args.command == "set":
        logger.addHandler(said)
    was = logger.level
    logger.setLevel(logging.INFO)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130
    finally:
        logger.removeHandler(said)
        logger.setLevel(was)
