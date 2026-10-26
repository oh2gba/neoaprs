#!/usr/bin/env python3
"""The smoke test of an installed NeoAPRS, on any system: a fake KISS TNC on a TCP port plays the capture of a radio, the daemon is started on a data folder of its own with that port, and what a user would see is checked.

The page and one script of it are fetched, the world map that ships with the program is asked for a range, the WebSocket of the page tells that the TNC is connected and that packets came, then the daemon is stopped the way its system stops a program (SIGTERM; Ctrl+Break on
Windows) and must end with exit code 0, a log whose last line is `NeoAPRS ended`, and a database that passes `PRAGMA integrity_check`. Nothing is sent to a radio and nothing leaves the loopback.

  scripts/smoke.py                                  the daemon of this interpreter: python -m neoaprs
  scripts/smoke.py --command VENV/bin/neoaprs        the installed command (VENV\\Scripts\\neoaprs.exe on Windows), as CI runs it against the wheel
Run it with the Python that has neoaprs installed (it uses Tornado's WebSocket client). Exit code 0: all is well; 1: the first thing that was not, said on stderr with the end of the daemon's log.
"""
import argparse
import asyncio
import json
import os
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "kiss" / "thd7-2026-10-21.bin"
LOG = "neoaprs.log"
DATABASE = "neoaprs.sqlite"
WINDOWS = sys.platform == "win32"


class Failure(Exception):
    """What was not as it should be."""


class FakeTnc:
    """A KISS TNC on the loopback: every client that connects is sent the capture and what it writes is thrown away."""
    DELAY_SEC = 0.5
    REPEAT_SEC = 3.0

    def __init__(self, capture: bytes) -> None:
        self.capture = capture
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.connections = 0
        self._clients: list[socket.socket] = []
        threading.Thread(target=self._accept, daemon=True).start()

    @property
    def url(self) -> str:
        return f"socket://127.0.0.1:{self.port}"

    def _accept(self) -> None:
        while True:
            try:
                client, _ = self.server.accept()
            except OSError:
                return
            self.connections += 1
            self._clients.append(client)
            threading.Thread(target=self._serve, args=(client,), daemon=True).start()

    def _serve(self, client: socket.socket) -> None:
        """The capture is played a moment after the connection and again every few seconds: a daemon throws away what is waiting at the moment it opens a line, and a slow runner may be past that or not."""
        threading.Thread(target=self._play, args=(client,), daemon=True).start()
        try:
            while client.recv(4096):
                pass
        except OSError:
            pass

    def _play(self, client: socket.socket) -> None:
        try:
            time.sleep(self.DELAY_SEC)
            while True:
                client.sendall(self.capture)
                time.sleep(self.REPEAT_SEC)
        except OSError:
            pass

    def close(self) -> None:
        self.server.close()
        for client in self._clients:
            client.close()


def command_line(command: str | None) -> list[str]:
    return [command] if command else [sys.executable, "-m", "neoaprs"]


def say(text: str) -> None:
    print(f"smoke: {text}", flush=True)


def log_tail(data: Path, lines: int = 25) -> str:
    try:
        return "\n".join((data / LOG).read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no log)"


def start_daemon(program: list[str], data: Path, tnc: FakeTnc) -> subprocess.Popen[bytes]:
    out = (data.parent / "daemon.out").open("wb")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0          # type: ignore[attr-defined, unused-ignore]  (so that Ctrl+Break reaches this child only)
    env = {k: v for k, v in os.environ.items() if k not in ("NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG")}
    env.setdefault("NEOAPRS_SERIAL_PATTERN", "/dev/neoaprs-smoke-no-such-port*")          # the daemon has a radio (--port) and searches no serial port of the machine
    env["NEOAPRS_UPDATE_CHECK"] = "0"                                                      # and does not ask the version page
    return subprocess.Popen([*program, "--data", str(data), "--port", tnc.url, "--web-port", "0"], stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, env=env, creationflags=flags)


def wait_for_page(daemon: subprocess.Popen[bytes], data: Path, seconds: float) -> str:
    """The address the log says the page is at."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if daemon.poll() is not None:
            raise Failure(f"the daemon ended with exit code {daemon.returncode} before the page was up")
        try:
            found = re.search(r"web page at (http://127\.0\.0\.1:\d+/)", (data / LOG).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            found = None
        if found:
            return found.group(1)
        time.sleep(0.1)
    raise Failure(f"no 'web page at' line in the log within {seconds:g} s")


def fetch(url: str) -> tuple[int, Any, bytes]:
    with urllib.request.urlopen(url, timeout=15) as answer:
        return answer.status, answer.headers, answer.read()


def check_the_page(base: str) -> None:
    status, headers, body = fetch(base)
    html = body.decode("utf-8", errors="replace")
    if status != 200 or '<div id="app"' not in html:
        raise Failure(f"GET / answered {status} and the page has no <div id=\"app\"> (the built page is not in the package?)")
    if "Content-Security-Policy" not in headers:
        raise Failure("GET / has no Content-Security-Policy header")
    scripts = re.findall(r'src="\./(assets/[^"]+\.js)"', html)
    if not scripts:
        raise Failure("the page names no script under assets/")
    status, _, script = fetch(base + scripts[0])
    if status != 200 or len(script) < 10_000:
        raise Failure(f"GET /{scripts[0]} answered {status} with {len(script)} bytes")
    say(f"the page and /{scripts[0]} ({len(script)} bytes) are served")


def check_the_world_map(base: str) -> None:
    """The world map that ships with the program is served from a data folder that has none (a wheel, the Windows app's frozen folder, an AppImage, a .deb: each has it in its own place)."""
    request = urllib.request.Request(base + "basemap-world.pmtiles", headers={"Range": "bytes=0-126"})
    try:
        with urllib.request.urlopen(request, timeout=15) as answer:
            status, head = answer.status, answer.read()
    except OSError as e:
        raise Failure(f"GET /basemap-world.pmtiles: {e} (the world map is not in the package?)") from None
    if status != 206 or head[:7] != b"PMTiles" or len(head) != 127 or head[101] < 4:
        raise Failure(f"GET /basemap-world.pmtiles answered {status} with {len(head)} bytes that are no PMTiles header to zoom 4")
    say(f"the world map is served (to zoom {head[101]})")


async def watch_the_socket(base: str, seconds: float) -> tuple[str, int]:
    """Opens /ws as the page does and waits until the TNC is `connected` and a packet is there; returns the state and the number of packets."""
    from tornado.websocket import websocket_connect
    topics: dict[str, Any] = {}
    connection = await websocket_connect("ws://" + base.removeprefix("http://") + "ws", connect_timeout=15)
    deadline = asyncio.get_running_loop().time() + seconds
    try:
        while True:
            left = deadline - asyncio.get_running_loop().time()
            tnc, packets = topics.get("tnc") or {}, topics.get("packets") or {}
            if tnc.get("state") == "connected" and packets:
                return "connected", len(packets)
            if left <= 0:
                raise Failure(f"within {seconds:g} s the TNC was {tnc.get('state')!r} with {len(packets)} packets (wanted connected and at least one)")
            try:
                raw = await asyncio.wait_for(connection.read_message(), left)
            except TimeoutError:
                continue
            if raw is None:
                raise Failure("the daemon closed the WebSocket")
            apply(topics, json.loads(raw))
    finally:
        connection.close()


def apply(topics: dict[str, Any], message: dict[str, Any]) -> None:
    """The page's copy of the topics: `state` replaces one, the ops of a `patch` change it."""
    if message.get("type") == "state":
        topics[message["topic"]] = message["value"]
    elif message.get("type") == "patch":
        value = topics.setdefault(message["topic"], {})
        for op in message["ops"]:
            if op["op"] == "replace":
                topics[message["topic"]] = value = op["value"]
            elif op["op"] == "set":
                value[op["key"]] = op["value"]
            else:
                value.pop(op["key"], None)


def stop_gracefully(daemon: subprocess.Popen[bytes], seconds: float) -> int:
    daemon.send_signal(signal.CTRL_BREAK_EVENT if WINDOWS else signal.SIGTERM)       # type: ignore[attr-defined, unused-ignore]
    try:
        return daemon.wait(seconds)
    except subprocess.TimeoutExpired:
        raise Failure(f"the daemon did not end within {seconds:g} s of the stop signal") from None


def check_the_end(data: Path, code: int) -> None:
    if code != 0:
        raise Failure(f"the daemon ended with exit code {code}, not 0")
    last = next((line for line in reversed((data / LOG).read_text(encoding="utf-8", errors="replace").splitlines()) if line.strip()), "")
    if not last.endswith("NeoAPRS ended"):
        raise Failure(f"the last line of the log is {last!r}, not '... NeoAPRS ended'")
    db = sqlite3.connect(data / DATABASE)
    try:
        result = db.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        db.close()
    if result != "ok":
        raise Failure(f"the database's integrity_check says {result!r}")
    say("the daemon ended with exit code 0, 'NeoAPRS ended' is the last line of the log, the database is ok")


def run(args: argparse.Namespace) -> None:
    program = command_line(args.command)
    done = subprocess.run([*program, "--version"], capture_output=True, text=True, timeout=60)
    if done.returncode != 0 or not done.stdout.startswith("NeoAPRS "):
        raise Failure(f"--version: exit code {done.returncode}, {done.stdout.strip() or done.stderr.strip()!r}")
    say(done.stdout.strip())
    folder = Path(tempfile.mkdtemp(prefix="neoaprs-smoke-"))
    data = folder / "data"
    tnc = FakeTnc(Path(args.capture).read_bytes())
    daemon = start_daemon(program, data, tnc)
    try:
        base = wait_for_page(daemon, data, args.timeout)
        say(f"the page is at {base}")
        check_the_page(base)
        check_the_world_map(base)
        state, packets = asyncio.run(watch_the_socket(base, args.timeout))
        say(f"over /ws the TNC is {state} and {packets} packets came")
        code = stop_gracefully(daemon, args.timeout)
        check_the_end(data, code)
    except Failure as e:
        print(f"smoke: FAILED: {e}\n--- the end of the log ---\n{log_tail(data)}\n--- output of the daemon ---\n{(folder / 'daemon.out').read_text(errors='replace')[-2000:]}", file=sys.stderr)
        raise
    finally:
        if daemon.poll() is None:
            daemon.kill()
            daemon.wait()
        tnc.close()
        shutil.rmtree(folder, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test of an installed NeoAPRS: a fake KISS TNC on a TCP port, the daemon started on a temporary data folder, the page and its WebSocket checked, a clean stop.")
    parser.add_argument("--command", metavar="PATH", help="the neoaprs command to test (default: this Python with -m neoaprs)")
    parser.add_argument("--capture", default=str(FIXTURE), metavar="FILE", help="the KISS capture the fake TNC plays; default %(default)s")
    parser.add_argument("--timeout", type=float, default=60.0, metavar="SEC", help="how long each wait may take; default %(default)s")
    args = parser.parse_args()
    try:
        run(args)
    except Failure:
        return 1
    say("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
