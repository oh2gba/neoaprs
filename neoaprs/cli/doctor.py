"""`neoaprs doctor [--data DIR]`: a checklist of what NeoAPRS needs.

Each line is marked ok, warn or fail, with the fix under every line that is not ok. It covers:
the Python, the data folder, the database and its version, the call, each radio (its type and how
it is reached, or that it is off), the serial ports the system lists (on Linux also the group that
owns them, brltty and ModemManager, which grab USB serial adapters, and Firefox as a Flatpak on
KDE, whose web pop-ups can go missing), a running daemon and its page, the base map and whether
the service is set up. Nothing is changed, written or sent: the database is opened read-only and
the ports are listed, not opened. The exit code is 1 when something failed, otherwise 0 (a warning
is not a failure)."""

import argparse
import asyncio
import platform
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from neoaprs import PROGRAM, VERSION
from neoaprs.backupfolder import way_back
from neoaprs.callsign import call_problem
from neoaprs.config import Config
from neoaprs.configradios import radios_from_rows
from neoaprs.db import READ_WAIT_MS, Db
from neoaprs.dberror import DbClosed, SqlError, StoreError
from neoaprs.instancelock import is_file
from neoaprs.migrations import SCHEMA_VERSION, schema_version
from neoaprs.paths import default_data_dir
from neoaprs.radiospec import RadioSpec, log_name
from neoaprs.serialboards import board_kind
from neoaprs.serialprobe import available_ports
from neoaprs.stopfile import migrating
from neoaprs.store import DB_NAME, Store

from . import servicecmd
from .daemonstate import describe
from .hostcheck import brltty_installed, firefox_flatpak, modemmanager_installed, serial_group_check
from .radiosettings import RADIO_ROWS_FROM, in_force, radio_tables, reached

MIN_PYTHON = (3, 13)
MAP_FILES = ("basemap.pmtiles", "basemap-world.pmtiles")


@dataclass(frozen=True)
class Finding:
    status: str  # "ok", "warn" or "fail"
    text: str
    fix: str = ""


def check_python() -> Finding:
    have = ".".join(str(n) for n in sys.version_info[:3])
    if sys.version_info[:2] >= MIN_PYTHON:
        return Finding("ok", f"Python {have} ({sys.executable})")
    return Finding(
        "fail",
        f"Python {have} is too old: NeoAPRS needs {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer",
        "install NeoAPRS from the AppImage or the .deb of the release, which bring their own Python",
    )


def check_data_folder(data: Path) -> Finding:
    try:
        there = data.exists()
    except OSError as e:
        return Finding(
            "fail",
            f"data folder {data} cannot be looked into: {e.strerror or e}",
            "give it back to your user (chown, chmod), or give another folder with --data",
        )
    if not there:
        return Finding("ok", f"data folder {data} does not exist yet; the daemon makes it when it first starts")
    if not data.is_dir():
        return Finding("fail", f"{data} is not a folder", "give another folder with --data, or move the file away")
    try:
        with tempfile.TemporaryFile(dir=data):
            pass
    except OSError as e:
        return Finding(
            "fail",
            f"data folder {data} cannot be written to ({e})",
            "give a folder of your own with --data, or fix its permissions",
        )
    return Finding("ok", f"data folder {data} (writable)")


@dataclass(frozen=True)
class Database:
    version: int
    rows: dict[str, str]
    radios: tuple[RadioSpec, ...] = ()
    # Why the radios could not be read; they are then none, never the defaults of the flat keys.
    radios_problem: str = ""


async def read_database(path: Path) -> Database:
    """Read the schema version, the settings and the radios of the database without changing it.

    The radios are empty in a file older than the radio rows or made by a newer NeoAPRS.
    """
    db = Db.at(path, READ_WAIT_MS)
    await db.start()
    try:
        store = Store()
        store.use(db, path)
        version = await db.read(schema_version)
        rows = await store.settings()
        if not RADIO_ROWS_FROM <= version <= SCHEMA_VERSION:
            return Database(version, rows)
        try:
            return Database(version, rows, radios_from_rows(*await db.read(radio_tables)))
        except SqlError as e:
            return Database(version, rows, radios_problem=str(e))
    finally:
        await db.close()


def check_database(data: Path) -> tuple[Finding, Config | None, str, bool]:
    """Return the database line, the settings in force (None if unreadable), why the radios could
    not be read ("" if they could), and whether the file predates the radio rows."""
    path = data / DB_NAME
    if not is_file(path):
        return Finding("ok", "no database yet; the daemon makes it when it first starts"), None, "", False
    try:
        found = asyncio.run(read_database(path))
    except (StoreError, SqlError, DbClosed, OSError) as e:
        return (
            Finding(
                "fail",
                f"{path} cannot be read: {e}",
                "if it is damaged, restore a copy from the backup folder next to it, or move it away (the settings and the packets are in it)",
            ),
            None,
            "",
            False,
        )
    version, config, unread = found.version, in_force(found.rows, found.radios), found.radios_problem
    older = version < RADIO_ROWS_FROM
    if version > SCHEMA_VERSION:
        return (
            Finding(
                "fail",
                f"database version {version}: made by a newer NeoAPRS than this one (it knows {SCHEMA_VERSION})",
                f"update NeoAPRS, or {way_back(data, SCHEMA_VERSION)}; the file has not been touched",
            ),
            config,
            "",
            older,
        )
    if version < SCHEMA_VERSION and migrating(data):
        return (
            Finding(
                "ok", f"database version {version}: the daemon is bringing it up to date to version {SCHEMA_VERSION}"
            ),
            config,
            "",
            older,
        )
    if version < SCHEMA_VERSION:
        return (
            Finding(
                "warn",
                f"database version {version}, this NeoAPRS uses {SCHEMA_VERSION}",
                "start the daemon once: it migrates the file and keeps a copy of the old one in backup/",
            ),
            config,
            "",
            older,
        )
    return (
        Finding("ok", f"database {path.name}, version {version} ({path.stat().st_size / 1e6:.1f} MB)"),
        config,
        unread,
        older,
    )


def check_call(config: Config | None) -> Finding:
    call = config.station_call if config is not None else ""
    if not call:
        return Finding(
            "warn",
            "no call is set: NeoAPRS only listens and transmits nothing",
            "set your call on the page (My station tab, Call)",
        )
    problem = call_problem(call)
    if problem:
        return Finding(
            "warn",
            f"the call {call} cannot transmit: {problem}",
            "set your own call on the page (My station tab, Call)",
        )
    return Finding("ok", f"call {call}")


def check_radios(
    config: Config | None, path: Path | None = None, unread: str = "", older: bool = False
) -> list[Finding]:
    """Return a line for each radio: its type and how it is reached, or that it is off.

    Return nothing without a database or if `older`; if `unread`, return that one failure.
    """
    if unread:
        return [
            Finding(
                "fail",
                f"the radios in {path} cannot be read: {unread}",
                "restore a copy from the backup folder next to it (neoaprs db restore)",
            )
        ]
    if config is None or older:
        return []
    if not config.live_radios:
        none = "this station has no radio yet" if not config.radios else "every radio of this station is removed"
        return [
            Finding(
                "warn",
                f"{none}: nothing is heard and nothing is sent",
                "add one: the setup guide, the page (Settings tab, Radio), or neoaprs db radios add TYPE",
            )
        ]
    found = []
    for spec in config.live_radios:
        how = ", ".join(f"{label.lower()} {words}" for label, words in reached(spec)) if spec.enabled else "off"
        found.append(Finding("ok", f"radio {log_name(spec, config.radios)} ({spec.type}): {how}"))
    if not config.enabled_radios:
        found.append(
            Finding(
                "warn",
                "no radio is on: nothing is heard and nothing is sent",
                "tick a radio on the page (Settings tab, Radio)",
            )
        )
    return found


def check_ports() -> Finding:
    ports = available_ports()
    if not ports:
        return Finding(
            "warn",
            "no serial port is listed by the system",
            "plug in the TNC's USB cable (a radio of the type Sound card, or your own Direwolf, needs no serial port)",
        )
    lines = []
    for p in ports:
        ids = f"{p.vid:04x}:{p.pid:04x}" if p.vid is not None and p.pid is not None else "-"
        board = board_kind(p.vid, p.pid)
        lines.append(
            f"    {p.device}  {p.description or '-'}  VID:PID {ids}"
            + (f"  ({board}: the search leaves it alone; name the port to use it)" if board else "")
        )
    return Finding(
        "ok", f"{len(ports)} serial port{'s' if len(ports) != 1 else ''} listed by the system:\n" + "\n".join(lines)
    )


def check_group() -> Finding | None:
    check = serial_group_check()
    if check.status == "ok":
        return Finding("ok", f"you are in the group {check.group}, which owns the serial devices")
    if check.status in ("missing", "relogin"):
        return Finding(
            "warn", f"you cannot open serial devices yet: not in the group {check.group} in this session", check.fix
        )
    return None


def check_grabbers() -> list[Finding]:
    found = []
    if brltty_installed():
        found.append(
            Finding(
                "warn",
                "brltty is installed: it takes USB serial adapters (CH340, CP210x, FTDI) for a braille display, and the port vanishes as the adapter is plugged in",
                "remove it: sudo apt remove brltty   (or the same with your package manager)",
            )
        )
    if modemmanager_installed():
        found.append(
            Finding(
                "warn",
                "ModemManager is installed: it opens new USB serial ports to see whether they are modems, which can disturb the first connection to a TNC",
                "stop it: sudo systemctl disable --now ModemManager   (or sudo apt remove modemmanager)",
            )
        )
    return found


def check_firefox_flatpak() -> Finding | None:
    check = firefox_flatpak()
    if check is None:
        return None
    if check.status == "ok":
        return Finding("ok", "Firefox is a Flatpak: its web notifications go to the desktop's notification service")
    return Finding(
        "warn",
        "Firefox is a Flatpak: on KDE its web notifications can go missing (the desktop portal accepts them and shows none)",
        check.fix,
    )


def check_daemon(data: Path) -> Finding:
    running, line = describe(data)
    if running and "does not" in line:
        return Finding(
            "warn", line, "open the log (neoaprs service logs) to see why; the setting web/port moves the page"
        )
    return Finding("ok", line)


def check_map(data: Path) -> Finding:
    sizes = {name: (data / name).stat().st_size for name in MAP_FILES if is_file(data / name)}
    if not sizes:
        return Finding(
            "warn",
            "no base map yet: the page shows no map",
            "make it on the page (Settings tab, Map, Download) or with `neoaprs map`",
        )
    text = ", ".join(f"{name} {size / 1e6:.0f} MB" for name, size in sizes.items())
    if MAP_FILES[0] not in sizes:
        return Finding(
            "warn",
            f"only the world map: {text}",
            "make the map of your area on the page (Settings tab, Map, Download) or with `neoaprs map`",
        )
    return Finding("ok", f"base map: {text}")


def check_service(data: Path) -> Finding:
    is_set, what = servicecmd.backend_for(sys.platform).installed(servicecmd.Plan(sys.executable, data))
    if is_set:
        return Finding("ok", f"service set up: {what}")
    return Finding(
        "warn", f"the service is not set up ({what}): NeoAPRS runs only while you run it", "neoaprs service install"
    )


def diagnose(data: Path) -> list[Finding]:
    database, config, unread, older = check_database(data)
    findings = [
        check_python(),
        check_data_folder(data),
        database,
        check_call(config),
        *check_radios(config, data / DB_NAME, unread, older),
        check_ports(),
        check_group(),
        *check_grabbers(),
        check_firefox_flatpak(),
        check_daemon(data),
        check_map(data),
        check_service(data),
    ]
    return [f for f in findings if f is not None]


def format_findings(findings: list[Finding]) -> list[str]:
    """Return the lines to print: one per finding, with the fix under each that is not ok."""
    lines = []
    for f in findings:
        lines.append(f"{f.status.upper() if f.status == 'fail' else f.status:<5} {f.text}")
        if f.fix:
            lines.append(f"      fix: {f.fix}")
    return lines


def show(findings: list[Finding]) -> None:
    for line in format_findings(findings):
        print(line)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="neoaprs doctor", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--data", default=str(default_data_dir()), help="the data folder to look at; default %(default)s"
    )
    args = parser.parse_args(argv)
    print(f"{PROGRAM} {VERSION} on {platform.system()} {platform.release()} ({platform.machine()})")
    findings = diagnose(Path(args.data).expanduser().resolve())
    show(findings)
    failed = sum(f.status == "fail" for f in findings)
    warned = sum(f.status == "warn" for f in findings)
    print(f"{failed} to fix, {warned} to look at" if failed or warned else "all is well")
    return 1 if failed else 0
