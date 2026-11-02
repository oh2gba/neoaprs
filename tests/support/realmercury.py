"""Real Mercury instances and real NeoAPRS daemons on one computer, for the developer's benches (scripts/mercury-bench, scripts/mercury-sim): a Mercury started on Mercury's `fifo` audio backend (raw s32le PCM at
8 kHz through two named pipes, what it hears in and what it transmits out, so that a channel of ours can be the air between several of them), a daemon on a data folder of its own attached to that Mercury's ports
(`--port socket://127.0.0.1:BROADCAST`, as to any Mercury something else runs), and a page's socket on the daemon that holds the topics as the page would and drives it with the page's commands. The daemon may be
the checkout's (`python -m neoaprs`) or an installed one (the .deb's `/usr/bin/neoaprs`, the AppImage), so that the same scenario runs against what ships."""
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

RATE = 8000                      # samples a second of Mercury's fifo backend
SAMPLE_BYTES = 4                 # s32le: the 16-bit sample in the top half of each word


class Failure(Exception):
    """What a bench says when the thing it waited for did not happen; its text is the whole report."""


def fifo(folder: Path, name: str) -> str:
    make = getattr(os, "mkfifo", None)              # (POSIX; the Windows type check knows no such name: the benches on named pipes run on Linux)
    if make is None:
        raise Failure("named pipes of this kind are Linux's")
    path = folder / name
    make(path)
    return str(path)


def mercury_ini(busy_detect: bool = True) -> str:
    """What NeoAPRS writes for a Mercury it starts itself, as far as a bench needs it: the busy detector (the one carrier sense of the plane) and no message store."""
    return f"[channel]\nbusy_detect = {'true' if busy_detect else 'false'}\n[store]\nenabled = false\n"


def start_mercury(binary: str, folder: Path, name: str, capture: str, playback: str, ports: tuple[int, int], busy_detect: bool = True) -> subprocess.Popen[bytes]:
    """One Mercury on the fifo backend: it hears `capture`, transmits into `playback`, serves KISS on ports[0] and its control port on ports[1] (200 above, as the daemon expects), keys nothing (`-P none`), logs to the folder.
    ALSA_CONFIG_PATH is the bundled configuration beside the program when there is one (the fifo backend opens no sound card, but the program still reads the configuration at start)."""
    out = (folder / f"mercury-{name}.log").open("wb")
    ini = folder / f"mercury-{name}.ini"
    ini.write_text(mercury_ini(busy_detect), encoding="utf-8")
    argv = [binary, "-C", str(ini), "-m", "1", "-x", "fifo", "-i", capture, "-o", playback, "-b", str(ports[0]), "-p", str(ports[1]), "-P", "none", "-v"]
    env = dict(os.environ)
    conf = Path(binary).resolve().parent / "share" / "alsa" / "alsa.conf"
    if conf.is_file():
        env["ALSA_CONFIG_PATH"] = str(conf)
    return subprocess.Popen(argv, cwd=str(folder), stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, env=env)


def daemon_env() -> dict[str, str]:
    """The environment of a daemon of the bench: its radio is the port it is given, so it opens no serial port of the machine, and it asks no version page."""
    env = {k: v for k, v in os.environ.items() if k not in ("NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG")}
    env["NEOAPRS_SERIAL_PATTERN"] = "/dev/neoaprs-bench-no-such-port*"
    env["NEOAPRS_UPDATE_CHECK"] = "0"
    return env


def default_daemon() -> list[str]:
    """The daemon of this checkout."""
    return [sys.executable, "-m", "neoaprs"]


def write_settings(data: Path, rows: dict[str, str], daemon: list[str] | None = None) -> None:
    """The settings of a station before its daemon starts, written with the daemon's own `db set`."""
    for key, value in rows.items():
        subprocess.run([*(daemon or default_daemon()), "db", "--data", str(data), "set", key, value], check=True, capture_output=True, env=daemon_env())


def start_daemon(data: Path, ports: tuple[int, int], daemon: list[str] | None = None, fm_port: int = 0) -> subprocess.Popen[bytes]:
    """A daemon on its data folder, its HF radio attached to the Mercury on these ports (and its FM radio to the KISS hub on `fm_port`, when given), its page on a free port; its output beside the folder."""
    out = (data.parent / f"{data.name}.out").open("wb")
    argv = [*(daemon or default_daemon()), "--data", str(data), "--hf-port", f"socket://127.0.0.1:{ports[0]}", "--web-port", "0", *(["--port", f"socket://127.0.0.1:{fm_port}"] if fm_port else [])]
    return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, env=daemon_env())


def wait_for_page(daemon: subprocess.Popen[bytes], data: Path, seconds: float, offset: int = 0) -> str:
    """The address of the daemon's page, read from its log when it is up (from `offset` bytes into the log: a daemon started again on the same folder writes after the old run's lines)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if daemon.poll() is not None:
            raise Failure(f"the daemon on {data.name} ended with exit code {daemon.returncode} before its page was up")
        try:
            found = re.search(r"web page at (http://127\.0\.0\.1:\d+/)", (data / "neoaprs.log").read_bytes()[offset:].decode("utf-8", errors="replace"))
        except OSError:
            found = None
        if found:
            return found.group(1)
        time.sleep(0.1)
    raise Failure(f"no 'web page at' line in the log of {data.name} within {seconds:g} s")


def stop(process: subprocess.Popen[bytes], seconds: float) -> int | None:
    """Ends a process as the system would (SIGTERM), kills it when it does not end in time; its exit code."""
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            return process.wait(seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait()
    return process.returncode


class Page:
    """A page's socket on a daemon: the topics as the page holds them, the errors, and the commands. The socket is read all the time by a task of its own (a daemon drops a page that answers no ping for a while, and
    a station nobody is waiting for must stay current), so a wait is for a condition on the topics as they are."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.topics: dict[str, Any] = {}
        self.errors: list[dict[str, Any]] = []
        self.on_error: Callable[[str, dict[str, Any]], None] | None = None          # told of every refusal the daemon sends the page, as it comes
        self.closed = False
        self._connection: Any = None
        self._changed = asyncio.Event()
        self._reader: asyncio.Task[None] | None = None

    async def open(self, base: str) -> None:
        from tornado.websocket import websocket_connect
        self._connection = await websocket_connect("ws://" + base.removeprefix("http://") + "ws", connect_timeout=15)
        self._reader = asyncio.get_running_loop().create_task(self._read(), name=f"page {self.name}")

    async def _read(self) -> None:
        while True:
            raw = await self._connection.read_message()
            if raw is None:
                self.closed = True
                self._changed.set()
                return
            self._apply(json.loads(raw))
            self._changed.set()

    async def send(self, command: dict[str, Any]) -> None:
        await self._connection.write_message(json.dumps(command))

    async def until(self, what: str, condition: Callable[[], bool], seconds: float) -> float:
        """Waits until the condition holds on the topics; the seconds it took. Failure, with the radio's and the modem's state and the last refusal, when it does not within `seconds` or the daemon closed the socket."""
        loop = asyncio.get_running_loop()
        started = loop.time()
        deadline = started + seconds
        while True:
            self._changed.clear()                   # (cleared before the look, so that a message between the look and the wait is not missed)
            if condition():
                return loop.time() - started
            if self.closed:
                raise Failure(f"{self.name}: the daemon closed the socket")
            left = deadline - loop.time()
            if left <= 0:
                raise Failure(f"{self.name}: {what} did not happen within {seconds:g} s (hf {json.dumps(self.topics.get('hf', {}).get('state'))}, modem {json.dumps(self.modem())}, "
                              f"the last error {json.dumps(self.errors[-1]) if self.errors else 'none'})")
            try:
                await asyncio.wait_for(self._changed.wait(), left)
            except TimeoutError:
                pass

    async def drain(self, seconds: float) -> None:
        """Lets `seconds` pass with the socket read as always (for a step that has nothing to wait for but time)."""
        await asyncio.sleep(seconds)

    def _apply(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "state":
            self.topics[message["topic"]] = message["value"]
        elif kind == "patch":
            value = self.topics.setdefault(message["topic"], {})
            for op in message["ops"]:
                if op["op"] == "replace":
                    self.topics[message["topic"]] = value = op["value"]
                elif op["op"] == "set":
                    value[op["key"]] = op["value"]
                else:
                    value.pop(op["key"], None)
        elif kind == "error":
            self.errors.append(message)
            if self.on_error is not None:
                self.on_error(self.name, message)

    def modem(self) -> dict[str, Any]:
        return (self.topics.get("hf") or {}).get("modem") or {}

    def free(self) -> bool:
        """The radio connected and the modem neither keyed nor hearing a signal: a frame handed to it now goes at once (`beacon_now` and `send_message` are refused while the radio is held)."""
        return self.ready() and not self.modem().get("keyed") and not self.modem().get("busy")

    def ready(self) -> bool:
        """The HF radio connected to its Mercury and the control port heard."""
        return (self.topics.get("hf") or {}).get("state") == "connected" and self.modem().get("state") == "running"

    def fm_connected(self) -> bool:
        """The FM radio (the TNC of the topic `tnc`) connected to its line; any other state, waiting between two attempts or silent, is a radio that is not there."""
        return (self.topics.get("tnc") or {}).get("state") == "connected"

    def stations(self) -> dict[str, Any]:
        return self.topics.get("stations") or {}

    def messages(self) -> dict[str, Any]:
        return self.topics.get("messages") or {}

    def hears(self, call: str) -> bool:
        return any(s.get("call") == call for s in self.stations().values())

    def acked(self) -> int:
        """How many messages of this station's own are acked."""
        return sum(1 for m in self.messages().values() if m.get("direction") == "out" and m.get("state") == "acked")

    def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
        if self._connection is not None:
            self._connection.close()


class AprsIs:
    """A stand-in APRS-IS on the loopback for the iGate of a bench: greets, verifies any login, keeps every line gated to it. (The suite's tests/support/fakeaprsis.py needs pytest; a bench runs on the daemon's Python alone.)"""

    def __init__(self) -> None:
        self.packets: list[str] = []
        self.logins: list[str] = []
        self._server: asyncio.AbstractServer | None = None
        self.address = ""

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        self.address = f"127.0.0.1:{port}"

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"# bench-aprsd 1.0\r\n")
        try:
            while line := (await reader.readline()).decode("utf-8", "replace").rstrip("\r\n"):
                if line.startswith("user "):
                    self.logins.append(line)
                    writer.write(f"# logresp {line.split()[1]} verified, server BENCH\r\n".encode())
                elif not line.startswith("#"):
                    self.packets.append(line)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    def close(self) -> None:
        if self._server is not None:
            self._server.close()


class FmHub:
    """The FM air of a bench: a KISS-over-TCP server every FM radio of the simulation connects to as its TNC (the type kiss-tcp), where every frame one client writes is written to every other at once. No digipeaters,
    no collisions: the VHF network is the suite's business; here it is the other radio beside HF. `frames` keeps every frame relayed, as (from the client's number, the KISS bytes)."""

    def __init__(self) -> None:
        self.port = 0
        self.frames: list[tuple[int, bytes]] = []
        self._writers: dict[int, asyncio.StreamWriter] = {}
        self._server: asyncio.AbstractServer | None = None
        self._count = 0

    async def start(self) -> None:
        """Listens on the hub's port (a free one the first time; after `hang_up` the same one again, which is where the radios' daemons come back to)."""
        self._server = await asyncio.start_server(self._client, "127.0.0.1", self.port)
        self.port = self._server.sockets[0].getsockname()[1]

    def hang_up(self) -> None:
        """The FM air goes away as a radio unplugged or out of power does: the hub stops listening and closes every connection, so that each FM radio of the simulation loses its line and goes on trying; `start` brings it back."""
        self.close()
        self._server = None
        for writer in list(self._writers.values()):
            writer.close()

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._count += 1
        number = self._count
        self._writers[number] = writer
        try:
            while data := await reader.read(4096):
                self.frames.append((number, data))
                for other, w in self._writers.items():
                    if other != number:
                        w.write(data)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self._writers.pop(number, None)
            writer.close()

    def heard(self, text: bytes) -> bool:
        """Whether a frame with this text crossed the hub."""
        return any(text in data for _, data in self.frames)

    def close(self) -> None:
        if self._server is not None:
            self._server.close()

