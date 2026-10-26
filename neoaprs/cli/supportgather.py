"""The parts of the support bundle, each a function that reads something of the computer and returns its text (neoaprs/cli/supportmake.py runs them, and turns a failure of one into a file that says so). They read and do
not change anything: the database is opened read-only, the logs are read, the commands that are run only report."""
import contextlib
import json
import logging
import platform
import shutil
import subprocess
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neoaprs import ax25
from neoaprs.config import DEFAULTS, Config
from neoaprs.configtypes import is_secret, redacted
from neoaprs.migrations import MIGRATIONS, SCHEMA_VERSION, history, source_hash
from neoaprs.packetcodec import PacketRow
from neoaprs.store import DB_NAME
from neoaprs.storesql import read_settings
from neoaprs.supportsql import file_facts, latest_packets, latest_undecoded, open_readonly, quick_check, table_counts

from . import doctor
from .supportbundle import rotated_logs, tail_text
from .supportsummary import DbFacts, megabytes, stamp

PACKETS_SHOWN = 1000
UNDECODED_SHOWN = 200
QUICK_CHECK_MAX_BYTES = 500 * 1024 * 1024
PROBLEM_SCAN_BYTES = 8 * 1024 * 1024
JOURNAL_LINES = 3000
JOURNAL_WAIT_SEC = 5.0
LOG_NAME = "neoaprs.log"
APP_LOG_NAME = "neoaprs-app.log"
START_LINE = " starting, data in "


@contextlib.contextmanager
def quiet(name: str = "neoaprs.config") -> Iterator[None]:
    """A value of a setting that is wrong is told in the log when it is read (and falls back to its default); reading the settings for a bundle does not add that line to the log again."""
    logger = logging.getLogger(name)
    was, logger.disabled = logger.disabled, True
    try:
        yield
    finally:
        logger.disabled = was


def config_of(rows: dict[str, str]) -> Config:
    with quiet():
        return Config.from_data(rows)


def system_description() -> str:
    """The operating system and its version, as a person names them."""
    system = platform.system()
    if system == "Linux":
        try:
            name = platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
        except OSError:
            name = "Linux"
        return f"{name}, kernel {platform.release()}"
    if system == "Windows":
        return f"Windows {platform.release()} ({platform.version()})"
    if system == "Darwin":
        return f"macOS {platform.mac_ver()[0] or platform.release()}"
    return platform.platform()


# ---- the settings

def settings_json(rows: dict[str, str]) -> str:
    """Every setting with the value in force and which of them are stored, a secret only as `(set, N characters)`; the stored rows that are no setting of this NeoAPRS apart (the beacon's memory of when it last sent, say)."""
    effective = config_of(rows).to_data()
    out: dict[str, Any] = {
        "values": {key: redacted(key, value) for key, value in effective.items()},
        "defaults_are_used_for": [key for key in DEFAULTS.to_data() if key not in rows],
        "stored_text_differs": {key: redacted(key, rows[key]) for key in effective if key in rows and rows[key] != effective[key]},
        "other_rows": {key: redacted(key, value) for key, value in rows.items() if key not in effective},
    }
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def secrets_of(rows: dict[str, str]) -> list[str]:
    """The values of the secret settings, so that the zip can be held free of them."""
    return [value for key, value in rows.items() if value and is_secret(key)]


# ---- the logs

def log_files(data: Path) -> tuple[list[Path], list[Path]]:
    """(the daemon's log and its rotated files, the desktop app's), each the newest first."""
    return rotated_logs(data, LOG_NAME), rotated_logs(data, APP_LOG_NAME)


def log_lines(files: list[Path]) -> list[str]:
    """The end of the daemon's logs as lines, the oldest first: all the files that are kept (the end of each, within PROBLEM_SCAN_BYTES), for the summary to group the warnings and errors of the whole log."""
    lines: list[str] = []
    for path in files:
        try:
            text, _ = tail_text(path, PROBLEM_SCAN_BYTES)
        except OSError:
            continue
        lines = text.splitlines() + lines
    return lines


def started_at(lines: list[str]) -> datetime | None:
    """When the latest start of the daemon that the log tells was (its first line, `2026-10-26 08:00:00Z  INFO  NeoAPRS 0.9.0 starting, ...`)."""
    for line in reversed(lines):
        if START_LINE in line:
            try:
                return datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            except ValueError:
                return None
    return None


def journal_text(run: Callable[..., Any] = subprocess.run, which: Callable[[str], str | None] = shutil.which) -> str | None:
    """What the user's journal has of the NeoAPRS service, the last lines (Linux with systemd); None where there is no journalctl. A command that fails is told in the text, not raised: it never fails the bundle."""
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
    """What `neoaprs doctor` prints for this data folder, as text."""
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
    """Each migration that was applied, when, and whether the source of it is the one this NeoAPRS has (a changed one means the file was migrated by another build)."""
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
    """`wal` or `rollback journal`, by the version bytes of the file's header (a connection that does not look at the log cannot say)."""
    with path.open("rb") as f:
        header = f.read(20)
    return "wal" if len(header) == 20 and header[18] == 2 and header[19] == 2 else "rollback journal"


def database_report(data: Path) -> tuple[str, DbFacts]:
    """database.txt and what the summary says of the file. A file that cannot be opened or read raises (the bundle then has database.txt.error.txt)."""
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


def read_rows(data: Path) -> dict[str, str]:
    """The rows of the settings table. Raises when the file cannot be read."""
    conn = open_readonly(data / DB_NAME)
    try:
        return read_settings(conn)
    finally:
        conn.close()


# ---- the packets

def packet_text(row: tuple[Any, ...]) -> str:
    """A packet row as a TNC2 line (what ax25 reads of the frame; else what the columns say)."""
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
    """The latest packets heard and sent, then the latest that did not decode, each oldest first."""
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
