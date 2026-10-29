"""The daemon: python -m neoaprs [--data DIR] [--port PATH] [--web-port N] [--debug]

One process, one asyncio loop. Everything NeoAPRS keeps is in one database, data/neoaprs.sqlite; the log is data/neoaprs.log, rotated and bounded; only what matters for `systemctl status`
goes to stderr (warnings, errors and the lines of the migrations; not when stderr is a file, where a launcher keeps what is said before the log exists). SIGTERM, SIGINT and SIGHUP (on Windows SIGINT, SIGTERM and SIGBREAK) end the program the same way, and so does the file `neoaprs.stop` in the data folder (`neoaprs stop`, neoaprs/stopfile.py); a second signal while it closes ends the process at once. Exit code 2: the database cannot be used, or another NeoAPRS has the data folder; a
restart would not cure either (the unit does not restart on it).
The page is served by neoaprs/web/server.py on web/port of the settings (default http://127.0.0.1:7303/; web/network opens it to the network), or on the next free port of the ten after it; the log says where ("web page at ..."), and so does the file neoaprs-web.url of the data folder while the page is served (neoaprs/cli/logfile.py), and
when none of them is free the daemon runs without the page.
After Update now of an AppImage the process, once the daemon has ended, runs the new file with the same arguments (neoaprs/selfreplace.py).
"""
import argparse
import asyncio
import contextlib
import io
import logging
import logging.handlers
import os
import platform
import signal
import stat
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import FrameType
from typing import Any

from . import PROGRAM, VERSION, selfreplace, stopfile
from .config import Config
from .controller import Controller
from .dberror import SqlError, StoreError
from .instancelock import AlreadyRunning, InstanceLock
from .migrationlog import MIGRATION_LOG
from .paths import default_data_dir
from .cli import uncaught
from .cli.logfile import LOG_NAME, START_FORMAT
from .cli.installkind import detect_here
from .cli.supportgather import system_description
from .cli.servicecmd import appimage_file
from .web.server import WebServer

DATABASE_UNUSABLE = 2
FOLDER_UNUSABLE = 1
SIGNAL_POLL_SEC = 0.5                                    # on Windows the loop waits in a call that a signal does not end: this is how long the program may take to notice Ctrl+C


def _port(text: str) -> int:
    value = int(text)
    if not 0 <= value <= 65535:
        raise argparse.ArgumentTypeError(f"{value} is not a port (0 to 65535)")
    return value


class _UtcFormatter(logging.Formatter):
    converter = staticmethod(time.gmtime)


class _LogFile(logging.handlers.RotatingFileHandler):
    """The rotating log that a program holding the file open cannot stop: on Windows the rename of a rollover fails then, and the log goes on in the file it has, the rollover tried again a minute later
    (the plain handler would try at every line, and lose every one)."""
    RETRY_SEC = 60.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._not_before = 0.0

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        return bool(time.monotonic() >= self._not_before and super().shouldRollover(record))

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except OSError:
            self._not_before = time.monotonic() + self.RETRY_SEC
            if self.stream is None:                          # (the rollover closes the file first)
                self.stream = self._open()


def _is_a_file(stream: Any) -> bool:
    """Is the stream a file on a disk? A program that was started with its output in a file (`neoaprs open`, a launcher) keeps there what is said before the log exists, a traceback; the log has every line after."""
    try:
        return stat.S_ISREG(os.fstat(stream.fileno()).st_mode)
    except (OSError, ValueError, AttributeError):
        return False


def _for_stderr(record: logging.LogRecord) -> bool:
    """What goes to stderr, and so to the journal: warnings and errors, and the lines of the migrations (once per upgrade, and they say what was changed in what the operator stored)."""
    return record.levelno >= logging.WARNING or record.name == MIGRATION_LOG


def setup_logging(data_dir: Path, debug: bool) -> None:
    # the level is in the line so that a health check tells an error from a line that only contains the word by what the log says it is
    fmt = _UtcFormatter("%(asctime)sZ  %(levelname)s  %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    # bounded: 20 MB a file, five files, whatever the debug flag says
    file_handler = _LogFile(data_dir / LOG_NAME, maxBytes=20_000_000, backupCount=4, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    if sys.stderr is not None:                               # (a program without a console, pythonw or a windowed build, has none)
        if not sys.stderr.isatty() and isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")      # (a pipe, a file or the journal: UTF-8, so that a line with a character the system's code page has not, "14 → 12" on Windows, is not lost)
        if not _is_a_file(sys.stderr):
            err = logging.StreamHandler(sys.stderr)
            err.addFilter(_for_stderr)
            err.setFormatter(fmt)
            root.addHandler(err)
    logging.getLogger("tornado.access").setLevel(logging.WARNING)
    logging.getLogger("tornado.general").setLevel(logging.WARNING)


def _private_data_dir(data_dir: Path, log: logging.Logger) -> None:
    try:
        os.chmod(data_dir, 0o700)             # main() sets the umask for what is made from now on; a folder that is there already (by hand, a restore) is made private too
    except OSError as e:
        log.warning("the data directory %s could not be made private (%s): other users of this computer may be able to read the database", data_dir, e)


def _stop_on_signals(loop: asyncio.AbstractEventLoop) -> asyncio.Event:
    """The event that SIGTERM, SIGINT and SIGHUP (SIGBREAK, Ctrl+Break, on Windows) set: the service manager's way to end the program. Must run in the main thread. `signal.signal` is
    what both systems have (the loop's add_signal_handler is POSIX only); the handler is Python code run between two instructions of the main thread, so it hands the event to the loop. A second signal while the program is closing
    ends the process at once, with the exit code 128 + the signal, for a closing that hangs."""
    stop = asyncio.Event()
    told: list[int] = []

    def first() -> None:
        stop.set()
        logging.getLogger("neoaprs").info("%s is told to stop; a second signal ends the process at once", PROGRAM)

    def set_stop(number: int, frame: FrameType | None) -> None:
        if told:                                         # (the closing hangs, on a database thread that does not end, say: this is the operator's way out)
            with contextlib.suppress(OSError):
                os.write(2, f"{PROGRAM}: a second signal: the process ends at once\n".encode())      # (not the log: a handler must not ask for the lock of the log, which the code it interrupted may hold)
            os._exit(128 + number)
        told.append(number)
        loop.call_soon_threadsafe(first)

    for name in ("SIGTERM", "SIGINT", "SIGHUP", "SIGBREAK"):
        number = getattr(signal, name, None)             # (not every system has every one)
        if number is not None:
            signal.signal(number, set_stop)
    return stop


async def _poll_for_signals(stop: asyncio.Event) -> None:
    """Windows only: a signal handler of Python runs when the main thread is back in Python, and the selector loop waits in a call that Ctrl+C does not end; a short timer sees to it."""
    while not stop.is_set():
        await asyncio.sleep(SIGNAL_POLL_SEC)


def _take_the_data_folder(data_dir: Path) -> InstanceLock | None:
    """The lock of the data folder, or None, with the reason on stderr, when another NeoAPRS has it (its log is not ours to write to)."""
    lock = InstanceLock(data_dir)
    try:
        lock.acquire()
    except AlreadyRunning as e:
        if sys.stderr is not None:
            print(f"neoaprs: {e}", file=sys.stderr)
        return None
    return lock


async def run(args: argparse.Namespace, after: list[list[str]] | None = None) -> int:
    """Runs the daemon until it is told to stop; the command line that is to run in the place of the process once it has ended (Update now) is put in `after`."""
    data_dir = Path(args.data).expanduser().resolve()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"neoaprs: the data folder {data_dir} cannot be made or used: {e.strerror or e}", file=sys.stderr)
        return FOLDER_UNUSABLE
    lock = _take_the_data_folder(data_dir)
    if lock is None:
        return DATABASE_UNUSABLE
    try:
        return await _run_locked(args, data_dir, [] if after is None else after)
    finally:
        lock.release()


async def _run_locked(args: argparse.Namespace, data_dir: Path, after: list[list[str]]) -> int:
    setup_logging(data_dir, args.debug)
    log = logging.getLogger("neoaprs")
    _private_data_dir(data_dir, log)
    log.info(START_FORMAT, PROGRAM, VERSION, data_dir)
    install = detect_here(data_dir)
    log.info("running on %s, %s, Python %s, installed as %s, pid %d", system_description(), platform.machine(), platform.python_version(), install.kind, os.getpid())
    restore = uncaught.install(log)
    asyncio.get_running_loop().set_exception_handler(uncaught.loop_handler(log))

    def page(ctl: Controller, config: Config) -> WebServer:
        return WebServer(ctl, config if args.web_port is None else replace(config, web_port=args.web_port))

    controller = Controller(data_dir, busy_ms=3000, port=args.port, web=page, install=install, auto_map=True)         # the daemon must not stand still behind another writer: a few seconds
    controller.debug = args.debug
    stop = _stop_on_signals(asyncio.get_running_loop())
    stopfile.clear(data_dir)                                 # (a request left by a stop that found nobody running is not for this run)
    helpers = [asyncio.create_task(stopfile.watch(data_dir, stop))]
    if sys.platform == "win32":
        helpers.append(asyncio.create_task(_poll_for_signals(stop)))
    try:
        code = await _serve(controller, stop, log)
        if controller.reexec:
            after.append(controller.reexec)
        return code
    except Exception:
        log.critical("the daemon ends with an exception nothing caught", exc_info=True)
        raise
    finally:
        for helper in helpers:
            helper.cancel()
        await asyncio.gather(*helpers, return_exceptions=True)
        stopfile.clear(data_dir)
        restore()


async def _serve(controller: Controller, stop: asyncio.Event, log: logging.Logger) -> int:
    try:
        await controller.start()
    except (StoreError, SqlError) as e:
        log.error("the database could not be used: %s", e)
        await controller.stop()
        return DATABASE_UNUSABLE
    except BaseException:
        await controller.stop()                                 # (whatever failed, the port, the page's listener and the database thread are not left behind)
        raise
    log.info("%s is running", PROGRAM)
    stopfile.clear_restart(controller.data_dir)              # (a restart as a new version is over)
    selfreplace.remove_old(appimage_file())
    await stop.wait()
    log.info("%s is closing", PROGRAM)
    await controller.stop()
    log.info("%s ended", PROGRAM)
    return 0


def build_parser(prog: str = "neoaprs") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description="An APRS client: reads the KISS port of a radio and shows the stations it hears.")
    parser.add_argument("--data", default=str(default_data_dir()), help="the data directory: neoaprs.sqlite (everything NeoAPRS keeps) and the log; default %(default)s")
    parser.add_argument("--port", default="", metavar="PATH", help="the radio's port for this run only (the setting serial/port is not changed): /dev/ttyUSB0, COM3, socket://host:port for KISS over TCP (Direwolf: socket://127.0.0.1:8001), bt://AA:BB:CC:DD:EE:FF for a paired Bluetooth device (Linux), ble://AA:BB:CC:DD:EE:FF for a Bluetooth LE KISS TNC (needs the extra ble), a replay's pseudo-terminal")
    parser.add_argument("--web-port", type=_port, default=None, metavar="N", help="the page's port for this run only (the setting web/port is not changed); 0 is a free port, which the log tells")
    parser.add_argument("--debug", action="store_true", help="log more (also NEOAPRS_DEBUG=1)")
    parser.add_argument("--version", action="version", version=f"{PROGRAM} {VERSION}")
    return parser


def main(argv: list[str] | None = None, prog: str = "neoaprs") -> int:
    """Runs the daemon until it is told to stop; `argv` is the flags (the command line's when None)."""
    os.umask(0o077)                                          # everything this program creates (the log, the copies, the folders) is for this user only
    args = build_parser(prog).parse_args(argv)
    if os.environ.get("NEOAPRS_DEBUG") == "1":
        args.debug = True
    after: list[list[str]] = []
    try:
        code = asyncio.run(run(args, after))
    except KeyboardInterrupt:
        return 0
    if after:
        selfreplace.reexec(after[0])                         # (returns only when neither the new file nor the old one could be started)
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
