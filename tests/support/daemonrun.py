"""The daemon's own `run()` (neoaprs/daemon.py) in the test's process, on a data folder of the test.

It has the signal handlers, logging, folder lock, Controller and stop file, without a child process,
so a test can break what the daemon stands on. `signals_restored` gives SIGTERM, SIGINT and SIGHUP
back.
"""

import argparse
import asyncio
import signal
from collections.abc import Iterator
from pathlib import Path

import pytest

from neoaprs import daemon, stopfile
from tests.support.env import until

# The longest a test waits for a start or stop while the machine runs a whole suite.
PATIENCE_SEC = 60.0


@pytest.fixture
def signals_restored() -> Iterator[None]:
    names = [n for n in ("SIGTERM", "SIGINT", "SIGHUP", "SIGBREAK") if hasattr(signal, n)]
    saved = {n: signal.getsignal(getattr(signal, n)) for n in names}
    yield
    for n, handler in saved.items():
        signal.signal(getattr(signal, n), handler)


def arguments(data: Path, *extra: str) -> argparse.Namespace:
    return daemon.build_parser().parse_args(["--data", str(data), "--web-port", "0", *extra])


def log_text(data: Path) -> str:
    path = data / "neoaprs.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


class InProcess:
    def __init__(self, data: Path, *extra: str) -> None:
        self.data = data
        self.after: list[list[str]] = []
        self.task: asyncio.Task[int] = asyncio.ensure_future(daemon.run(arguments(data, *extra), self.after))

    async def running(self) -> bool:
        """Waits until the daemon says it is running or has ended; whether it is running."""
        await until(lambda: self.task.done() or "is running" in log_text(self.data), PATIENCE_SEC)
        return not self.task.done()

    async def stop(self) -> int:
        stopfile.request(self.data)
        return await asyncio.wait_for(self.task, PATIENCE_SEC)

    async def ended(self) -> int:
        """The exit code of a daemon that is going to end by itself."""
        return await asyncio.wait_for(self.task, PATIENCE_SEC)
