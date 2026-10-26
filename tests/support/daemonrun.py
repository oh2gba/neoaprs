"""The daemon's own `run()` (neoaprs/daemon.py) in the test's process, on a data folder of the test: the signal handlers, the logging, the lock of the folder, the Controller and the stop file, as `python -m neoaprs`
has them, without a child process, so that a test can break what the daemon stands on (the migrations, the database file) and read what it did.

    daemon = InProcess(tmp_path / "data")             # starts it
    await daemon.running()                            # the log says "is running" (or the daemon ended: its code is daemon.task.result())
    code = await daemon.stop()                        # the stop file, as `neoaprs stop` writes it; the exit code

`signals_restored` is a fixture for the test module to import: the daemon takes SIGTERM, SIGINT, SIGHUP over, and the test gives them back."""
import argparse
import asyncio
import signal
from collections.abc import Iterator
from pathlib import Path

import pytest

from neoaprs import daemon, stopfile
from tests.support.env import until

PATIENCE_SEC = 60.0                 # a daemon that starts or stops while the machine runs a whole test suite takes its time: the longest a test waits for it, not how long it takes


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
