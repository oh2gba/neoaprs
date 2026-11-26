"""`summary.txt` of the support bundle: one screen with the version, the system and what is wrong.

`Facts` is what the gatherers found (any part may be missing, as the computer may be in trouble);
`summary_text` lays it out. No file is read here."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from neoaprs.beaconrule import interval_words, send_on_radios
from neoaprs.config import Config
from neoaprs.emailrule import email_radio
from neoaprs.radiospec import RadioId, RadioSpec, in_force_set, log_name
from neoaprs.versions import InstallInfo

from .radiosettings import is_mercury, reached

Section = tuple[str, list[tuple[str, str]]]
LOG_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}Z?)  (DEBUG|INFO|WARNING|ERROR|CRITICAL)  (.*)$")
MAX_GROUPS = 25
MAX_MESSAGE = 240
# Web server requests for optional files that may be absent (base map, icon, map fonts); they are
# left out of the problem list, not of the log.
OPTIONAL_FILE_REQUEST = re.compile(
    r"^(?:(?:403|404) (?:HEAD|GET) /basemap\S*\.pmtiles|404 (?:HEAD|GET) (?:/favicon\.ico|/fonts/\S*\.pbf))(?:\s|$)"
)
ADDRESS = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b|\[[0-9a-fA-F:]{3,}\](?::\d+)?")
NUMBER = re.compile(r"0x[0-9a-fA-F]+|\d+(?:\.\d+)*")
MAX_CHECKS = 8
MAX_CARDS = 12  # more are folded by device name (a virtual mixer lists every pair of its ends)
NO_DAEMON = "not known: the daemon was not asked (see the log below)"


@dataclass(frozen=True)
class Problems:
    """The grouped warning and error lines, the optional-file requests left out, the overflow."""

    lines: list[str]
    left_out: int
    more: int


@dataclass(frozen=True)
class DbFacts:
    """The database file as found. `version` is None if it could not be read; `problem` says why."""

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
    live: dict[str, Any] | None = None  # state.json, when the running daemon made the bundle
    page_url: str = ""
    database: DbFacts | None = None
    problems: Problems = field(default_factory=lambda: Problems([], 0, 0))
    checks: str = ""  # doctor.txt, when it could be made
    # Why the stored radios could not be read; the radios of `config` are then not the station's.
    radios_problem: str = ""


def stamp(t: datetime | None) -> str:
    return "never" if t is None else t.strftime("%Y-%m-%d %H:%M:%SZ")


def duration(seconds: float) -> str:
    """Return the two largest non-zero units, e.g. `3 d 4 h` or `4 min 5 s`."""
    left = int(max(0, seconds))
    parts = [(left // 86400, "d"), (left % 86400 // 3600, "h"), (left % 3600 // 60, "min"), (left % 60, "s")]
    shown = [f"{n} {unit}" for n, unit in parts if n]
    return " ".join(shown[:2]) or "0 s"


def megabytes(size: int) -> str:
    return f"{size / 1e6:.1f} MB"


def _local_time(t: datetime) -> str:
    local = t.astimezone()
    offset = local.strftime("%z")
    return (
        f"{local:%Y-%m-%d %H:%M:%S} ({local.tzname() or '?'}, UTC{offset[:3]}:{offset[3:]})"
        if offset
        else f"{local:%Y-%m-%d %H:%M:%S}"
    )


def _daemon_line(f: Facts) -> str:
    if not f.daemon_running:
        return "not running (nothing holds the data folder)"
    if f.live is not None:
        uptime = f.live.get("daemon", {}).get("uptime_sec")
        since = f.live.get("daemon", {}).get("started_at")
        return (
            f"running, up {duration(uptime)}" + (f" (since {since})" if since else "")
            if isinstance(uptime, (int, float))
            else "running"
        )
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
    text = (
        f"on, SmartBeaconing (travelling: {c.beacon_travel})"
        if c.mobile
        else f"on, every {interval_words(c.beacon_interval_min, c.radios)}"
    )
    if not c.station_transmit:
        text += "; receive only: nothing is sent"
    beacon = (f.live or {}).get("beacon")
    if isinstance(beacon, dict):
        text += f"; last sent {beacon.get('last_sent') or 'never'}, next due {beacon.get('next_due') or 'none'}"
        if beacon.get("problem"):
            text += f"; not sent because: {beacon['problem']}"
    return text


# The things with a per-radio Send on, as the page names them.
SEND_ON_LABELS = (("beacon", "Beacon"), ("status", "Status"), ("ask", "Ask around"), ("local_info", "Local info"))


def _names(ids: Any, specs: list[RadioSpec]) -> str:
    """Return the log names of the radios with these ids, in radio order, or "none"."""
    wanted = set(ids)
    return ", ".join(log_name(spec, specs) for spec in specs if spec.id in wanted) or "none"


def _send_on(f: Facts, c: Config) -> list[tuple[str, str]]:
    """Return one row per sendable thing with the radios it goes out on, as in force now.

    Objects and bulletins come from the running daemon's state; the rest from the settings."""
    specs = list(c.radios)
    rows = [(label, _names(send_on_radios(key, specs), specs)) for key, label in SEND_ON_LABELS]
    mail = email_radio(specs, c.email_choice)
    rows.append(("E-mail", _names(() if mail is None else (mail,), specs)))
    live = (f.live or {}).get("send_on")
    if not isinstance(live, dict):
        return [*rows, ("Objects, bulletins", NO_DAEMON)]
    for kind, label in (("objects", "Object"), ("bulletins", "Bulletin")):
        sets = live.get(kind)
        for name, ids in sets.items() if isinstance(sets, dict) else ():
            stored: list[RadioId] = [id for id in ids if isinstance(id, int)] if isinstance(ids, list) else []
            rows.append((f"{label} {name}", _names(in_force_set(stored, specs), specs)))
    return rows


def _state_rows(tnc: dict[str, Any]) -> list[tuple[str, str]]:
    """Return a radio's state, its current problem, and its latest error if any."""
    rows = [("State", str(tnc.get("state", "?"))), ("Problem", str(tnc.get("problem") or "none"))]
    if tnc.get("last_error"):
        rows.append(("Latest error", f"{tnc['last_error']} (the latest one, not necessarily a problem now)"))
    return rows


def _live_radio(f: Facts, spec: RadioSpec) -> dict[str, Any] | None:
    """Return the running daemon's entry for the radio from state.json, or None."""
    for entry in (f.live or {}).get("radios") or []:
        if isinstance(entry, dict) and entry.get("id") == spec.id:
            return entry
    return None


def _radio(f: Facts, spec: RadioSpec) -> list[tuple[str, str]]:
    """Return the rows for one radio: type, on or off, how it is reached, and its state if on."""
    entry = _live_radio(f, spec)
    found = (entry or {}).get("tnc")
    tnc: dict[str, Any] = found if isinstance(found, dict) else {}
    now = {"Port": tnc.get("path"), "Speed": f"{tnc['baud']} baud" if tnc.get("baud") else None}
    rows = [
        ("Type", spec.type),
        ("On", "yes" if spec.enabled else "no"),
        *((label, now.get(label) or words) for label, words in reached(spec)),
    ]
    if not spec.enabled:
        return rows
    if entry is None:
        return [
            *rows,
            (
                "State",
                NO_DAEMON
                if f.live is None
                else "not known: the daemon did not run this radio when the bundle was made",
            ),
        ]
    rows += _state_rows(tnc)
    cards = entry.get("sound_cards") or []
    modem = tnc.get("modem")
    rows += _cards(cards, str(modem.get("sound_card") or "") if isinstance(modem, dict) else "")
    if is_mercury(spec) and not cards:
        rows.append(("Sound cards listed", "none"))
    if isinstance(mercury := entry.get("mercury"), dict):
        rows += _mercury(mercury)
    return rows


def _card_words(card: dict[str, Any], chosen: str) -> str:
    ways = " and ".join(w for w, on in (("records", card.get("records")), ("plays", card.get("plays"))) if on)
    marks = ", the system default" if card.get("default") else ""
    marks += ", the chosen one" if chosen and card.get("id") == chosen else ""
    return f"{card.get('name')!r}: {ways or 'neither'}{marks}; {card.get('id')}"


def _cards(cards: list[dict[str, Any]], chosen: str) -> list[tuple[str, str]]:
    """Return the chosen card and the default first, then the others; over MAX_CARDS the others are
    folded by the device name before " (", with their count (state.json has them all)."""
    first = [c for c in cards if (chosen and c.get("id") == chosen) or c.get("default")]
    others = [c for c in cards if c not in first]
    rows = [("Sound card listed", _card_words(c, chosen)) for c in first]
    if len(cards) <= MAX_CARDS:
        return rows + [("Sound card listed", _card_words(c, chosen)) for c in others]
    folded: dict[str, list[dict[str, Any]]] = {}
    for card in others:
        folded.setdefault(str(card.get("name")).split(" (")[0], []).append(card)
    for name, alike in folded.items():
        if len(alike) == 1:
            rows.append(("Sound card listed", _card_words(alike[0], chosen)))
        else:
            rows.append(("Sound cards listed", f"{name!r}: {len(alike)} of its combinations (state.json lists them)"))
    return rows


def _mercury(m: dict[str, Any]) -> list[tuple[str, str]]:
    """Return what tells a Mercury that hears nothing: frames, stalls, restarts and its devices."""
    snr = m.get("snr")
    rows = [
        ("Frames heard", f"{m.get('frames_in', 0)}, the last {m.get('last_frame') or 'never'}"),
        ("Last SNR", "none yet" if snr is None else f"{snr} dB"),
        ("Hears nothing", f"{m.get('capture_stalls', 0)} times, the last {m.get('last_stall_at') or 'never'}"),
        (
            "Restarted for it",
            f"{m.get('restarts_for_stalls', 0)} times, the last {m.get('last_restart_at') or 'never'}",
        ),
    ]
    return rows + [("Mercury said", str(line)) for line in m.get("device_lines") or []]


def _layers(f: Facts) -> list[tuple[str, str]]:
    rows = []
    for layer in (f.live or {}).get("layers") or []:
        if not isinstance(layer, dict):
            continue
        text = str(layer.get("source"))
        if layer.get("state"):
            text += f", {layer['state']} since {layer.get('since') or 'the start'}"
            text += f", last data {layer.get('heard_at') or 'never'}"
        rows.append((str(layer.get("layer")).capitalize(), text))
    return rows


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
    return f"schema version {db.version}{note}, {megabytes(db.size)}" + (
        f", log file {megabytes(db.wal_size)}" if db.wal_size else ""
    )


def _checks(doctor_text: str) -> list[tuple[str, str]]:
    """Return the doctor's failing checks and its verdict."""
    lines = [line for line in doctor_text.splitlines() if line.strip()]
    rows = [(line[:5].strip(), line[6:]) for line in lines if line.startswith(("FAIL", "warn"))]
    return [
        *rows[:MAX_CHECKS],
        *([("", f"... and {len(rows) - MAX_CHECKS} more")] if len(rows) > MAX_CHECKS else []),
        ("Result", lines[-1] if lines else ""),
    ]


def sections(f: Facts) -> list[Section]:
    install = f.install.kind + (" (a service starts it)" if f.install.service else "")
    local = _local_time(f.made_at)
    what: list[tuple[str, str]] = [
        (
            "NeoAPRS",
            f"{f.version}, installed as {install}" + (f" ({f.install.appimage})" if f.install.appimage else ""),
        ),
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
        out.append(
            (
                "Station",
                [
                    ("Call", c.station_call or "(none set: nothing is transmitted)"),
                    ("Position", _position(c)),
                    ("Beacon", _beacon(f, c)),
                ],
            )
        )
        if f.radios_problem:
            out.append(("Radios", [("Could not be read", f"{f.radios_problem} (settings.json says it too)")]))
        else:
            out += [(f"Radio {spec.id}: {log_name(spec, c.radios)}", _radio(f, spec)) for spec in c.live_radios]
        if not c.live_radios and not f.radios_problem:
            out.append(("Radios", [("Radios", "none")]))
        elif not f.radios_problem:
            out.append(("Send on", _send_on(f, c)))
        out.append(("GPS", _gps(f, c)))
        if layers := _layers(f):
            out.append(("Map layers", layers))
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
    lines.append(
        "The warnings and errors of the log, each message once (COUNT× LAST-TIME LEVEL MESSAGE; errors first, then the newest; logs/neoaprs.log has every line):"
    )
    lines.extend(f"  {line}" for line in f.problems.lines or ["none"])
    if f.problems.more:
        lines.append(f"  ... and {f.problems.more} more messages, older ones")
    lines.append(
        f"Left out of this list: {f.problems.left_out} web server request lines for optional files that are not there (the base map, favicon.ico, the map fonts)."
    )
    return "\n".join(lines) + "\n"


def message_key(level: str, message: str) -> str:
    """Return the grouping key: the level and the message with addresses and numbers masked."""
    return f"{level} {NUMBER.sub('#', ADDRESS.sub('<address>', message))}"


def problem_groups(log_lines: list[str]) -> Problems:
    """Group WARNING, ERROR and CRITICAL records by `message_key`, one line each.

    ERROR and CRITICAL come first, then WARNING, newest first, at most MAX_GROUPS."""
    # key -> [count, order of the last, time, level, message, exception line]
    groups: dict[str, list[Any]] = {}
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
            last[:] = [
                last[0] + 1,
                order,
                when,
                level,
                message if len(message) <= MAX_MESSAGE else message[: MAX_MESSAGE - 1] + "…",
                "",
            ]
        elif last is not None and line.strip():
            last[5] = f"    {line.strip()}"  # keeps only the last following line
    ranked = sorted(groups.values(), key=lambda g: (g[3] == "WARNING", -g[1]))
    lines: list[str] = []
    for count, _, when, level, message, exception in ranked[:MAX_GROUPS]:
        lines.append(f"{count}× {when} {level:<8} {message}")
        if exception:
            lines.append(exception)
    return Problems(lines, left_out, max(0, len(ranked) - MAX_GROUPS))
