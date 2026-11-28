"""PHP's own web server on a free loopback port, serving a folder laid out as the project's site is,
for the tests of the server's endpoints (server/neo/)."""

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

PHP = shutil.which("php")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class PhpServer:
    def __init__(self, site: Path) -> None:
        self.site = site
        self.process: subprocess.Popen[bytes] | None = None
        self.port = free_port()

    def start(self, workers: int = 1) -> None:
        """Start the server and wait until it listens; another port is tried if it could not bind."""
        environment = {"PATH": os.environ["PATH"], **({"PHP_CLI_SERVER_WORKERS": str(workers)} if workers > 1 else {})}
        assert PHP is not None
        for _ in range(3):
            self.process = subprocess.Popen(
                [PHP, "-S", f"127.0.0.1:{self.port}", "-t", str(self.site)],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and self.process.poll() is None:
                try:
                    socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                    return
                except OSError:
                    time.sleep(0.05)
            if self.process.poll() is None:
                break
            self.port = free_port()
        raise AssertionError("php did not start")

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process.wait(10)
