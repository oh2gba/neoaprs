"""`neoaprs service install|remove|status|logs [--data DIR]`: run NeoAPRS as a service of the user.

A systemd user unit on Linux, the Run key on Windows (a Windows service has no desktop) and a
launchd agent on macOS. This module builds the `Plan` and hands it to the system's module."""

import argparse
import importlib
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from neoaprs.paths import default_data_dir

from .daemonstate import tail
from .logfile import LOG_NAME

PACKAGE_DIR = Path(__file__).resolve().parent.parent
REPO = "https://github.com/oh2gba/neoaprs"


@dataclass(frozen=True)
class Plan:
    """What the service is to run: this interpreter, on this data folder.

    `gui_exe` and `pythonw` run it on Windows without a console; `appimage` replaces `python`."""

    python: str
    data: Path
    clone: Path | None = None
    linger: bool = False
    gui_exe: str | None = None
    pythonw: str | None = None
    appimage: str | None = None


def source_tree() -> Path | None:
    """Return the git clone the package is imported from, or None for an installed wheel."""
    parent = PACKAGE_DIR.parent
    return parent if (parent / "pyproject.toml").is_file() and (parent / "neoaprs" / "__init__.py").is_file() else None


def appimage_file() -> str | None:
    """Return the AppImage file this program runs from, or None outside one.

    A stale `$APPIMAGE` inherited from a parent does not count: Python must be in `$APPDIR`."""
    file, mount = os.environ.get("APPIMAGE"), os.environ.get("APPDIR")
    if not file or not mount or not os.path.isfile(file):
        return None
    inside = os.path.realpath(sys.executable).startswith(os.path.realpath(mount) + os.sep)
    return os.path.abspath(file) if inside else None


def windowless_programs() -> tuple[str | None, str | None]:
    """Return the `neoaprsw` script and `pythonw`; None if absent."""
    here = Path(sys.executable).parent
    gui = next((str(p) for p in (here / "neoaprsw.exe", here / "neoaprsw") if p.is_file()), None) or shutil.which(
        "neoaprsw"
    )
    pythonw = here / "pythonw.exe"
    return gui, str(pythonw) if pythonw.is_file() else None


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="neoaprs service",
        description="Run NeoAPRS as a service of your user: it starts at login (at boot too on Linux with --linger) and is kept running.",
    )
    p.add_argument(
        "action",
        choices=["install", "remove", "status", "logs"],
        help="install: set it up and start it; remove: take it away (the data stays); status: is it set up, and does the daemon answer; logs: the end of the daemon's log",
    )
    p.add_argument(
        "--data", default=str(default_data_dir()), help="the data folder the service runs on; default %(default)s"
    )
    p.add_argument(
        "--linger",
        action="store_true",
        help="install, Linux: also run `loginctl enable-linger`, so that it starts at boot and survives a logout, not only while you are logged in",
    )
    p.add_argument(
        "--clone",
        metavar="DIR",
        help="install, Linux: the folder of the git clone this runs from (the unit then runs in it); found by itself when the package is imported from a clone",
    )
    p.add_argument("-n", "--lines", type=int, default=50, help="logs: how many lines (default 50)")
    return p


def make_plan(args: argparse.Namespace) -> Plan:
    gui, pythonw = windowless_programs()
    clone = Path(args.clone).expanduser().resolve() if args.clone else source_tree()
    return Plan(
        os.path.abspath(sys.executable),
        Path(args.data).expanduser().resolve(),
        clone,
        args.linger,
        gui,
        pythonw,
        appimage_file(),
    )


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
    """Return the module for the service manager of `system` (a sys.platform value).

    It provides install, remove, status and installed (each taking a Plan) and LOG_HINT."""
    name = {"win32": "servicewindows", "darwin": "servicelaunchd"}.get(system, "servicesystemd")
    return importlib.import_module(f"{__package__}.{name}")


def main(argv: list[str], platform: str | None = None) -> int:
    args = parser().parse_args(argv)
    plan = make_plan(args)
    backend = backend_for(platform or sys.platform)
    if args.action == "logs":
        return logs(plan, args.lines, str(backend.LOG_HINT))
    return int({"install": backend.install, "remove": backend.remove, "status": backend.status}[args.action](plan))
