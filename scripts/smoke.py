#!/usr/bin/env python3
"""Smoke test of an installed NeoAPRS: a fake KISS TNC feeds a daemon, which is then checked.

scripts/smoke.py                          the daemon of this interpreter: python -m neoaprs
scripts/smoke.py --command VENV/bin/neoaprs    the installed command (as CI runs it)"""

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
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "kiss" / "thd7-2026-10-21.bin"
LOG = "neoaprs.log"
DATABASE = "neoaprs.sqlite"
WINDOWS = sys.platform == "win32"
# The topic of every radio, keyed by its id.
RADIOS = "radios"


class Failure(Exception):
    """What was not as it should be."""


class FakeTnc:
    """A KISS TNC on the loopback: each client is sent the capture; what it writes is discarded."""

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
        """Play the capture shortly after connection and again every few seconds.

        A daemon discards what is waiting when it opens a line; a slow runner may be past that."""
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
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0  # type: ignore[attr-defined, unused-ignore]  (Ctrl+Break reaches this child only)
    env = {k: v for k, v in os.environ.items() if k not in ("NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG")}
    # The daemon has a radio (--port), searches no serial port and does not ask the version page.
    env.setdefault("NEOAPRS_SERIAL_PATTERN", "/dev/neoaprs-smoke-no-such-port*")
    env["NEOAPRS_UPDATE_CHECK"] = "0"
    # No device is opened and nothing but this computer is reached (neoaprs/nodevices.py).
    env["NEOAPRS_NO_DEVICES"] = "1"
    return subprocess.Popen(
        [*program, "--data", str(data), "--port", tnc.url, "--web-port", "0"],
        stdin=subprocess.DEVNULL,
        stdout=out,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=flags,
    )


def wait_for_page(daemon: subprocess.Popen[bytes], data: Path, seconds: float) -> str:
    """The address the log says the page is at."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if daemon.poll() is not None:
            raise Failure(f"the daemon ended with exit code {daemon.returncode} before the page was up")
        try:
            found = re.search(
                r"web page at (http://127\.0\.0\.1:\d+/)", (data / LOG).read_text(encoding="utf-8", errors="replace")
            )
        except OSError:
            found = None
        if found:
            return found.group(1)
        time.sleep(0.1)
    raise Failure(f"no 'web page at' line in the log within {seconds:g} s")


def fetch(url: str) -> tuple[int, Any, bytes]:
    with urllib.request.urlopen(url, timeout=15) as answer:  # noqa: S310  (the loopback page of the daemon this script started)
        return answer.status, answer.headers, answer.read()


def check_the_page(base: str) -> None:
    status, headers, body = fetch(base)
    html = body.decode("utf-8", errors="replace")
    if status != 200 or '<div id="app"' not in html:
        raise Failure(
            f'GET / answered {status} and the page has no <div id="app"> (the built page is not in the package?)'
        )
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
    """Check that the shipped world map is served from a data folder that has none."""
    request = urllib.request.Request(base + "basemap-world.pmtiles", headers={"Range": "bytes=0-126"})  # noqa: S310  (the same loopback page)
    try:
        with urllib.request.urlopen(request, timeout=15) as answer:  # noqa: S310  (the request made on the line before)
            status, head = answer.status, answer.read()
    except OSError as e:
        raise Failure(f"GET /basemap-world.pmtiles: {e} (the world map is not in the package?)") from None
    if status != 206 or head[:7] != b"PMTiles" or len(head) != 127 or head[101] < 4:
        raise Failure(
            f"GET /basemap-world.pmtiles answered {status} with {len(head)} bytes that are no PMTiles header to zoom 4"
        )
    say(f"the world map is served (to zoom {head[101]})")


# The radio a new installation is given first, as the setup guide does: radio 1, the fake TNC.
FIRST_RADIO = "kiss"


async def watch_the_socket(base: str, seconds: float) -> tuple[str, int]:
    """Open /ws, give the new installation its first radio, and wait until it is `connected` and a
    packet is there; return the state and the packet count. The hello must name `radios`."""
    page = await PageSocket.open(base)
    try:
        # A hello that names no topic `radios` is a Failure here, before the wait.
        wire = page.wire
        await give_radio(page, "fm", FIRST_RADIO, {}, seconds)
        await page.until(
            f"the FM radio connected and a packet (the topic {wire})",
            lambda p: radio_state(p.topics, "fm") == "connected" and bool(p.topics.get("packets")),
            seconds,
        )
        return "connected", len(page.topics["packets"])
    finally:
        page.close()


def wire_of(hello: dict[str, Any]) -> str:
    """Return the topic `radios`, which the daemon's `hello` must list; otherwise a Failure."""
    topics = hello.get("topics") or []
    if RADIOS in topics:
        return RADIOS
    raise Failure(
        f"the daemon tells of no radio: its hello does not list the topic {RADIOS} ({', '.join(topics) or 'no topic'})"
    )


def live_radios(topics: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """Return the radios of a kind that are not removed, by position; [] until the topic is told."""
    rows = (topics.get(RADIOS) or {}).values()
    return sorted(
        (row for row in rows if row.get("kind") == kind and not row.get("removed")),
        key=lambda row: (row.get("position", 0), row.get("id", 0)),
    )


def radio_of(topics: dict[str, Any], kind: str) -> dict[str, Any] | None:
    """Return the first enabled radio of a kind from the topic `radios`, or None."""
    return next((row for row in live_radios(topics, kind) if row.get("enabled")), None)


def radio_state(topics: dict[str, Any], kind: str) -> str | None:
    """`connected`, `waiting`, ... of the radio of a kind (radio_of); None while it is not told."""
    radio = radio_of(topics, kind)
    return None if radio is None else radio.get("state")


def modem_state(topics: dict[str, Any], kind: str, id: int | None = None) -> str | None:
    """Return the state (`starting`, `running`, ...) of a radio's Mercury modem, or None."""
    radio = (topics.get(RADIOS) or {}).get(str(id)) if id is not None else radio_of(topics, kind)
    return ((radio or {}).get("modem") or {}).get("state")


def heard_on(topics: dict[str, Any], row: dict[str, Any], kind: str) -> int:
    """Return how many packets of a station's row came on radios of a kind (`heard` by radio id).

    A radio not yet told counts 0; a row without `heard` is a Failure."""
    if "heard" not in row:
        raise Failure(
            f"the row of {row.get('call')} says nothing of what the {kind} radios heard: it has no heard (by radio)"
        )
    kinds = {str(radio.get("id")): radio.get("kind") for radio in (topics.get(RADIOS) or {}).values()}
    return sum(
        int((heard or {}).get("count") or 0)
        for id, heard in (row.get("heard") or {}).items()
        if kinds.get(str(id)) == kind
    )


class PageSocket:
    """The page's WebSocket, read as the page reads it: the hello, the topics, the status and other
    messages in order. It is read only inside `until`; the client answers pings itself."""

    def __init__(self, connection: Any, hello: dict[str, Any]) -> None:
        self.connection, self.hello = connection, hello
        self.topics: dict[str, Any] = {}
        self.status: dict[str, Any] = {}
        self.messages: list[dict[str, Any]] = []

    @classmethod
    async def open(cls, base: str, seconds: float = 15.0) -> "PageSocket":
        """The socket of the page at `base` (`http://127.0.0.1:PORT/`), its hello read."""
        from tornado.websocket import websocket_connect

        connection = await websocket_connect("ws://" + base.removeprefix("http://") + "ws", connect_timeout=seconds)
        raw = await asyncio.wait_for(connection.read_message(), seconds)
        hello = json.loads(raw) if raw is not None else {}
        if hello.get("type") != "hello":
            connection.close()
            raise Failure(f"the first message of the socket is not hello: {raw!r}")
        return cls(connection, hello)

    @property
    def wire(self) -> str:
        return wire_of(self.hello)

    async def send(self, command: dict[str, Any]) -> int:
        """Send a command; return the number of messages read before it (see `refusal`)."""
        await self.connection.write_message(json.dumps(command))
        return len(self.messages)

    def refusal(self, since: int, *commands: str) -> dict[str, Any] | None:
        """Return the first `error` answering one of `commands` after message `since`."""
        return next((m for m in self.messages[since:] if m.get("type") == "error" and m.get("cmd") in commands), None)

    async def until(self, what: str, condition: Callable[["PageSocket"], bool], seconds: float) -> None:
        """Read until `condition` holds; Failure if time is up or the socket closes first."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds
        while not condition(self):
            left = deadline - loop.time()
            if left <= 0:
                refused = [m.get("text") for m in self.messages if m.get("type") == "error"]
                raise Failure(
                    f"{what}: not within {seconds:g} s (the FM radio {radio_state(self.topics, 'fm')!r}, the Mercury radio {radio_state(self.topics, 'hf')!r}, refusals {refused})"
                )
            try:
                raw = await asyncio.wait_for(self.connection.read_message(), min(left, 1.0))
            except TimeoutError:
                continue
            if raw is None:
                raise Failure(f"{what}: the daemon closed the socket first")
            message = json.loads(raw)
            if message.get("type") in ("state", "patch"):
                apply(self.topics, message)
            elif message.get("type") == "status":
                self.status = message
            else:
                self.messages.append(message)

    def config(self) -> dict[str, str]:
        """Return the settings in force from the topic `config`: `values`, plus a radio's own
        `radio/<id>/<key>` from `values` or from `radio_values`."""
        told = self.topics.get("config") or {}
        return {**(told.get("values") or {}), **(told.get("radio_values") or {})}

    async def set_config(self, values: dict[str, str], seconds: float) -> None:
        """Save settings as the settings form does and wait until `config` has them."""
        since = await self.send({"cmd": "set_config", "values": values})
        await self.until(
            f"the settings {', '.join(values)} saved",
            lambda p: (
                p.refusal(since, "set_config") is not None or all(p.config().get(k) == v for k, v in values.items())
            ),
            seconds,
        )
        if refused := self.refusal(since, "set_config"):
            raise Failure(f"set_config was refused: {refused.get('text')}")

    def close(self) -> None:
        self.connection.close()


async def give_radio(page: PageSocket, kind: str, radio_type: str, values: dict[str, str], seconds: float) -> int:
    """Make the first radio of a kind a `radio_type`, enabled, with `values`, as the page does.

    Waits until the daemon says so; a refusal is a Failure. Return the radio's id."""
    # A hello without it is a Failure, before the wait.
    await page.until(
        f"the settings and the radios told (the topic {page.wire})",
        lambda p: "config" in p.topics and RADIOS in p.topics,
        seconds,
    )
    radio = next(iter(live_radios(page.topics, kind)), None)
    if radio is None:
        since = await page.send({"cmd": "radio_add", "type": radio_type})
        await page.until(
            f"a {radio_type} radio added",
            lambda p: (
                p.refusal(since, "radio_add") is not None
                or any(m.get("type") == "radio_added" for m in p.messages[since:])
            ),
            seconds,
        )
        if refused := page.refusal(since, "radio_add"):
            raise Failure(f"radio_add was refused: {refused.get('text')}")
        added = next(m for m in page.messages[since:] if m.get("type") == "radio_added")["id"]
        await page.until(f"radio {added} told", lambda p: str(added) in (p.topics.get(RADIOS) or {}), seconds)
        radio = page.topics[RADIOS][str(added)]
    id = radio["id"]
    change = {key: value for key, value in (("type", radio_type), ("enabled", True)) if radio.get(key) != value}
    if change:
        since = await page.send({"cmd": "radio_change", "radio": id, **change})
        await page.until(
            f"radio {id} made {change}",
            lambda p: (
                p.refusal(since, "radio_change") is not None
                or all(((p.topics.get(RADIOS) or {}).get(str(id)) or {}).get(k) == v for k, v in change.items())
            ),
            seconds,
        )
        if refused := page.refusal(since, "radio_change"):
            raise Failure(f"radio_change was refused: {refused.get('text')}")
    if values:
        await page.set_config({f"radio/{id}/{key}": value for key, value in values.items()}, seconds)
    return int(id)


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
    daemon.send_signal(signal.CTRL_BREAK_EVENT if WINDOWS else signal.SIGTERM)  # type: ignore[attr-defined, unused-ignore]
    try:
        return daemon.wait(seconds)
    except subprocess.TimeoutExpired:
        raise Failure(f"the daemon did not end within {seconds:g} s of the stop signal") from None


def check_the_end(data: Path, code: int) -> None:
    if code != 0:
        raise Failure(f"the daemon ended with exit code {code}, not 0")
    last = next(
        (
            line
            for line in reversed((data / LOG).read_text(encoding="utf-8", errors="replace").splitlines())
            if line.strip()
        ),
        "",
    )
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
        say(f"over /ws the FM radio is {state} and {packets} packets came")
        code = stop_gracefully(daemon, args.timeout)
        check_the_end(data, code)
    except Failure as e:
        print(
            f"smoke: FAILED: {e}\n--- the end of the log ---\n{log_tail(data)}\n--- output of the daemon ---\n{(folder / 'daemon.out').read_text(errors='replace')[-2000:]}",
            file=sys.stderr,
        )
        raise
    finally:
        if daemon.poll() is None:
            daemon.kill()
            daemon.wait()
        tnc.close()
        shutil.rmtree(folder, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test of an installed NeoAPRS: a fake KISS TNC on a TCP port, the daemon started on a temporary data folder, the page and its WebSocket checked, a clean stop."
    )
    parser.add_argument(
        "--command", metavar="PATH", help="the neoaprs command to test (default: this Python with -m neoaprs)"
    )
    parser.add_argument(
        "--capture",
        default=str(FIXTURE),
        metavar="FILE",
        help="the KISS capture the fake TNC plays; default %(default)s",
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0, metavar="SEC", help="how long each wait may take; default %(default)s"
    )
    args = parser.parse_args()
    try:
        run(args)
    except Failure:
        return 1
    say("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
