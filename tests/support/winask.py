"""Windows: a stand-in for a daemon without a console (run DETACHED_PROCESS by a test) that starts a
console program hidden, as the daemon starts Mercury, asks it to end with winchild.ask_to_end and
writes what happened as JSON to the file named by its one argument.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

from neoaprs import winchild

# the program: says "up" once its Ctrl-C handler is in, writes "asked" when Ctrl-C comes and ends with 0
CHILD = (
    "import signal, sys, time\n"
    "out = sys.argv[1]\n"
    "def asked(*_):\n"
    "    open(out, 'w').write('asked')\n"
    "    sys.exit(0)\n"
    "signal.signal(signal.SIGINT, asked)\n"
    "open(out, 'w').write('up')\n"
    "while True:\n"
    "    time.sleep(0.05)\n"
)
WAIT_SEC = 60.0


def main(out: Path) -> None:
    said = out.with_suffix(".child")
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD, str(said)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    deadline = time.monotonic() + WAIT_SEC
    while time.monotonic() < deadline and not (said.exists() and said.read_text() == "up"):
        time.sleep(0.05)
    sent = winchild.ask_to_end(child.pid)
    try:
        code: int | None = child.wait(WAIT_SEC)
    except subprocess.TimeoutExpired:
        child.kill()
        code = None
    out.write_text(json.dumps({"sent": sent, "code": code, "child": said.read_text() if said.exists() else ""}))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
