"""Windows: a stand-in for a daemon without a console (run DETACHED_PROCESS by a test). For each way of
asking a program to end, it starts a fresh console program hidden, asks, and writes to the JSON file named
by its one argument what each call returned (and GetLastError) and what the program heard.

    "ctrl_c": Ctrl-C to the console of a CREATE_NO_WINDOW child, as the daemon asks Mercury
    "break_attached": Ctrl-Break to the group of a CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP child, attached
    "break_detached": the same Ctrl-Break without attaching to any console
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from neoaprs import winchild

# says "up" once its handlers are in, then the name of the signal that came, and ends with 0
CHILD = (
    "import signal, sys, time\n"
    "out = sys.argv[1]\n"
    "def asked(number, frame):\n"
    "    open(out, 'w').write(signal.Signals(number).name)\n"
    "    sys.exit(0)\n"
    "signal.signal(signal.SIGINT, asked)\n"
    "if hasattr(signal, 'SIGBREAK'):\n"
    "    signal.signal(signal.SIGBREAK, asked)\n"
    "open(out, 'w').write('up')\n"
    "while True:\n"
    "    time.sleep(0.05)\n"
)
WAIT_SEC = 30.0
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NEW_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
WAYS = ("ctrl_c", "break_attached", "break_detached")


def _try(way: str, folder: Path) -> dict[str, Any]:
    said = folder / f"{way}.child"
    flags = NO_WINDOW if way == "ctrl_c" else NO_WINDOW | NEW_GROUP
    child = subprocess.Popen([sys.executable, "-c", CHILD, str(said)], creationflags=flags)
    deadline = time.monotonic() + WAIT_SEC
    while time.monotonic() < deadline and not (said.exists() and said.read_text() == "up"):
        time.sleep(0.05)
    steps: winchild.Steps = []
    try:
        if way == "ctrl_c":
            sent = winchild.ask_to_end(child.pid, steps=steps)
        else:
            sent = winchild.break_group(child.pid, attach=way == "break_attached", steps=steps)
    except Exception as e:  # what went wrong is the finding
        sent, steps = False, [*steps, {"exception": repr(e)}]
    try:
        code: int | None = child.wait(WAIT_SEC)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
        code = None
    return {"sent": sent, "code": code, "child": said.read_text() if said.exists() else "", "steps": steps}


def main(out: Path) -> None:
    out.write_text(json.dumps({way: _try(way, out.parent) for way in WAYS}, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
