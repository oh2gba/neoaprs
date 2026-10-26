"""`summary.txt` of the support bundle: the one screen that answers "what version, what system, what is wrong" for the person who reads the bundle. `Facts` is what the gatherers found (any part of it may be
missing: a bundle is made for a computer that is in trouble), `summary_text` lays it out. Pure: no file is read here."""
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from neoaprs.config import Config
from neoaprs.versions import InstallInfo

Section = tuple[str, list[tuple[str, str]]]
LOG_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}Z?)  (DEBUG|INFO|WARNING|ERROR|CRITICAL)  (.*)$")
MAX_GROUPS = 25
MAX_MESSAGE = 240
# the web server's lines for the optional files that are not there (the base map before it is installed, the icon, the map fonts): left out of the list of problems, not of the log
OPTIONAL_FILE_REQUEST = re.compile(r"^(?:(?:403|404) (?:HEAD|GET) /basemap\S*\.pmtiles|404 (?:HEAD|GET) (?:/favicon\.ico|/fonts/\S*\.pbf))(?:\s|$)")
ADDRESS = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b|\[[0-9a-fA-F:]{3,}\](?::\d+)?")
NUMBER = re.compile(r"0x[0-9a-fA-F]+|\d+(?:\.\d+)*")
MAX_CHECKS = 8
NO_DAEMON = "not known: the daemon was not asked (see the log below)"


@dataclass(frozen=True)
class Problems:
    """The warnings and errors of a log as `summary_text` lists them: the lines of the groups, how many request lines for optional files were left out, and how many groups did not fit."""
    lines: list[str]
    left_out: int
    more: int


@dataclass(frozen=True)
class DbFacts:
    """The database file as the bundle found it. `version` is None when it could not be read, and `problem` says why."""
    version: int | None
    expected: int
    size: int
    wal_size: int
    problem: str = ""


@dataclass
class Facts:
    version: str
    install: InstallInfo
    frozen: bool
    system: str
    machine: str
    python: str
    data_dir: Path
    made_at: datetime
    made_by: str
    daemon_running: bool
    daemon_since: datetime | None = None
    config: Config | None = None
    settings_problem: str = ""
    live: dict[str, Any] | None = None             # state.json, when the running daemon made the bundle
    page_url: str = ""
    database: DbFacts | None = None
    problems: Problems = field(default_factory=lambda: Problems([], 0, 0))
    checks: str = ""                               # doctor.txt, when it could be made


def stamp(t: datetime | None) -> str:
    return "never" if t is None else t.strftime("%Y-%m-%d %H:%M:%SZ")


def duration(seconds: float) -> str:
    """`3 d 4 h 12 min`, `4 min 5 s`: the two largest units that are not zero."""
    left = int(max(0, seconds))
    parts = [(left // 86400, "d"), (left % 86400 // 3600, "h"), (left % 3600 // 60, "min"), (left % 60, "s")]
    shown = [f"{n} {unit}" for n, unit in parts if n]
    return " ".join(shown[:2]) or "0 s"


def megabytes(size: int) -> str:
    return f"{size / 1e6:.1f} MB"


def _local_time(t: datetime) -> str:
    local = t.astimezone()
    offset = local.strftime("%z")
    return f"{local:%Y-%m-%d %H:%M:%S} ({local.tzname() or '?'}, UTC{offset[:3]}:{offset[3:]})" if offset else f"{local:%Y-%m-%d %H:%M:%S}"


def _daemon_line(f: Facts) -> str:
    if not f.daemon_running:
        return "not running (nothing holds the data folder)"
    if f.live is not None:
        uptime = f.live.get("daemon", {}).get("uptime_sec")
        since = f.live.get("daemon", {}).get("started_at")
        return f"running, up {duration(uptime)}" + (f" (since {since})" if since else "") if isinstance(uptime, (int, float)) else "running"
    if f.daemon_since is not None:
        return f"running, up {duration((f.made_at - f.daemon_since).total_seconds())} (since {stamp(f.daemon_since)}, by its log)"
    return "running (a daemon holds the data folder)"


def _position(c: Config) -> str:
    if c.gps_source == "gpsd":
        return f"gpsd at {c.gps_host}"
    if c.gps_source == "serial":
        return f"serial GPS on {c.gps_device or '(no port set)'} at {c.gps_baud} baud"
    return "Fixed" + ("" if c.station_position else " (no position set)")


def _beacon(f: Facts, c: Config) -> str:
    if not c.beacon_on:
        return "off (interval 0)" + ("" if c.station_transmit else "; receive only")
    text = f"on, SmartBeaconing (travelling: {c.beacon_travel})" if c.mobile else f"on, every {c.beacon_interval_min} min"
    if not c.station_transmit:
        text += "; receive only: nothing is sent"
    beacon = (f.live or {}).get("beacon")
    if isinstance(beacon, dict):
        text += f"; last sent {beacon.get('last_sent') or 'never'}, next due {beacon.get('next_due') or 'none'}"
        if beacon.get("problem"):
            text += f"; not sent because: {beacon['problem']}"
    return text


def _radio(f: Facts, c: Config) -> list[tuple[str, str]]:
    tnc = (f.live or {}).get("tnc")
    where = f"{c.tcp_host}:{c.tcp_port}" if c.profile.transport == "tcp" else (c.serial_port or "(found by searching)")
    if not isinstance(tnc, dict):
        return [("TNC profile", c.tnc_profile), ("Port", f"{where}"), ("Speed", f"{c.tnc_baud} baud"), ("State", NO_DAEMON)]
    port = tnc.get("path") or where
    return [("TNC profile", c.tnc_profile), ("Port", f"{port}"), ("Speed", f"{tnc.get('baud') or c.tnc_baud} baud"),
            ("State", str(tnc.get("state", "?"))), ("Problem", str(tnc.get("problem") or tnc.get("last_error") or "none"))]


def _gps(f: Facts, c: Config) -> list[tuple[str, str]]:
    gps = (f.live or {}).get("gps")
    if isinstance(gps, dict):
        return [("GPS state", str(gps.get("state", "?"))), ("GPS problem", str(gps.get("problem") or "none"))]
    return [("GPS state", "off" if c.gps_source == "off" else NO_DAEMON)]


def _web(f: Facts, c: Config) -> str:
    web = (f.live or {}).get("web", {})
    bind = web.get("address") or ("every interface" if c.web_network else "127.0.0.1")
    port = web.get("port") or c.web_port
    text = f"{bind}, port {port}" if f.daemon_running or web else f"would listen on {bind}, port {c.web_port}"
    text += f"; network {'on' if c.web_network else 'off'}; https {'on' if c.web_https else 'off'}"
    if f.page_url:
        text += f"; the log says the page is at {f.page_url}"
    return text


def _database(db: DbFacts | None) -> str:
    if db is None:
        return "not looked at"
    if db.version is None:
        return f"could not be read: {db.problem}"
    note = "" if db.version == db.expected else f"; this NeoAPRS expects {db.expected}"
    return f"schema version {db.version}{note}, {megabytes(db.size)}" + (f", log file {megabytes(db.wal_size)}" if db.wal_size else "")


def _checks(doctor_text: str) -> list[tuple[str, str]]:
    """The checks of the doctor that are not ok, and its verdict."""
    lines = [line for line in doctor_text.splitlines() if line.strip()]
    rows = [(line[:5].strip(), line[6:]) for line in lines if line.startswith(("FAIL", "warn"))]
    return [*rows[:MAX_CHECKS], *([("", f"... and {len(rows) - MAX_CHECKS} more")] if len(rows) > MAX_CHECKS else []), ("Result", lines[-1] if lines else "")]


def sections(f: Facts) -> list[Section]:
    install = f.install.kind + (" (a service starts it)" if f.install.service else "")
    local = _local_time(f.made_at)
    what: list[tuple[str, str]] = [
        ("NeoAPRS", f"{f.version}, installed as {install}" + (f" ({f.install.appimage})" if f.install.appimage else "")),
        ("System", f"{f.system}, {f.machine}"),
        ("Python", f"{f.python}, {'frozen program' if f.frozen else 'not frozen'}"),
        ("Data folder", str(f.data_dir)),
        ("Made", f"{stamp(f.made_at)} (UTC), local {local}; by {f.made_by}"),
        ("Daemon", _daemon_line(f)),
    ]
    out: list[Section] = [("What", what)]
    if f.config is None:
        out.append(("Settings", [("Could not be read", f.settings_problem or "no settings were found")]))
    else:
        c = f.config
        out.append(("Station", [("Call", c.station_call or "(none set: nothing is transmitted)"), ("Position", _position(c)), ("Beacon", _beacon(f, c))]))
        out.append(("Radio", _radio(f, c)))
        out.append(("GPS", _gps(f, c)))
        out.append(("Web page", [("Listens", _web(f, c))]))
    out.append(("Database", [("File", _database(f.database))]))
    if f.checks:
        out.append(("Checks (doctor.txt has the fixes)", _checks(f.checks)))
    return out


def summary_text(f: Facts) -> str:
    lines = ["NeoAPRS support summary", "=======================", ""]
    for title, rows in sections(f):
        lines.append(title)
        width = max(len(label) for label, _ in rows)
        lines.extend(f"  {label + ':':<{width + 1}} {value}" for label, value in rows)
        lines.append("")
    lines.append("The warnings and errors of the log, each message once (COUNT× LAST-TIME LEVEL MESSAGE; errors first, then the newest; logs/neoaprs.log has every line):")
    lines.extend(f"  {line}" for line in f.problems.lines or ["none"])
    if f.problems.more:
        lines.append(f"  ... and {f.problems.more} more messages, older ones")
    lines.append(f"Left out of this list: {f.problems.left_out} web server request lines for optional files that are not there (the base map, favicon.ico, the map fonts).")
    return "\n".join(lines) + "\n"


def message_key(level: str, message: str) -> str:
    """What makes two messages the same one: the level and the words, with the addresses, the numbers and the durations taken out."""
    return f"{level} {NUMBER.sub('#', ADDRESS.sub('<address>', message))}"


def problem_groups(log_lines: list[str]) -> Problems:
    """The WARNING, ERROR and CRITICAL records of a log in groups of the same message (`message_key`), each as `COUNT× LAST-TIME LEVEL MESSAGE` with the message as last seen (for one that was followed by a traceback, the exception line too, on a line of its own):
    ERROR and CRITICAL first, then WARNING, the newest first in each, at most MAX_GROUPS. The requests for optional files are counted in `left_out` and are in no group."""
    groups: dict[str, list[Any]] = {}                      # key -> [count, order of the last, time, level, message, exception line]
    left_out = 0
    last: list[Any] | None = None
    for order, line in enumerate(log_lines):
        match = LOG_LINE.match(line)
        if match:
            last = None
            when, level, message = match.groups()
            if level not in ("WARNING", "ERROR", "CRITICAL"):
                continue
            if OPTIONAL_FILE_REQUEST.match(message):
                left_out += 1
                continue
            last = groups.setdefault(message_key(level, message), [0, 0, "", "", "", ""])
            last[:] = [last[0] + 1, order, when, level, message if len(message) <= MAX_MESSAGE else message[:MAX_MESSAGE - 1] + "…", ""]
        elif last is not None and line.strip():
            last[5] = f"    {line.strip()}"                   # (only the last line of the lines that follow)
    ranked = sorted(groups.values(), key=lambda g: (g[3] == "WARNING", -g[1]))
    lines: list[str] = []
    for count, _, when, level, message, exception in ranked[:MAX_GROUPS]:
        lines.append(f"{count}× {when} {level:<8} {message}")
        if exception:
            lines.append(exception)
    return Problems(lines, left_out, max(0, len(ranked) - MAX_GROUPS))
