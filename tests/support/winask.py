"""Windows: a stand-in for a daemon without a console (run DETACHED_PROCESS by a test, one process for each
way of asking, so that the ways cannot disturb each other). It starts a console program, asks it to end
the way its first argument names, and writes to the JSON file of its second argument the program's
creation flags, every call with its result and GetLastError, what the program heard, and that the asker
itself is still alive afterwards.

    ctrl_c          a CREATE_NO_WINDOW child, Ctrl-C to its console, as the daemon asks Mercury
    break_attached  a CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP child, Ctrl-Break to its group on its console
    break_shared    a CREATE_NEW_PROCESS_GROUP child on this process's console (if it has one), Ctrl-Break to its group
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
WAYS = ("ctrl_c", "break_attached", "break_shared")
FLAGS = {"ctrl_c": NO_WINDOW, "break_attached": NO_WINDOW | NEW_GROUP, "break_shared": NEW_GROUP}
ALIVE_SEC = 2.0  # how long the asker waits after the ask: an echo that ended it would have done so


def ask(way: str, folder: Path) -> dict[str, Any]:
    said = folder / f"{way}.child"
    k = winchild.kernel32()
    before: winchild.Steps = []
    sharing, visible = winchild.console_of_own(k, before)
    child = subprocess.Popen([sys.executable, "-c", CHILD, str(said)], creationflags=FLAGS[way])
    deadline = time.monotonic() + WAIT_SEC
    while time.monotonic() < deadline and not (said.exists() and said.read_text() == "up"):
        time.sleep(0.05)
    steps: winchild.Steps = []
    try:
        if way == "ctrl_c":
            sent = winchild.ask_to_end(child.pid, k, steps)
        else:
            sent = winchild.break_group(child.pid, way == "break_attached", k, steps)
    except Exception as e:  # what went wrong is the finding
        sent, steps = False, [*steps, {"exception": repr(e)}]
    try:
        code: int | None = child.wait(WAIT_SEC)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
        code = None
    time.sleep(ALIVE_SEC)
    return {
        "child_flags": hex(FLAGS[way]),
        "asker_console_before": {"processes": sharing, "visible": visible, "steps": before},
        "sent": sent,
        "code": code,
        "child": said.read_text() if said.exists() else "",
        "steps": steps,
        "asker_alive": True,
    }


def main(way: str, out: Path) -> None:
    out.write_text(json.dumps(ask(way, out.parent), indent=1))


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
