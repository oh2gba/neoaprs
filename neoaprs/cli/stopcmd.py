"""`neoaprs stop [--data DIR] [--timeout SEC]`: ends the daemon that holds the data folder, cleanly (the same end as SIGTERM: the database is closed, the log says `NeoAPRS ended`), on every system. It writes the
file `neoaprs.stop` in the data folder (neoaprs/stopfile.py), which the daemon looks for, and waits until the daemon has let go of the instance lock. Exit code 0: it is not running now; 1: it did not end in time.
This is how the Windows uninstaller and the Start menu's "Stop NeoAPRS" end it; a service manager that restarts it (systemd, launchd) starts it again: use `systemctl --user stop neoaprs` there."""
import argparse
import time
from pathlib import Path

from neoaprs import stopfile
from neoaprs.paths import default_data_dir

from .daemonstate import is_running
from .output import say

POLL_SEC = 0.25


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neoaprs stop", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default=str(default_data_dir()), help="the data folder of the daemon; default %(default)s")
    p.add_argument("--timeout", type=float, default=30.0, metavar="SEC", help="how long to wait for it to end; default %(default)s")
    return p


def stop_daemon(data: Path, timeout: float) -> bool:
    """Asks the daemon that holds the data folder to end and waits up to `timeout` seconds for it to let go of the lock; True when none runs (any more). The desktop app's Quit is this too."""
    if not is_running(data):
        stopfile.clear(data)
        return True
    stopfile.request(data)
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
    say(f"stop: NeoAPRS on {data} did not end within {args.timeout:g} s; look at its log, or end the process neoaprsw.exe / neoaprs in the task manager")
    return 1
