"""Makes a support bundle: runs the gatherers of neoaprs/cli/supportgather.py, writes what they found with neoaprs/cli/supportbundle.py, and finds where the file goes and how it is shown. The daemon (the page's button),
the command `neoaprs support` and the app's tray item all come here; they differ in what they know (only the daemon has `live`, the state of the running parts) and in who is told.

A gatherer that fails does not fail the bundle: its file is replaced by `<file>.error.txt` with the traceback, and the summary says what it could not read."""
import json
import logging
import os
import platform
import subprocess
import sys
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from neoaprs import VERSION
from neoaprs.clock import Clock, utcnow
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.store import DB_NAME
from neoaprs.versions import InstallInfo

from . import supportgather as gather
from .daemonstate import LOG_NAME, is_running, page_url, tail
from .installkind import detect_here
from .supportbundle import Member, bundle_name, log_members, write_zip
from .supportreadme import readme_text
from .supportsummary import DbFacts, Facts, problem_groups, summary_text

ORDER = ("README.txt", "summary.txt", "settings.json", "state.json", "doctor.txt", "database.txt", "packets.txt", "page.json", "page-errors.json")
log = logging.getLogger("neoaprs.support")


@dataclass(frozen=True)
class Made:
    path: Path
    size: int


@dataclass
class Collector:
    """The members of a bundle as they are made: a step that raises is a member `<name>.error.txt` and a note for the summary."""
    members: dict[str, Member] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)

    def add(self, name: str, text: str) -> None:
        self.members[name] = Member(name, text)

    def step(self, name: str, fn: Callable[[], str | None]) -> bool:
        """Runs a gatherer; its text becomes the member `name` (nothing when it says None), and a failure the member `name.error.txt`."""
        try:
            text = fn()
        except Exception as e:
            self.failed[name] = f"{type(e).__name__}: {e}"
            self.add(name + ".error.txt", f"{name} could not be made.\n\n{traceback.format_exc()}")
            return False
        if text is not None:
            self.add(name, text)
        return True

    def ordered(self) -> list[Member]:
        """README.txt and summary.txt first, then the files in the order of ORDER, the files that say a part failed, the logs (the daemon's first), and what is left."""
        def place(member: Member) -> tuple[int, str]:
            name = member.name
            if name in ORDER:
                return ORDER.index(name), name
            if name.endswith(".error.txt"):
                return len(ORDER), name
            if name.startswith("logs/"):
                return len(ORDER) + 1, ("0" if name.startswith("logs/neoaprs.log") else "1") + name
            return len(ORDER) + 2, name
        return sorted(self.members.values(), key=place)


def dumped(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n"


def collect(data: Path, now: datetime, live: dict[str, Any] | None, page: dict[str, Any] | None, page_errors: list[dict[str, Any]] | None,
            install: InstallInfo | None, running: bool | None, by: str, journal: Callable[[], str | None], call: str) -> tuple[list[Member], list[str], str]:
    """(the members, the values that must not be in the file, the call) of a bundle for the data folder; `call` is the one the caller knows, for the name of the file when the settings cannot be read."""
    col = Collector()
    rows: dict[str, str] | None = None

    def settings() -> str:
        nonlocal rows
        rows = gather.read_rows(data) if (data / DB_NAME).is_file() else {}
        return gather.settings_json(rows)

    col.step("settings.json", settings)
    daemon_logs, app_logs = gather.log_files(data)
    col.step("logs", lambda: _logs(col, [*app_logs, *daemon_logs]))
    col.step("doctor.txt", lambda: gather.doctor_text(data))
    facts: list[DbFacts] = []
    col.step("database.txt", lambda: _database(data, facts))
    col.step("packets.txt", lambda: gather.packets_text(data) if (data / DB_NAME).is_file() else "There is no database file yet, so there are no packets.\n")
    col.step("logs/journal.txt", journal)
    if live is not None:
        col.add("state.json", dumped(live))
    if page is not None:
        col.add("page.json", dumped(page))
    if page_errors is not None:
        col.add("page-errors.json", dumped(page_errors))
    config = gather.config_of(rows) if rows is not None else None

    def summary() -> str:
        db = facts[0] if facts else DbFacts(None, SCHEMA_VERSION, 0, 0, col.failed.get("database.txt", "not read"))
        known = Facts(VERSION, install or detect_here(data), bool(getattr(sys, "frozen", False)), gather.system_description(), platform.machine(), platform.python_version(), data, now, by,
                      is_running(data) if running is None else running, gather.started_at(tail(data / LOG_NAME, 100_000)), config, col.failed.get("settings.json", ""), live, page_url(data) or "", db,
                      problem_groups(gather.log_lines(daemon_logs)), col.members["doctor.txt"].text if "doctor.txt" in col.members else "")
        return summary_text(known)

    col.step("summary.txt", summary)
    col.step("README.txt", lambda: readme_text(col.ordered(), now, VERSION, by))
    return col.ordered(), gather.secrets_of(rows or {}), config.station_call if config else call


def _logs(col: Collector, files: list[Path]) -> None:
    for member in log_members(files):
        col.members[member.name] = member


def _database(data: Path, facts: list[DbFacts]) -> str:
    text, db = gather.database_report(data)
    facts.append(db)
    return text


def make_bundle(data: Path, out_dir: Path, *, live: dict[str, Any] | None = None, page: dict[str, Any] | None = None, page_errors: list[dict[str, Any]] | None = None,
                install: InstallInfo | None = None, running: bool | None = None, by: str = "neoaprs support, without the daemon", now: Clock = utcnow,
                journal: Callable[[], str | None] = gather.journal_text, call: str = "") -> Made:
    """Writes the bundle of the data folder into `out_dir` (made if it is not there) and says where. Nothing in the data folder is changed. Blocking: the daemon runs it in a thread."""
    made_at = now()
    members, secrets, call = collect(data, made_at, live, page, page_errors, install, running, by, journal, call)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / bundle_name(call, made_at)
    return Made(path, write_zip(path, members, made_at, secrets))


# ---- where the file goes, and showing it

def desktop_dir(home: Path | None = None, environ: Mapping[str, str] | None = None) -> Path:
    """The user's Desktop folder when there is one (the name the system gave it: Linux's `user-dirs.dirs` knows it as Työpöytä in Finnish, a OneDrive on Windows has it inside), else the home folder."""
    home = Path.home() if home is None else home
    env = os.environ if environ is None else environ
    candidates: list[Path] = []
    try:
        for line in (home / ".config" / "user-dirs.dirs").read_text(encoding="utf-8").splitlines():
            if line.startswith("XDG_DESKTOP_DIR="):
                candidates.append(Path(line.split("=", 1)[1].strip().strip('"').replace("$HOME", str(home))))
    except OSError:
        pass
    candidates.append(home / "Desktop")
    for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if env.get(name):
            candidates.append(Path(env[name]) / "Desktop")
    return next((c for c in candidates if c.is_dir()), home)


def show_command(path: Path, system: str) -> list[str] | str:
    """The command that shows the file in the system's file manager: Explorer with the file selected, Finder revealing it, or on Linux the folder (the file managers there do not agree on selecting a file). Explorer's is
    a command line and not a list: it wants the quotes round the path itself, after the comma, which a list would put round the whole argument."""
    if system == "win32":
        return f'explorer /select,"{path}"'
    if system == "darwin":
        return ["open", "-R", str(path)]
    return ["xdg-open", str(path.parent)]


def show_file(path: Path, system: str | None = None, start: Callable[..., object] = subprocess.Popen) -> bool:
    """Opens the file manager at the file; best effort, False when it could not be started."""
    try:
        start(show_command(path, sys.platform if system is None else system), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True


def made_text(made: Made) -> str:
    return f"{made.size / 1e6:.1f} MB" if made.size >= 100_000 else f"{max(1, made.size // 1024)} KB"


def make_for_the_user(data: Path, show: bool = True) -> Made:
    """The bundle of the data folder on the Desktop (the home folder when there is none), shown in the file manager: what the tray item and the Start menu entry do. Logged."""
    made = make_bundle(data, desktop_dir())
    log.info("support bundle made: %s, %s", made.path, made_text(made))
    if show and not show_file(made.path):
        log.warning("the file manager could not be started to show %s", made.path)
    return made
