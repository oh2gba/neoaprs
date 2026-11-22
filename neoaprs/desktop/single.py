"""One app per data folder: a second `neoaprs-app` raises the first one's window and exits.

The first holds a lock and listens on a loopback port; the second sends `show` (or `quit`)."""
import contextlib
import os
import logging
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path

from neoaprs.instancelock import APP_LOCK_NAME, AlreadyRunning, InstanceLock, is_file

from .splash import PID_NAME, PORT_NAME

log = logging.getLogger("neoaprs.desktop")

LOCK_NAME = APP_LOCK_NAME
COMMANDS = ("show", "quit")
HEAR_SEC = 2.0
ACCEPT_SEC = 0.25
# How long the second app waits for the port file; the lock is taken before the port is written.
FIND_SEC = 3.0


class SingleApp:
    def __init__(self, data: Path) -> None:
        self.data = data
        self._lock = InstanceLock(data, LOCK_NAME)
        self._server: socket.socket | None = None
        self._handler: Callable[[str], None] | None = None
        # Commands received before a handler was set.
        self._early: list[str] = []
        self._guard = threading.Lock()

    def acquire(self) -> bool:
        """Return True if this is the app (now listening), False if another app has the folder."""
        try:
            self._lock.acquire()
        except AlreadyRunning:
            return False
        try:
            self._listen()
        except OSError:
            self._lock.release()
            raise
        return True

    def running(self) -> bool:
        """Return whether an app holds the folder, by taking the lock briefly."""
        if not is_file(self.data / LOCK_NAME):
            return False
        probe = InstanceLock(self.data, LOCK_NAME)
        try:
            probe.acquire()
        except AlreadyRunning:
            return True
        except OSError:
            return False
        probe.release()
        return False

    def handle(self, handler: Callable[[str], None]) -> None:
        """Call `handler("show")` or `handler("quit")` from a server thread.

        Commands received since `acquire` are delivered too."""
        with self._guard:
            self._handler, early = handler, self._early
            self._early = []
        for command in early:
            self._deliver(command)

    def _deliver(self, command: str) -> None:
        with self._guard:
            handler = self._handler
            if handler is None:
                self._early.append(command)
                return
        try:
            handler(command)
        except Exception:
            log.exception("%s: the app could not do what the second one asked", command)

    def _listen(self) -> None:
        server = socket.create_server(("127.0.0.1", 0))
        # Closing a socket does not end a blocked accept everywhere, so poll the flag between waits.
        server.settimeout(ACCEPT_SEC)
        self._server = server
        (self.data / PORT_NAME).write_text(f"{server.getsockname()[1]}\n", encoding="ascii")
        (self.data / PID_NAME).write_text(f"{os.getpid()}\n", encoding="ascii")
        threading.Thread(target=self._serve, args=(server,), name="neoaprs-app-single", daemon=True).start()

    def _serve(self, server: socket.socket) -> None:
        while self._server is server:
            try:
                client, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with client:
                client.settimeout(HEAR_SEC)
                try:
                    heard = client.recv(16)
                except OSError:
                    continue
            command = heard.decode("ascii", errors="replace").strip()
            if command in COMMANDS:
                self._deliver(command)

    def tell_the_other(self, command: str) -> bool:
        """Send `show` or `quit` to the app holding the folder; False if unreachable in FIND_SEC."""
        deadline = time.monotonic() + FIND_SEC
        while True:
            try:
                port = int((self.data / PORT_NAME).read_text(encoding="ascii").strip())
                with socket.create_connection(("127.0.0.1", port), timeout=HEAR_SEC) as link:
                    link.sendall(command.encode("ascii") + b"\n")
                return True
            except (OSError, ValueError):
                if time.monotonic() >= deadline:
                    log.warning("another NeoAPRS app has this data folder, but it did not answer on the loopback")
                    return False
                time.sleep(0.1)

    def pid(self) -> int | None:
        """Return the pid the holding app wrote, or None if unreadable."""
        try:
            return int((self.data / PID_NAME).read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None


    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
            with contextlib.suppress(OSError):
                (self.data / PORT_NAME).unlink(missing_ok=True)
        self._lock.release()


def process_alive(pid: int) -> bool:
    """Return whether a process with this id exists.

    On Windows `os.kill` would terminate the process, so the process object is queried instead."""
    if os.name == "nt":
        return _alive_on_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _alive_on_windows(pid: int) -> bool:
    import ctypes

    windll = ctypes.windll  # type: ignore[attr-defined, unused-ignore]  # only Windows has it
    kernel32 = windll.kernel32
    # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
    handle = kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)
    if not handle:
        return False
    try:
        # 0x102 is WAIT_TIMEOUT: the process has not ended.
        return bool(kernel32.WaitForSingleObject(handle, 0) == 0x102)
    finally:
        kernel32.CloseHandle(handle)
