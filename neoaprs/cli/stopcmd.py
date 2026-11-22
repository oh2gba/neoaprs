"""`neoaprs stop [--data DIR] [--timeout SEC]`: end the daemon that holds the data folder, cleanly.

The end is the same as with SIGTERM (the database is closed, the log says `NeoAPRS ended`), on
every system. It writes the file `neoaprs.stop` in the data folder, which the daemon watches for,
and waits until the daemon releases the instance lock. Exit code 0: it is not running now; 1: it
did not end in time.
The Windows uninstaller and the Start menu's "Stop NeoAPRS" use it. A service manager (systemd,
launchd) restarts the daemon again: use `systemctl --user stop neoaprs` there."""

import argparse
import logging
import time
from pathlib import Path

from neoaprs import stopfile
from neoaprs.paths import default_data_dir

from .daemonstate import is_running
from .output import say

log = logging.getLogger("neoaprs.cli")

POLL_SEC = 0.25


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="neoaprs stop", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--data", default=str(default_data_dir()), help="the data folder of the daemon; default %(default)s")
    p.add_argument(
        "--timeout", type=float, default=30.0, metavar="SEC", help="how long to wait for it to end; default %(default)s"
    )
    return p


def stop_daemon(data: Path, timeout: float) -> bool:
    """Ask the daemon to end and wait up to `timeout` seconds for it to release the lock.

    Return True when no daemon runs (any more). The desktop app's Quit uses this too."""
    if not is_running(data):
        stopfile.clear(data)
        return True
    try:
        stopfile.request(data)
    except OSError:
        log.warning("the stop file could not be written in %s", data, exc_info=True)
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(POLL_SEC)
        if not is_running(data):
            stopfile.clear(data)
            return True
    return False


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    data = Path(args.data).expanduser().resolve()
    if not is_running(data):
        stopfile.clear(data)
        say(f"stop: NeoAPRS is not running on {data}")
        return 0
    if stop_daemon(data, args.timeout):
        say("stop: NeoAPRS has ended")
        return 0
    say(
        f"stop: NeoAPRS on {data} did not end within {args.timeout:g} s; look at its log, or end the process neoaprsw.exe / neoaprs in the task manager"
    )
    return 1
