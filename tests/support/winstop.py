"""Windows: the daemon's own stop of a modem program, run DETACHED_PROCESS by a test as the daemon runs. It
starts a stand-in for Mercury through mercuryhelper.Program (the product's class, its own process group
and hidden console), stops it the product's way and writes to the JSON file of its one argument what the
stand-in heard, its exit code, the stop's log lines and that this process lives on.
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from neoaprs import mercuryhelper

# a Mercury that unkeys on Ctrl-Break (sigbreak.patch): it says "up", then writes what came and ends with 0
CHILD = (
    "import signal, sys, time\n"
    "out = sys.argv[1]\n"
    "def asked(number, frame):\n"
    "    open(out, 'w').write(signal.Signals(number).name)\n"
    "    sys.exit(0)\n"
    "signal.signal(signal.SIGBREAK, asked)\n"
    "open(out, 'w').write('up')\n"
    "print('up', flush=True)\n"
    "while True:\n"
    "    time.sleep(0.05)\n"
)
WAIT_SEC = 30.0


class Lines(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


async def stop_one(out: Path) -> dict[str, Any]:
    said = out.with_suffix(".child")
    lines = Lines()
    for name in ("neoaprs.mercury", "neoaprs.childprogram"):
        logging.getLogger(name).addHandler(lines)
        logging.getLogger(name).setLevel(logging.DEBUG)
    program = mercuryhelper.Program(lambda code, last: None)
    program.start([sys.executable, "-c", CHILD, str(said)], out.parent)
    process = program._process
    assert process is not None
    deadline = time.monotonic() + WAIT_SEC
    while time.monotonic() < deadline and not (said.exists() and said.read_text() == "up"):
        await asyncio.sleep(0.05)
    started = time.monotonic()
    await asyncio.to_thread(program.stop)
    return {
        "child": said.read_text() if said.exists() else "",
        "code": process.returncode,
        "stop_sec": round(time.monotonic() - started, 2),
        "log": lines.lines,
        "asker_alive": True,
    }


def main(out: Path) -> None:
    record = asyncio.run(stop_one(out))
    time.sleep(2.0)  # an echo that ended this process would have done so by now
    out.write_text(json.dumps(record, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
