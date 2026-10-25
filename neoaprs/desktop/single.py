"""One app to a data folder: a second `neoaprs-app` brings the window of the first one up and ends. The first holds a lock file (`neoaprs-app.lock`, the same kind of lock as the daemon's) and listens on a loopback
port that it writes into `neoaprs-app.port`; the second finds the lock taken, reads the port and says `show`. `neoaprs app --quit` says `quit` the same way (how the uninstaller ends the app). Nothing else is
understood, and the two words only raise the window and end the app, which whoever can write in the data folder can do anyway (it is private to the user), so no key is needed. The lock goes with the process,
however it ends, so a crash leaves no stale app behind (a stale port file is only a refused connection)."""
import contextlib
import os
import logging
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path

from neoaprs.instancelock import APP_LOCK_NAME, AlreadyRunning, InstanceLock

log = logging.getLogger("neoaprs.desktop")

LOCK_NAME = APP_LOCK_NAME
PORT_NAME = "neoaprs-app.port"
PID_NAME = "neoaprs-app.pid"           # the process id of the app that holds the folder: `--quit` waits for the process itself to be gone, not only for the lock (the window's engine unloads after the lock is let go)
COMMANDS = ("show", "quit")
HEAR_SEC = 2.0
ACCEPT_SEC = 0.25
FIND_SEC = 3.0                          # how long the second app waits for the first one's port file (the first has the lock a moment before it has the port)


class SingleApp:
    def __init__(self, data: Path) -> None:
        self.data = data
        self._lock = InstanceLock(data, LOCK_NAME)
        self._server: socket.socket | None = None
        self._handler: Callable[[str], None] | None = None
        self._early: list[str] = []                              # what was said before there was a window to say it to
        self._guard = threading.Lock()

    def acquire(self) -> bool:
        """True: this is the app, and it listens for a second one. False: another app has the folder."""
        try:
            self._lock.acquire()
        except AlreadyRunning:
            return False
        self._listen()
        return True

    def running(self) -> bool:
        """Whether an app holds the folder (the lock is taken for a moment and let go, as for the daemon's)."""
        if not (self.data / LOCK_NAME).is_file():
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
        """From now on `handler("show")` or `handler("quit")` is called, from a thread of its own, for what a second app says (and for what it said since `acquire`)."""
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
        server.settimeout(ACCEPT_SEC)                            # (closing a socket does not end an accept that waits in another thread on every system: it looks at the flag between waits)
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
                return                                           # closed
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
        """Says `show` or `quit` to the app that holds the folder; False when it cannot be reached (it is only started, and has no port yet, for FIND_SEC seconds; or it is gone)."""
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
        """The process id of the app that holds the folder, as it wrote it; None when there is none to read."""
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
    """Whether a process of this id is still there. Windows is asked for the process object itself (`os.kill` would end the process there); elsewhere a signal of 0 is sent, which only looks."""
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

    windll = ctypes.windll  # type: ignore[attr-defined, unused-ignore]        # (only Windows has it)
    kernel32 = windll.kernel32
    handle = kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)             # SYNCHRONIZE and PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        return bool(kernel32.WaitForSingleObject(handle, 0) == 0x102)           # WAIT_TIMEOUT: the process has not ended
    finally:
        kernel32.CloseHandle(handle)
