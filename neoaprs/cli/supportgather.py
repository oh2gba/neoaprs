"""The parts of the support bundle: functions that each read something and return its text.

supportmake.py runs them and turns a failure of one into a file that says so. They change
nothing: the database is opened read-only, and the commands that are run only report."""
import contextlib
import json
import logging
import platform
import shutil
import subprocess
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neoaprs import ax25
from neoaprs.clock import iso
from neoaprs.config import Config
from neoaprs.configradios import radios_from_rows
from neoaprs.dberror import Row, SqlError
from neoaprs.migrations import MIGRATIONS, SCHEMA_VERSION, history, schema_version, source_hash
from neoaprs.packetcodec import PacketRow
from neoaprs.pairsetting import PairSpec, call_of, may_pair
from neoaprs.radiospec import RadioSpec, log_name
from neoaprs.radiosql import radio_rows, radio_settings
from neoaprs.store import DB_NAME
from neoaprs.storesql import read_settings
from neoaprs.supportsql import file_facts, latest_packets, latest_undecoded, open_readonly, quick_check, table_counts

from . import doctor
from .logfile import APP_LOG_NAME, LOG_NAME, START_LINE
from .radiosettings import RADIO_ROWS_FROM, SHOWN_KEYS, in_force, own_fields, shown_settings, stored_own, stored_text_of, value_text
from .redaction import hides, shown_value
from .supportbundle import rotated_logs, tail_text
from .supportsummary import DbFacts, megabytes, stamp

PACKETS_SHOWN = 1000
UNDECODED_SHOWN = 200
QUICK_CHECK_MAX_BYTES = 500 * 1024 * 1024
PROBLEM_SCAN_BYTES = 8 * 1024 * 1024
JOURNAL_LINES = 3000
JOURNAL_WAIT_SEC = 5.0


@contextlib.contextmanager
def quiet(name: str = "neoaprs.config") -> Iterator[None]:
    """Silence a logger so reading settings for a bundle does not log invalid values again."""
    logger = logging.getLogger(name)
    was, logger.disabled = logger.disabled, True
    try:
        yield
    finally:
        logger.disabled = was


@dataclass(frozen=True)
class StoredRadios:
    """The radios as stored: rows of `radio` and `radio_setting`, invalid values included.

    `problem` is set when the tables exist but could not be read."""
    rows: list[Row] = field(default_factory=list)
    settings: list[Row] = field(default_factory=list)
    problem: str = ""

    @property
    def specs(self) -> tuple[RadioSpec, ...]:
        with quiet():
            return radios_from_rows(self.rows, self.settings)

    def own_rows(self) -> dict[tuple[int, str], str]:
        """Return the radios' own settings as stored, by radio and key."""
        return stored_own(self.settings)


@dataclass(frozen=True)
class Stored:
    """The settings table rows, and the radios if they are in their own tables (else None)."""
    rows: dict[str, str]
    radios: StoredRadios | None = None


def config_of(rows: dict[str, str], radios: StoredRadios | None = None) -> Config:
    """Return the settings in force, as the daemon reads them, with the stored radios."""
    with quiet():
        return in_force(rows, radios.specs if radios is not None else ())


# ---- the settings

def settings_json(rows: dict[str, str], radios: StoredRadios | None = None) -> str:
    """Return settings.json: the settings in force, which are stored, the radios and pairs.

    A secret appears only as `(set, N characters)`."""
    specs = radios.specs if radios is not None else ()
    own = radios.own_rows() if radios is not None else {}
    with quiet():
        config = in_force(rows, specs)
        effective = shown_settings(config)
    stored = {key: text for key in effective if (text := stored_text_of(key, rows)) is not None}
    out: dict[str, Any] = {
        "values": {key: shown_value(key, value) for key, value in effective.items()},
        "defaults_are_used_for": [key for key in SHOWN_KEYS if key not in stored],
        "stored_text_differs": {key: shown_value(key, text) for key, text in stored.items() if text != effective[key]},
        "other_rows": {key: shown_value(key, value) for key, value in rows.items() if key not in effective},
    }
    if radios is not None:
        out["radios"] = [radio_json(spec, specs, own) for spec in specs]
        out["pairs"] = [pair_json(pair, specs, config.station_call) for pair in config.pairs]
        if radios.problem:
            out["radios_problem"] = radios.problem
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def radio_json(spec: RadioSpec, specs: Sequence[RadioSpec], own: dict[tuple[int, str], str]) -> dict[str, Any]:
    """Return one radio for settings.json: its row, log name, settings in force and as stored."""
    def shown(key: str, text: str) -> str:
        return shown_value(f"radio/{spec.id}/{key}", text)
    return {"id": spec.id, "kind": spec.kind, "type": spec.type, "name": spec.name, "log_name": log_name(spec, specs), "enabled": spec.enabled, "position": spec.position,
            "removed_at": None if spec.removed_at is None else iso(spec.removed_at), "values": {key: shown(key, value_text(spec, key)) for key in own_fields(spec)},
            "stored": {key: shown(key, text) for (radio, key), text in sorted(own.items()) if radio == spec.id}}


def pair_json(pair: PairSpec, specs: Sequence[RadioSpec], station_call: str) -> dict[str, Any]:
    """Return one pair for settings.json: its radios, SSID, call, and whether they may pair now."""
    low, high = (next((spec for spec in specs if spec.id == id), None) for id in (pair.low, pair.high))
    return {"low": pair.low, "high": pair.high, "enabled": pair.enabled, "ssid": pair.ssid, "call": call_of(station_call, pair.ssid),
            "may_pair_now": low is not None and high is not None and may_pair(low, high)}


def secrets_of(rows: dict[str, str]) -> list[str]:
    """Return the secret setting values, so the zip can be checked for them."""
    return [value for key, value in rows.items() if value and hides(key, value)]


# ---- the logs

def log_files(data: Path) -> tuple[list[Path], list[Path]]:
    """Return (the daemon's log files, the desktop app's log files), each newest first."""
    return rotated_logs(data, LOG_NAME), rotated_logs(data, APP_LOG_NAME)


def log_lines(files: list[Path]) -> list[str]:
    """Return the tail (PROBLEM_SCAN_BYTES) of each log file as lines, oldest first."""
    lines: list[str] = []
    for path in files:
        try:
            text, _ = tail_text(path, PROBLEM_SCAN_BYTES)
        except OSError:
            continue
        lines = text.splitlines() + lines
    return lines


def started_at(lines: list[str]) -> datetime | None:
    """Return the time of the latest start line, e.g. `2026-10-26 08:00:00Z  INFO  NeoAPRS ...`."""
    for line in reversed(lines):
        if START_LINE in line:
            try:
                return datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            except ValueError:
                return None
    return None


def journal_text(run: Callable[..., Any] = subprocess.run, which: Callable[[str], str | None] = shutil.which) -> str | None:
    """Return the last journal lines of the NeoAPRS service (Linux, systemd), else None.

    A failing command is reported in the text, never raised, so it cannot fail the bundle."""
    if platform.system() != "Linux" or which("journalctl") is None or which("systemctl") is None:
        return None
    command = ["journalctl", "--user", "-u", "neoaprs", "-n", str(JOURNAL_LINES), "--no-pager", "-o", "short-iso"]
    try:
        done = run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=JOURNAL_WAIT_SEC)
    except (OSError, subprocess.SubprocessError) as e:
        return f"[{' '.join(command)} could not be run: {type(e).__name__}: {e}]\n"
    note = f"[{' '.join(command)} ended with {done.returncode}: {done.stderr.strip()[:300]}]\n" if done.returncode else ""
    return f"[{' '.join(command)}: the NeoAPRS service of this user, which is not necessarily the one of this data folder]\n" + note + str(done.stdout)


# ---- the doctor

def doctor_text(data: Path) -> str:
    """Return what `neoaprs doctor` prints for this data folder."""
    findings = doctor.diagnose(data)
    failed = sum(f.status == "fail" for f in findings)
    warned = sum(f.status == "warn" for f in findings)
    tail = f"{failed} to fix, {warned} to look at" if failed or warned else "all is well"
    return "\n".join([*doctor.format_findings(findings), tail]) + "\n"


# ---- the database

def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def migration_lines(rows: list[tuple[int, str, str, datetime, str]]) -> list[str]:
    """Return one line per applied migration: when, and whether its source matches this build's.

    A differing source means another build migrated the file."""
    lines = []
    for version, name, digest, applied, note in rows:
        if not 1 <= version <= len(MIGRATIONS):
            verdict = "this NeoAPRS does not know this step"
        elif digest == "unknown" or source_hash(MIGRATIONS[version - 1]) == "unknown":
            verdict = "source hash not comparable (no source in this build)"
        else:
            verdict = "source hash matches" if source_hash(MIGRATIONS[version - 1]) == digest else "SOURCE HASH DIFFERS from this NeoAPRS's"
        lines.append(f"  {version:>3}  {name:<6} applied {stamp(applied)}  {verdict}" + (f"  ({note})" if note else ""))
    return lines


def journal_mode(path: Path) -> str:
    """Return `wal` or `rollback journal`, from the version bytes of the file header."""
    with path.open("rb") as f:
        header = f.read(20)
    return "wal" if len(header) == 20 and header[18] == 2 and header[19] == 2 else "rollback journal"


def database_report(data: Path) -> tuple[str, DbFacts]:
    """Return the text of database.txt and the facts for the summary.

    Raise if the file cannot be opened or read; the bundle then has database.txt.error.txt."""
    path = data / DB_NAME
    if not path.is_file():
        text = f"There is no database file at {path} (the daemon makes it when it first starts).\n"
        return text, DbFacts(None, SCHEMA_VERSION, 0, 0, "there is no database file yet")
    size, wal = _size(path), _size(path.with_name(path.name + "-wal"))
    lines = [f"File:     {path}", f"Size:     {megabytes(size)} ({size:,} bytes); write-ahead log {megabytes(wal)}, shared memory file {megabytes(_size(path.with_name(path.name + '-shm')))}", ""]
    conn = open_readonly(path)
    try:
        facts = file_facts(conn)
        version = int(facts["user_version"])
        lines.append(f"Schema version: {version} (this NeoAPRS expects {SCHEMA_VERSION}){'' if version == SCHEMA_VERSION else '  <-- DIFFERENT'}")
        lines += [f"SQLite file:    {facts['page_count']} pages of {facts['page_size']} bytes, {facts['freelist_count']} free, journal mode {journal_mode(path)}", "", "Migrations applied:"]
        lines += migration_lines(history(conn)) or ["  (none recorded)"]
        lines += ["", "Rows:"] + [f"  {name:<18} {count:>10,}" for name, count in table_counts(conn)]
        lines += ["", "Integrity (PRAGMA quick_check):"]
        if size > QUICK_CHECK_MAX_BYTES:
            lines.append(f"  skipped: the file is {megabytes(size)}, over the {megabytes(QUICK_CHECK_MAX_BYTES)} that it is checked up to")
        else:
            lines += [f"  {line}" for line in quick_check(conn)[:20]]
    finally:
        conn.close()
    return "\n".join(lines) + "\n", DbFacts(version, SCHEMA_VERSION, size, wal)


def read_stored(data: Path) -> Stored:
    """Return the settings rows and the radios. Raise if the file cannot be read.

    Unreadable radios are reported in `problem`, so the settings are still returned."""
    conn = open_readonly(data / DB_NAME)
    try:
        rows = read_settings(conn)
        if not RADIO_ROWS_FROM <= schema_version(conn) <= SCHEMA_VERSION:
            return Stored(rows)
        try:
            return Stored(rows, StoredRadios(radio_rows(conn), radio_settings(conn)))
        except SqlError as e:
            return Stored(rows, StoredRadios(problem=f"the radios could not be read: {e}"))
    finally:
        conn.close()


# ---- the packets

def packet_text(row: tuple[Any, ...]) -> str:
    """Return a packet row as a TNC2 line, from the frame or else from the columns."""
    raw = PacketRow(*row)
    try:
        line = ax25.decode(bytes(raw.raw)).tnc2()
    except ax25.Ax25Error:
        path = "".join("," + p for p in raw.path.split(",") if p)
        line = f"{raw.source}>{raw.destination}{path}: (not an AX.25 frame) {bytes(raw.raw)[:80]!r}"
    return "".join(c if c.isprintable() else "?" for c in line)


def packet_line(row: tuple[Any, ...]) -> str:
    packet = PacketRow(*row)
    outcome = f"NOT DECODED: {packet.error}" if packet.kind == "undecoded" else f"{packet.kind}: {packet.summary}"
    return f"{packet.heard_at[:23].replace('T', ' ')}Z  {'out' if packet.direction == 'out' else 'in ':<3}  {packet_text(row)}\n{'':>29}-> {outcome}"


def packets_text(data: Path) -> str:
    """Return the latest packets, then the latest undecoded ones, each oldest first."""
    conn = open_readonly(data / DB_NAME)
    try:
        latest, bad = latest_packets(conn, PACKETS_SHOWN), latest_undecoded(conn, UNDECODED_SHOWN)
    finally:
        conn.close()
    out = [f"The last {PACKETS_SHOWN} packets heard (in) and sent (out), the newest last; {len(latest)} here.", "These went over the air, where they are public.", ""]
    out += [packet_line(row) for row in reversed(latest)] or ["(none)"]
    out += ["", f"The last {UNDECODED_SHOWN} packets that could not be decoded, the newest last; {len(bad)} here.", ""]
    out += [packet_line(row) for row in reversed(bad)] or ["(none)"]
    return "\n".join(out) + "\n"
