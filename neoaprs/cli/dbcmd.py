"""`neoaprs db COMMAND`: looks at and changes what NeoAPRS keeps in its one database (the settings, the packets, the stations); the daemon may be running, the database thread of this tool waits a few
seconds for it.

    neoaprs db list                      every setting with its value and whether it is stored or the default
    neoaprs db get station/call          one setting, or one of the rows the daemon keeps that are not settings (`update/install_id`: the number of this installation)
    neoaprs db set station/call OH2GBA-9 a setting, checked like the daemon checks it against the settings stored; the daemon reads settings at its start (or when the page saves them)
    neoaprs db set update/not_counted true  the update check sends the number 0 in place of this installation's own, so that the project does not count this run; `false` takes it away (read at each check)
    neoaprs db radios                    the radios: each with its number, name, kind, type, whether it is on, and its own settings (radio/<id>/<key>) with their values
    neoaprs db radios add kiss [NAME]    a radio of the type (kiss, kenwood-tnc2, kiss-tcp, mercury ...), on unless --off, after the others; a fresh data folder is made, so that a station can be set up
                                         before its first start. The database gives it its number; the daemon takes it at its next start
    neoaprs db set radio/1/port /dev/ttyUSB0  one setting of one radio, checked as the daemon checks it; `get` reads one the same way. A key of before of a radio's setting (serial/port,
                                         hf/enabled, mercury/* ...) is no setting: the answer names the radio's own key
    neoaprs db stations                  the stations the daemon knows: call, kind, last heard, position, packets
    neoaprs db packets -n 50             the latest packets, oldest first, as TNC2 line -> what the parser made of it
    neoaprs db restore                   the copies in the backup folder: date, version of the schema, size, and whether this NeoAPRS can open it
    neoaprs db restore NAME              puts the copy NAME in the place of the database, with NeoAPRS stopped; the file that was there is kept beside it under a name that says when

--data DIR is the data folder (default: the one the daemon uses). `set`, `radios add` and `restore` are the writes; everything else opens the database for reading and changes nothing."""
import argparse
import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from neoaprs.backupfolder import FOLDER_NAME, RestoreRefused, before_copy, can_open, copies, restore, stamp as copy_stamp
from neoaprs.cli.redaction import shown_value
from neoaprs.config import BY_KEY, DEFAULTS, HF_DIAL, INSTALL_ID, LAST_PORT, RADIO_STATE, STATE_BEFORE_31, STATE_KEYS, Config
from neoaprs.configradios import FLAT_HOMES, FLAT_KINDS, flat_moved, flat_now, radio_key_of
from neoaprs.configtypes import boolean
from neoaprs.radiospec import KIND_WORDS, RadioSpec
from neoaprs.radiotypes import BY_KEY as TYPES
from neoaprs.db import READ_WAIT_MS, Db
from neoaprs.dberror import DbClosed, SqlError, StoreError
from neoaprs.dbopen import open_connection
from neoaprs.pairsetting import call_refusal
from neoaprs.instancelock import is_file
from neoaprs.migrations import SCHEMA_VERSION, schema_version
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.packetcodec import tnc2
from neoaprs.packetlog import PacketLog
from neoaprs.paths import default_data_dir
from neoaprs.skeds import SKED_TOKEN
from neoaprs.versions import NOT_COUNTED
from neoaprs.store import DB_NAME, Store

from .dbwrite import held
from .output import say
from .dbradios import Radios, add_radio, show_radios, stamp, stored_radios
from .radiosettings import SHOWN_KEYS, in_force, own_key, port_problem, shown_settings, stored_text_of, value_text

PROG = "neoaprs db"
WRITE_WAIT_MS = 5000


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=PROG, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=str(default_data_dir()), help="the data folder (default %(default)s)")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def command(name: str, help: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help)
        sub.add_argument("--data", default=argparse.SUPPRESS, help="the data folder, as given before the command (the subcommand takes it too)")          # (no default of its own: it would put the default over the one given before the command)
        return sub

    command("list", "every setting")
    command("get", "one setting").add_argument("key")
    setter = command("set", "change a setting")
    setter.add_argument("key")
    setter.add_argument("value")
    radios = command("radios", "the radios and their own settings, or add one")
    radios.add_argument("add", nargs="?", choices=["add"], help="add a radio of TYPE")
    radios.add_argument("type", nargs="?", default="", help="the type of the radio to add (kiss, kenwood-tnc2, kiss-tcp, mercury, dummy, dummy-hf ...)")
    radios.add_argument("name", nargs="?", default="", help="its name (none: the type's)")
    radios.add_argument("--off", action="store_true", help="add it switched off")
    command("stations", "the stations the daemon knows")
    command("restore", "list the copies in the backup folder, or put one back").add_argument("name", nargs="?", default="", help="the copy to put back, as the list names it")
    packets = command("packets", "the latest packets")
    packets.add_argument("-n", type=int, default=20, help="how many (default 20)")
    return parser.parse_args(argv)


def daemon_state(key: str) -> bool:
    """A row only the daemon writes, which `set` refuses: the station's state, a radio's own (its beacon's last send; the port its search found is radio 1's alone), and the two rows of before migration 31."""
    radio = radio_key_of(key)
    return key in STATE_KEYS or key in STATE_BEFORE_31 or key == LAST_PORT or (radio is not None and radio[1] in RADIO_STATE and radio[1] != "last_port")


def kept_note(key: str) -> str:
    if key in STATE_KEYS or key in STATE_BEFORE_31:
        return "kept by the daemon (when it last sent, how the map stands), not a setting"
    if key == HF_DIAL:
        return "kept by the daemon (the HF dial the version page named last), not a setting"
    if key == SKED_TOKEN:
        return "kept by the daemon (the secret that goes with the HF tests of this installation), not a setting"
    if key == NOT_COUNTED:
        return "whether the update check sends the number 0, so that this run is not counted (set with db set), not a setting"
    if radio_key_of(key) is not None:
        return "kept by the daemon (a radio's own: when its beacon or its status last sent, the port its search found), not a setting"
    return "kept by the daemon (the number of this installation), not a setting" if key == INSTALL_ID else "stored, not a setting of this NeoAPRS"


async def show_settings(store: Any, only: str | None) -> int:
    rows, radios = await store.settings(), await stored_radios(store)
    if only is not None:
        return show_one(rows, radios, only)
    config = in_force(rows, radios.specs)
    shown = shown_settings(config)
    width = max(len(k) for k in shown)
    for key in shown:
        print(f"{key:<{width}}  {shown[key]:<18}  {'default' if stored_text_of(key, rows) is None else 'stored'}")
    for key in sorted(set(rows) - set(shown)):
        print(f"{key:<{width}}  {shown_value(key, rows[key]):<18}  {before_note(key, config) or kept_note(key)}")
    return 0


def before_note(key: str, config: Config) -> str:
    """For a row of a key of before of a radio's setting, which nothing reads (a folder set up by a build of the round before its first start, whose radio was never made), where its value goes now:
    the sentence of `moved`, and while the station has no radio, that one is added first; "" for any other key."""
    found = moved(key, config)
    if not found:
        return ""
    where = found.split("no such setting: ", 1)[-1]
    return f"a key of before, not read: {where}" + ("" if config.live_radios else " (add the radio first: neoaprs db radios add TYPE)")


def stored_note(key: str, text: str | None, check: Callable[[str], object]) -> str:
    """What `get` says under a value when it is not the stored one: that the setting is not stored, or that it is stored as a text that is no value (`check` refuses it); "" when it is."""
    if text is None:
        return f"{key} is not stored; this is the default"
    try:
        check(text)
    except ValueError:
        return f"{key} is stored as {shown_value(key, text)!r}, which is not a value: the default is in force"
    return ""


def moved(key: str, config: Config = DEFAULTS) -> str:
    """For a key of before of a radio's setting (`serial/port`, `hf/enabled`), which is no setting of the command line, the sentence that names where it is now with the radios of `config`: the page's
    (configradios.flat_moved) for a radio's own key, and for its type and Enable, which only the page changes, the radio's by its number (`flat_now`); "" for any other key."""
    setting = BY_KEY.get(key)
    found = None if setting is None else flat_moved(setting.attr, config.radios)
    if setting is None or found is None:
        return ""
    id, field = FLAT_HOMES[setting.attr]
    if field in ("type", "enabled"):
        radio = flat_now(setting.attr, config.radios)
        whose = f"the {KIND_WORDS[FLAT_KINDS[id]]} radio's" if radio is None else f"radio {radio.id}'s"
        return f"{key}: no such setting: it is {whose} {'Enable' if field == 'enabled' else 'type'} (Settings tab, Radio) now"
    return f"{key}: {found}"


def no_setting_now(key: str, specs: tuple[RadioSpec, ...], rows: dict[str, str]) -> int:
    """`get` or `set` of a key of before of a radio's setting: the sentence that names where it is now (`moved`), and the exit code 2."""
    say(f"{PROG}: {moved(key, in_force(rows, specs))}")
    return 2


def show_one(rows: dict[str, str], radios: Radios, only: str) -> int:
    """`get`: a setting, a radio's own setting (`radio/<id>/<key>`) or a row the daemon keeps; the exit code."""
    specs = radios.specs
    if moved(only):
        return no_setting_now(only, specs, rows)
    if only in SHOWN_KEYS:
        print(shown_settings(in_force(rows, specs))[only])
        if note := stored_note(only, stored_text_of(only, rows), lambda t: Config.check(only, t)):
            say(f"{PROG}: {note}")
        return 0
    radio = own_key(only, specs)
    if radio is not None:
        spec, key = radio
        if spec is None:
            say(f"{PROG}: {only}: there is no such radio (try radios)")
            return 2
        print(shown_value(only, value_text(spec, key)))
        if note := stored_note(only, radios.own.get((spec.id, key)), lambda t: Config.check_radio(spec, key, t)):
            say(f"{PROG}: {note}")
        return 0
    if only in rows:                                # (a row the daemon keeps that is not a setting; a secret one is shown as its length only)
        print(shown_value(only, rows[only]))
        return 0
    say(f"{PROG}: {only}: no such setting (try list, or radios for the settings of a radio)")
    return 2


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


def checked_row(key: str, value: str) -> str:
    """The text of `update/not_counted` as it is kept, `true` or `false`; ValueError naming the key when `value` is neither."""
    try:
        return "true" if boolean(value) else "false"
    except ValueError as e:
        raise ValueError(f"{key}: {e}") from None


async def store_setting(store: Store, key: str, value: str, text: str) -> int:
    """`set`: the value `text` (`value` as the setting keeps it) stored when it goes with the settings stored, by the rules between settings that a save of the page applies; the exit code. With the
    radios stored, `serial/last_port` is radio 1's own state row (config.LAST_PORT), which is read in its place. A key of before of a radio's setting is refused with where it is now."""
    rows, radios = await store.settings(), (await stored_radios(store)).specs
    if moved(key):
        return no_setting_now(key, radios, rows)
    try:
        if key != NOT_COUNTED:
            config = Config.checked(in_force(rows, radios), {key: value})
            if key == "station/call" and (refusal := call_refusal(config.station_call, config.pairs)):
                raise refusal
    except ValueError as e:
        say(f"{PROG}: {e}")
        return 2
    if not await store.put_setting(LAST_PORT if radios and key == "serial/last_port" else key, text):
        say(f"{PROG}: {key} could not be stored")
        return 1
    print(f"{key} = {text}")
    return 0


async def store_radio_setting(store: Store, key: str, value: str) -> int:
    """`set radio/<id>/<key> VALUE`: one setting of one radio, checked by its field, and its port by the radio's type (a TCP type connects to its KISS server, not to a serial device); the exit code."""
    radios = (await stored_radios(store)).specs
    id, own = radio_key_of(key) or (0, "")
    spec = next((s for s in radios if s.id == id), None)
    if spec is None or spec.removed:
        say(f"{PROG}: {key}: there is no radio {id}{' any more: it was removed' if spec is not None else ''} (try radios)")
        return 2
    try:
        text = Config.check_radio(spec, own, value)
        if own == "port" and (problem := port_problem(replace(spec, settings={**spec.settings, own: text}))):
            raise ValueError(f"{key}: {problem}")
    except ValueError as e:
        say(f"{PROG}: {e}")
        return 2
    if not await store.put_radio_settings(id, {own: text}):
        say(f"{PROG}: {key} could not be stored")
        return 1
    print(f"{key} = {text}")
    return 0


def list_copies(data: Path) -> int:
    found = copies(data / FOLDER_NAME)
    if not found:
        say(f"{PROG}: no copy of the database in {data / FOLDER_NAME}")
        return 0
    width = max(len(c.name) for c in found)
    before = before_copy(data / FOLDER_NAME)
    for c in found:
        usable = "" if can_open(c, SCHEMA_VERSION) else "  (of a newer NeoAPRS: cannot be opened by this one)"
        older = f"  (taken before the update to version {before.new}: the NeoAPRS you had before opens it)" if before is not None and c.path == before.path else ""
        print(f"{c.name:<{width}}  {copy_stamp(c.made)}  version {c.version:<3}  {c.size / 1e6:8.1f} MB{usable}{older}")
    return 0


def restore_copy(data: Path, name: str) -> int:
    """`restore NAME`: the exit code of putting the copy in the place of the database, or of the reason it was not done."""
    try:
        copy, aside = restore(data, DB_NAME, name, SCHEMA_VERSION)
    except RestoreRefused as e:
        say(f"{PROG}: {e}")
        return 1
    say(f"{PROG}: {copy.name} (version {copy.version}, of {copy_stamp(copy.made)}) is now the database" + (f"; the file that was there is kept as {aside.name}" if aside is not None else ""))
    return 0


def before_opening(args: argparse.Namespace, path: Path) -> int | str:
    """What is checked before the database is opened: for `set`, the value of a setting of the station by its key (the text as it is kept), and that the data folder can be made; for any other
    command, and for a radio's own setting (checked by its radio's field once the database is read), that the file is there; a key of before of a radio's setting is answered with where it is now,
    by the database's radios where there is a database. The text, or the exit code of the refusal."""
    if args.command in ("set", "get") and moved(args.key):
        if is_file(path):
            return ""
        say(f"{PROG}: {moved(args.key, replace(DEFAULTS, radios=()))}")
        return 2
    if args.command == "radios" and args.add:
        if not args.type:
            say(f"{PROG}: radios add: which type? (the types are {', '.join(TYPES)})")
            return 2
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            say(f"{PROG}: the data folder {path.parent} cannot be made or used: {e.strerror or e}")
            return 1
        return ""
    if args.command == "set" and daemon_state(args.key):
        say(f"{PROG}: {args.key}: {kept_note(args.key)}" + ("; db set serial/last_port sets it" if args.key == LAST_PORT else ""))
        return 2
    if args.command == "set" and args.key.startswith("radio/") and radio_key_of(args.key) is None:
        say(f"{PROG}: {args.key}: a radio's setting is radio/<number>/<key> (try radios)")
        return 2
    if args.command == "set" and radio_key_of(args.key) is None:
        try:
            text = checked_row(args.key, args.value) if args.key == NOT_COUNTED else Config.check(args.key, args.value)
        except ValueError as e:
            say(f"{PROG}: {e}")
            return 2
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            say(f"{PROG}: the data folder {path.parent} cannot be made or used: {e.strerror or e}")
            return 1
        return text
    if not is_file(path):
        say(f"{PROG}: there is no database at {path}" + (", so no radio" if args.command == "set" else "") + " (has the daemon run? --data DIR)")
        return 1
    return ""


async def answer(args: argparse.Namespace, store: Store, log: PacketLog, text: str) -> int:
    """The command on the open database; its exit code."""
    if args.command == "set":
        return await (store_radio_setting(store, args.key, args.value) if radio_key_of(args.key) is not None else store_setting(store, args.key, args.value, text))
    if args.command in ("list", "get"):
        return await show_settings(store, args.key if args.command == "get" else None)
    if args.command == "radios":
        return await (add_radio(store, args.type, args.name, not args.off) if args.add else show_radios(store))
    if args.command == "stations":
        return await show_stations(log)
    return await show_packets(log, args.n)


async def run(args: argparse.Namespace) -> int:
    if args.command == "restore":
        data = Path(args.data).expanduser()
        return restore_copy(data, args.name) if args.name else list_copies(data)
    path = Path(args.data).expanduser() / DB_NAME
    writing = args.command == "set" or (args.command == "radios" and bool(args.add))
    text = before_opening(args, path)
    if isinstance(text, int):
        return text
    with held(path, writing, WRITE_WAIT_MS) as refused:                     # (the daemon migrates the file, another NeoAPRS writes it, or one of the version before has it open: dbwrite.py)
        if refused:
            say(f"{PROG}: {path}: {refused}")
            return 1
        db = Db(lambda: open_connection(path, WRITE_WAIT_MS)) if writing else Db.at(path, READ_WAIT_MS)
        try:
            await db.start()
        except (StoreError, SqlError) as e:
            say(f"{PROG}: {path}: {e}")
            return 1
        store = Store()
        store.use(db, path)
        try:
            version = await db.read(schema_version)
            if version < SCHEMA_VERSION and not writing:
                say(f"{PROG}: {path} is of version {version}, this NeoAPRS needs {SCHEMA_VERSION}: start the daemon once, it migrates the file")
                return 1
            return await answer(args, store, PacketLog(db), text)
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
    if args.command == "set" or (args.command == "radios" and args.add):
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
