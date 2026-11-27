"""Windows: a stand-in for the daemon (run DETACHED_PROCESS by a test, one process for each way of asking,
so that the ways cannot disturb each other). It starts a console program, asks it to end the way its first
argument names, and writes to the JSON file of its second argument the program's creation flags, the calls
with their results and GetLastError, what the program heard, and that the asker is still alive afterwards.

    break_group       a CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP child, asked the daemon's way: winchild.ask_to_end,
                      which starts the disposable asker (neoaprs/winask.py)
    break_shared      a CREATE_NEW_PROCESS_GROUP child on this process's console, Ctrl-Break to its group from here
    ctrl_c_inherited  a CREATE_NO_WINDOW child, Ctrl-C to its console: the control, a child that inherits
                      "ignore Ctrl-C" does not hear it
"""

import json
import logging
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
WAYS = ("break_group", "break_shared", "ctrl_c_inherited")
FLAGS = {"break_group": NO_WINDOW | NEW_GROUP, "break_shared": NEW_GROUP, "ctrl_c_inherited": NO_WINDOW}
ALIVE_SEC = 2.0  # how long the asker waits after the ask: an event that ended it would have done so


class Lines(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def ask(way: str, folder: Path) -> dict[str, Any]:
    said = folder / f"{way}.child"
    lines = Lines()
    logging.getLogger("neoaprs.childprogram").addHandler(lines)
    logging.getLogger("neoaprs.childprogram").setLevel(logging.DEBUG)
    k = winchild.kernel32()
    child = subprocess.Popen([sys.executable, "-c", CHILD, str(said)], creationflags=FLAGS[way])
    deadline = time.monotonic() + WAIT_SEC
    while time.monotonic() < deadline and not (said.exists() and said.read_text() == "up"):
        time.sleep(0.05)
    steps: winchild.Steps = []
    try:
        if way == "break_group":
            sent = winchild.ask_to_end(child.pid)
        elif way == "break_shared":
            sent = bool(winchild._step(steps, k, "GenerateConsoleCtrlEvent", winchild.CTRL_BREAK_EVENT, child.pid))
        else:
            # this disposable process takes no Ctrl-C itself (the child, started before, does not inherit that)
            winchild._step(steps, k, "SetConsoleCtrlHandler", None, True)
            sent = winchild.send_event(child.pid, 0, 0, k, steps) == winchild.SENT
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
        "sent": sent,
        "code": code,
        "child": said.read_text() if said.exists() else "",
        "steps": steps,
        "log": lines.lines,
        "asker_alive": True,
    }


def main(way: str, out: Path) -> None:
    out.write_text(json.dumps(ask(way, out.parent), indent=1))


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
