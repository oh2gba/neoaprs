"""`neoaprs service install|remove|status|logs [--data DIR]`: NeoAPRS as a service of the user, started at login or at boot, by the way each system has: a systemd user unit on Linux
(servicesystemd.py), the Run key of the user's registry on Windows (servicewindows.py, no Windows service: a service has no desktop and no profile of the user) and a launchd agent on macOS
(servicelaunchd.py). This module reads the command line, works out what is to be run (`Plan`) and hands it to the system's own module; `logs` is the same everywhere."""
import argparse
import importlib
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from neoaprs.paths import default_data_dir

from .daemonstate import LOG_NAME, tail

PACKAGE_DIR = Path(__file__).resolve().parent.parent
REPO = "https://github.com/oh2gba/neoaprs"


@dataclass(frozen=True)
class Plan:
    """What the service is to run: this interpreter, on this data folder. `clone` is the folder of a git clone that the program runs from (the unit then runs in it); `gui_exe` and `pythonw` are
    the two ways Windows has to run it without a console window (the script `neoaprsw.exe` an install makes, else `pythonw.exe` of the same Python)."""
    python: str
    data: Path
    clone: Path | None = None
    linger: bool = False
    gui_exe: str | None = None
    pythonw: str | None = None


def source_tree() -> Path | None:
    """The folder of the clone this package is imported from (an editable install, `python -m neoaprs` in a clone), or None for a wheel in site-packages."""
    parent = PACKAGE_DIR.parent
    return parent if (parent / "pyproject.toml").is_file() and (parent / "neoaprs" / "__init__.py").is_file() else None


def windowless_programs() -> tuple[str | None, str | None]:
    """(the `neoaprsw` script next to this Python or on the PATH, `pythonw` next to this Python), each None when there is not one."""
    here = Path(sys.executable).parent
    gui = next((str(p) for p in (here / "neoaprsw.exe", here / "neoaprsw") if p.is_file()), None) or shutil.which("neoaprsw")
    pythonw = here / "pythonw.exe"
    return gui, str(pythonw) if pythonw.is_file() else None


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neoaprs service", description="Run NeoAPRS as a service of your user: it starts at login (at boot too on Linux with --linger) and is kept running.")
    p.add_argument("action", choices=["install", "remove", "status", "logs"], help="install: set it up and start it; remove: take it away (the data stays); status: is it set up, and does the daemon answer; logs: the end of the daemon's log")
    p.add_argument("--data", default=str(default_data_dir()), help="the data folder the service runs on; default %(default)s")
    p.add_argument("--linger", action="store_true", help="install, Linux: also run `loginctl enable-linger`, so that it starts at boot and survives a logout, not only while you are logged in")
    p.add_argument("--clone", metavar="DIR", help="install, Linux: the folder of the git clone this runs from (the unit then runs in it); found by itself when the package is imported from a clone")
    p.add_argument("-n", "--lines", type=int, default=50, help="logs: how many lines (default 50)")
    return p


def make_plan(args: argparse.Namespace) -> Plan:
    gui, pythonw = windowless_programs()
    clone = Path(args.clone).expanduser().resolve() if args.clone else source_tree()
    return Plan(os.path.abspath(sys.executable), Path(args.data).expanduser().resolve(), clone, args.linger, gui, pythonw)


def logs(plan: Plan, lines: int, hint: str) -> int:
    path = plan.data / LOG_NAME
    found = tail(path, lines)
    if not found:
        print(f"{path}: no log yet (the daemon writes it when it starts)")
    for line in found:
        print(line)
    if hint:
        print(hint)
    return 0


def backend_for(system: str) -> ModuleType:
    """The module that knows the service manager of `system` (sys.platform): install(plan), remove(plan), status(plan), installed(plan) and LOG_HINT."""
    name = {"win32": "servicewindows", "darwin": "servicelaunchd"}.get(system, "servicesystemd")
    return importlib.import_module(f"{__package__}.{name}")


def main(argv: list[str], platform: str | None = None) -> int:
    args = parser().parse_args(argv)
    plan = make_plan(args)
    backend = backend_for(platform or sys.platform)
    if args.action == "logs":
        return logs(plan, args.lines, str(backend.LOG_HINT))
    return int({"install": backend.install, "remove": backend.remove, "status": backend.status}[args.action](plan))
