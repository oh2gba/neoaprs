"""The `neoaprs` command: `neoaprs [run] [flags]` runs the daemon (the flags of `python -m neoaprs`), and the subcommands are the tools around it: `service` (set it up to start at login), `map` (make the
base map), `db` (look at the database), `replay` (play a capture as a TNC), `gps-replay` (play a drive as a gpsd), `capture` (record the radio), `doctor` (what is wrong with this computer), `open` (the page in the browser, starting the
daemon if needed), `stop` (end the daemon) and `app` (the desktop app: the page in a window and a tray icon; needs the extra `neoaprs[app]`). `neoaprsw` is the daemon without a console
window, which is how Windows starts it; `neoaprs-app` is the desktop app without one. The subcommands are imported when they are used, so that `neoaprs --version` and `neoaprs doctor` do not load the web server."""
import argparse
import os
import sys
from collections.abc import Callable

COMMANDS = {
    "run": "run the daemon (what `neoaprs` does with no command, and `python -m neoaprs`)",
    "service": "set NeoAPRS up to start at login (install, remove, status, logs)",
    "map": "make the base map of your area (what the page's Download button does)",
    "db": "look at and change the database: settings, stations, packets",
    "replay": "play a capture as a KISS TNC on a TCP port, to run without a radio",
    "gps-replay": "play a drive as a gpsd on a TCP port, to run a moving station without a car or a GPS",
    "capture": "record what the radio sends into a file",
    "doctor": "check this computer: Python, folders, database, call, serial ports, the map, the service",
    "open": "open the page in the browser, starting the daemon first if none is running",
    "stop": "end the daemon cleanly (the one that holds the data folder)",
    "app": "the desktop app: the page in a window and a tray icon, attaching to the daemon or starting one (needs neoaprs[app])",
}


def _run(argv: list[str]) -> int:
    from neoaprs.daemon import main as run_daemon
    return run_daemon(argv)


def _service(argv: list[str]) -> int:
    from .servicecmd import main as service
    return service(argv)


def _map(argv: list[str]) -> int:
    from .mapcmd import main as map_command
    return map_command(argv)


def _db(argv: list[str]) -> int:
    from .dbcmd import main as db_command
    return db_command(argv)


def _replay(argv: list[str]) -> int:
    from .replaycmd import main as replay
    return replay(argv)


def _gps_replay(argv: list[str]) -> int:
    from .gpsreplaycmd import main as gps_replay
    return gps_replay(argv)


def _capture(argv: list[str]) -> int:
    from .capturecmd import main as capture
    return capture(argv)


def _open(argv: list[str]) -> int:
    from .opencmd import main as open_page
    return open_page(argv)


def _stop(argv: list[str]) -> int:
    from .stopcmd import main as stop
    return stop(argv)


def _app(argv: list[str]) -> int:
    from neoaprs.desktop.cmd import main as app
    return app(argv)


def _doctor(argv: list[str]) -> int:
    from .doctor import main as doctor
    return doctor(argv)


HANDLERS: dict[str, Callable[[list[str]], int]] = {"run": _run, "service": _service, "map": _map, "db": _db, "replay": _replay, "gps-replay": _gps_replay, "capture": _capture, "doctor": _doctor, "open": _open, "stop": _stop, "app": _app}


def commands_text() -> str:
    width = max(len(name) for name in COMMANDS)
    lines = [f"  {name:<{width}}  {text}" for name, text in COMMANDS.items()]
    return "commands (the options above are those of `run`, which is what no command means):\n" + "\n".join(lines) + "\n\n`neoaprs COMMAND --help` says what a command takes."


def help_text() -> str:
    """The help of the daemon's options (what `python -m neoaprs --help` prints) and under it the commands."""
    from neoaprs.daemon import build_parser
    parser = build_parser("neoaprs")
    parser.usage = "neoaprs [COMMAND] [-h] [--data DATA] [--port PATH] [--web-port N] [--debug] [--version]"
    parser.epilog = commands_text()
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    return parser.format_help()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print(help_text())
        return 0
    if args and args[0] in HANDLERS:
        return HANDLERS[args[0]](args[1:])
    if args and not args[0].startswith("-"):
        print(f"neoaprs: {args[0]}: no such command\n\n{commands_text()}", file=sys.stderr)
        return 2
    return _run(args)


def gui_main() -> int:
    """`neoaprsw`: the same, for a program that has no console (Windows starts it so at login): the streams that are not there are replaced, so that a print or a usage error cannot fail."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    return main()
