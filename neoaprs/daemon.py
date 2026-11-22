"""The daemon: python -m neoaprs [--data DIR] [--port PATH] [--hf-port URL] [--web-port N] [--debug]

One process, one asyncio loop. Signals or `neoaprs.stop` end it; a second signal ends it at once.
Exit code 2: the database cannot be used or another NeoAPRS holds the data folder."""
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
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from . import PROGRAM, VERSION, selfreplace, stopfile
from .dberror import SqlError, StoreError
from .instancelock import AlreadyRunning, InstanceLock
from .migrationlog import MIGRATION_LOG
from .paths import default_data_dir
from .cli import uncaught
from .cli.logfile import LOG_NAME, START_FORMAT, page_of_the_run_before

if TYPE_CHECKING:
    from .controller import Controller

DATABASE_UNUSABLE = 2
FOLDER_UNUSABLE = 1
# On Windows the loop waits in a call that a signal does not end; this bounds the delay for Ctrl+C.
SIGNAL_POLL_SEC = 0.5


def _port(text: str) -> int:
    value = int(text)
    if not 0 <= value <= 65535:
        raise argparse.ArgumentTypeError(f"{value} is not a port (0 to 65535)")
    return value


class _UtcFormatter(logging.Formatter):
    converter = staticmethod(time.gmtime)


class _LogFile(logging.handlers.RotatingFileHandler):
    """Rotating log that survives a failed rollover (Windows: another program holds the file)."""
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
            # The rollover closes the file first.
            if self.stream is None:
                self.stream = self._open()


def _is_a_file(stream: Any) -> bool:
    """Return True if the stream is a regular file."""
    try:
        return stat.S_ISREG(os.fstat(stream.fileno()).st_mode)
    except (OSError, ValueError, AttributeError):
        return False


def _for_stderr(record: logging.LogRecord) -> bool:
    """Pass warnings, errors and migration lines to stderr, and so to the journal."""
    return record.levelno >= logging.WARNING or record.name == MIGRATION_LOG


def setup_logging(data_dir: Path, debug: bool) -> None:
    # The level is in the line so that a health check can tell an error from a mention of one.
    fmt = _UtcFormatter("%(asctime)sZ  %(levelname)s  %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    # Bounded to five files of 20 MB, with or without debug.
    file_handler = _LogFile(data_dir / LOG_NAME, maxBytes=20_000_000, backupCount=4, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    # A windowed build or pythonw has no stderr.
    if sys.stderr is not None:
        if not sys.stderr.isatty() and isinstance(sys.stderr, io.TextIOWrapper):
            # UTF-8 for a pipe or file, so that characters the Windows code page lacks survive.
            sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
        if not _is_a_file(sys.stderr):
            err = logging.StreamHandler(sys.stderr)
            err.addFilter(_for_stderr)
            err.setFormatter(fmt)
            root.addHandler(err)
    logging.getLogger("tornado.access").setLevel(logging.WARNING)
    logging.getLogger("tornado.general").setLevel(logging.WARNING)


def _private_data_dir(data_dir: Path, log: logging.Logger) -> None:
    try:
        # The umask covers new files; a folder that already exists is made private here.
        os.chmod(data_dir, 0o700)
    except OSError as e:
        log.warning("the data directory %s could not be made private (%s): other users of this computer may be able to read the database", data_dir, e)


def _stop_on_signals(loop: asyncio.AbstractEventLoop) -> asyncio.Event:
    """Return an event that SIGTERM, SIGINT, SIGHUP and SIGBREAK set; call from the main thread.

    A second signal exits at once. `signal.signal` is used as add_signal_handler is POSIX only."""
    stop = asyncio.Event()
    told: list[int] = []

    def first() -> None:
        stop.set()
        logging.getLogger("neoaprs").info("%s is told to stop; a second signal ends the process at once", PROGRAM)

    def set_stop(number: int, frame: FrameType | None) -> None:
        if told:
            with contextlib.suppress(OSError):
                # Not the log: the interrupted code may hold the log's lock.
                os.write(2, f"{PROGRAM}: a second signal: the process ends at once\n".encode())
            os._exit(128 + number)
        told.append(number)
        loop.call_soon_threadsafe(first)

    for name in ("SIGTERM", "SIGINT", "SIGHUP", "SIGBREAK"):
        number = getattr(signal, name, None)
        if number is not None:
            signal.signal(number, set_stop)
    return stop


async def _poll_for_signals(stop: asyncio.Event) -> None:
    """Wake the loop regularly on Windows, where its wait call is not interrupted by Ctrl+C."""
    while not stop.is_set():
        await asyncio.sleep(SIGNAL_POLL_SEC)


def kept_port(data_dir: Path) -> int:
    """Return the port the previous daemon served the page on, or 0.

    Without a note it comes from the previous run's log: call it after this run's start line."""
    port = stopfile.noted_port(data_dir)
    if port is None and stopfile.restarting(data_dir):
        try:
            port = urlsplit(page_of_the_run_before(data_dir) or "").port
        except ValueError:
            port = None
    return port or 0


def _take_the_data_folder(data_dir: Path) -> InstanceLock | None:
    """Return the data folder's lock, or None (reason on stderr) if another NeoAPRS holds it."""
    lock = InstanceLock(data_dir)
    try:
        lock.acquire()
    except AlreadyRunning as e:
        if sys.stderr is not None:
            print(f"neoaprs: {e}", file=sys.stderr)
        return None
    return lock


async def run(args: argparse.Namespace, after: list[list[str]] | None = None) -> int:
    """Run the daemon until stopped; a command to run afterwards (Update now) goes in `after`."""
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
    # Imported late so that `--version` and `--help` stay fast and the log has its first line.
    from .cli.installkind import detect_here, developers_run
    from .cli.systemdescription import system_description
    from .config import Config
    from .controller import Controller
    from .web.server import WebServer
    install = detect_here(data_dir)
    log.info("running on %s, %s, Python %s, installed as %s, pid %d", system_description(), platform.machine(), platform.python_version(), install.kind, os.getpid())
    restore = uncaught.install(log)
    asyncio.get_running_loop().set_exception_handler(uncaught.loop_handler(log))

    stay_on = kept_port(data_dir)

    def page(ctl: Controller, config: Config) -> WebServer:
        return WebServer(ctl, config if args.web_port is None else replace(config, web_port=args.web_port), kept_port=stay_on)

    # busy_ms: wait at most a few seconds behind another database writer.
    controller = Controller(data_dir, busy_ms=3000, port=args.port, hf_port=getattr(args, "hf_port", ""), web=page, install=install, auto_map=True, encryption=args.encryption)
    controller.debug = args.debug
    controller.updatecheck.developer = developers_run(install)
    stop = _stop_on_signals(asyncio.get_running_loop())
    # A stop request left by a stop that found nobody running is not for this run.
    stopfile.clear(data_dir)
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


async def _serve(controller: "Controller", stop: asyncio.Event, log: logging.Logger) -> int:
    try:
        await controller.start()
    except (StoreError, SqlError) as e:
        log.error("the database could not be used: %s", e)
        await controller.stop()
        return DATABASE_UNUSABLE
    except BaseException:
        # Release the port, the page's listener and the database thread whatever failed.
        await controller.stop()
        raise
    log.info("%s is running", PROGRAM)
    stopfile.clear_restart(controller.data_dir)
    from .cli.servicecmd import appimage_file
    selfreplace.remove_old(appimage_file())
    await stop.wait()
    log.info("%s is closing", PROGRAM)
    await controller.stop()
    log.info("%s ended", PROGRAM)
    return 0


def build_parser(prog: str = "neoaprs") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description="An APRS client: reads the KISS port of a radio and shows the stations it hears.")
    parser.add_argument("--data", default=str(default_data_dir()), help="the data directory: neoaprs.sqlite (everything NeoAPRS keeps) and the log; default %(default)s")
    parser.add_argument("--port", default="", metavar="PATH", help="radio 1's port for this run only (its own port is not changed): /dev/ttyUSB0, COM3, socket://host:port for your own Direwolf or soundmodem (Direwolf: socket://127.0.0.1:8001), bt://AA:BB:CC:DD:EE:FF for a paired Bluetooth device (Linux), ble://AA:BB:CC:DD:EE:FF for a Bluetooth LE KISS TNC (needs the extra ble), a replay's pseudo-terminal")
    parser.add_argument("--hf-port", default="", metavar="URL", help="the first Mercury radio's modem for this run only, one that something else runs (socket://127.0.0.1:8100: its KISS port, the control port 200 above), instead of the one the daemon starts; the benches' way")
    parser.add_argument("--web-port", type=_port, default=None, metavar="N", help="the page's port for this run only (the setting web/port is not changed); 0 is a free port, which the log tells; after Update now the page stays on the port it was on")
    parser.add_argument("--debug", action="store_true", help="log more (also NEOAPRS_DEBUG=1)")
    parser.add_argument("--encryption", action="store_true", help="allow encrypted messages between two stations that have each other's key: for exceptional circumstances only, and only in a build made with NEOAPRS_ENCRYPTION=1")
    parser.add_argument("--version", action="version", version=f"{PROGRAM} {VERSION}")
    return parser


def main(argv: list[str] | None = None, prog: str = "neoaprs") -> int:
    """Run the daemon until stopped; `argv` defaults to the command line."""
    # Everything this program creates is for this user only.
    os.umask(0o077)
    args = build_parser(prog).parse_args(argv)
    if os.environ.get("NEOAPRS_DEBUG") == "1":
        args.debug = True
    after: list[list[str]] = []
    try:
        code = asyncio.run(run(args, after))
    except KeyboardInterrupt:
        return 0
    if after:
        # Returns only if neither the new file nor the old one could be started.
        selfreplace.reexec(after[0])
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
