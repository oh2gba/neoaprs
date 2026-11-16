#!/usr/bin/env python3
"""The smoke test of an installed NeoAPRS, on any system: a fake KISS TNC on a TCP port plays the capture of a radio, the daemon is started on a data folder of its own with that port, and what a user would see is checked.

The page and one script of it are fetched, the world map that ships with the program is asked for a range, the WebSocket of the page tells that the FM radio (the fake TNC) is connected and that packets came, then the daemon is stopped the way its system stops a program (SIGTERM; Ctrl+Break on
Windows) and must end with exit code 0, a log whose last line is `NeoAPRS ended`, and a database that passes `PRAGMA integrity_check`. Nothing is sent to a radio and nothing leaves the loopback.

  scripts/smoke.py                                  the daemon of this interpreter: python -m neoaprs
  scripts/smoke.py --command VENV/bin/neoaprs        the installed command (VENV\\Scripts\\neoaprs.exe on Windows), as CI runs it against the wheel
Run it with the Python that has neoaprs installed (it uses Tornado's WebSocket client). The other scripts that talk to a daemon's page take its socket and its readers from here (`PageSocket`, `radio_of`,
`heard_on`, `give_radio`): each reads the radios by the topic `radios` and works them by the radio commands. Exit code 0: all is well; 1: the first thing that was not, said on stderr with the end of the daemon's log.
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
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "kiss" / "thd7-2026-10-21.bin"
LOG = "neoaprs.log"
DATABASE = "neoaprs.sqlite"
WINDOWS = sys.platform == "win32"
RADIOS = "radios"                                                                       # the topic of every radio, keyed by its id


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
    env["NEOAPRS_NO_DEVICES"] = "1"                                                        # and opens no device and reaches nothing but this computer, whatever a setting says (neoaprs/nodevices.py)
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
    with urllib.request.urlopen(url, timeout=15) as answer:  # noqa: S310  (the page of the daemon this script started: the http://127.0.0.1 address `wait_for_page` read from its log)
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
    request = urllib.request.Request(base + "basemap-world.pmtiles", headers={"Range": "bytes=0-126"})  # noqa: S310  (the same page: `base` is that http://127.0.0.1 address)
    try:
        with urllib.request.urlopen(request, timeout=15) as answer:  # noqa: S310  (the request made on the line before)
            status, head = answer.status, answer.read()
    except OSError as e:
        raise Failure(f"GET /basemap-world.pmtiles: {e} (the world map is not in the package?)") from None
    if status != 206 or head[:7] != b"PMTiles" or len(head) != 127 or head[101] < 4:
        raise Failure(f"GET /basemap-world.pmtiles answered {status} with {len(head)} bytes that are no PMTiles header to zoom 4")
    say(f"the world map is served (to zoom {head[101]})")


FIRST_RADIO = "kiss"                     # the radio a new installation is given first, as the setup guide gives it: radio 1, the one --port names, the fake TNC


async def watch_the_socket(base: str, seconds: float) -> tuple[str, int]:
    """Opens /ws as the page does, gives the new installation its first radio (FIRST_RADIO, by the radio commands, as the setup guide does: a new installation has none), and waits until it is `connected`
    to the fake TNC of --port and a packet is there; returns the state and the number of packets. The radio is read in the topic `radios`, which the hello must name."""
    page = await PageSocket.open(base)
    try:
        wire = page.wire                                                                # (a hello that names no topic `radios` is a Failure here, before the wait)
        await give_radio(page, "fm", FIRST_RADIO, {}, seconds)
        await page.until(f"the FM radio connected and a packet (the topic {wire})", lambda p: radio_state(p.topics, "fm") == "connected" and bool(p.topics.get("packets")), seconds)
        return "connected", len(page.topics["packets"])
    finally:
        page.close()


def wire_of(hello: dict[str, Any]) -> str:
    """The topic of the radios, `radios`, which the daemon's `hello` must list (the commands that name a radio, the rows' `heard` by radio go with it). A daemon that does not list it is a Failure, never a guess."""
    topics = hello.get("topics") or []
    if RADIOS in topics:
        return RADIOS
    raise Failure(f"the daemon tells of no radio: its hello does not list the topic {RADIOS} ({', '.join(topics) or 'no topic'})")


def live_radios(topics: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """The radios of a kind that are not removed, by position, as the topic `radios` tells them; [] while it is not told."""
    rows = (topics.get(RADIOS) or {}).values()
    return sorted((row for row in rows if row.get("kind") == kind and not row.get("removed")), key=lambda row: (row.get("position", 0), row.get("id", 0)))


def radio_of(topics: dict[str, Any], kind: str) -> dict[str, Any] | None:
    """The radio of a kind as the page holds it: the first enabled one of the topic `radios`; None while there is none or the topic is not told."""
    return next((row for row in live_radios(topics, kind) if row.get("enabled")), None)


def radio_state(topics: dict[str, Any], kind: str) -> str | None:
    """`connected`, `waiting`, ... of the radio of a kind (radio_of); None while it is not told."""
    radio = radio_of(topics, kind)
    return None if radio is None else radio.get("state")


def modem_state(topics: dict[str, Any], kind: str, id: int | None = None) -> str | None:
    """`starting`, `running`, ... of the Mercury modem of a radio: the radio `id` of the topic `radios`, or the radio of a kind (radio_of); None while it has no modem or is not told."""
    radio = (topics.get(RADIOS) or {}).get(str(id)) if id is not None else radio_of(topics, kind)
    return ((radio or {}).get("modem") or {}).get("state")


def heard_on(topics: dict[str, Any], row: dict[str, Any], kind: str) -> int:
    """How many packets of a station's row came on the radios of a kind: its `heard` by radio id, counted for the radios of that kind of the topic `radios`. A row read before the topic `radios` has come counts 0
    (the hello lists the stations first: a radio not yet told is one whose kind is not yet known), as does a radio the row names that `radios` does not yet tell. A row without `heard` is a Failure: the wire
    changed under the script."""
    if "heard" not in row:
        raise Failure(f"the row of {row.get('call')} says nothing of what the {kind} radios heard: it has no heard (by radio)")
    kinds = {str(radio.get("id")): radio.get("kind") for radio in (topics.get(RADIOS) or {}).values()}
    return sum(int((heard or {}).get("count") or 0) for id, heard in (row.get("heard") or {}).items() if kinds.get(str(id)) == kind)


class PageSocket:
    """The page's WebSocket, read as the page reads it: the hello, the topics as the page holds them, the latest status, and every other message (an answer, a refusal) in the order it came. The socket is read
    while something is waited for (`until`); the client answers the daemon's pings by itself meanwhile."""

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
        """Sends a command; the number of messages read before it (what `refusal` looks at after it)."""
        await self.connection.write_message(json.dumps(command))
        return len(self.messages)

    def refusal(self, since: int, *commands: str) -> dict[str, Any] | None:
        """The first `error` that answers one of `commands` among the messages read after `since`."""
        return next((m for m in self.messages[since:] if m.get("type") == "error" and m.get("cmd") in commands), None)

    async def until(self, what: str, condition: Callable[["PageSocket"], bool], seconds: float) -> None:
        """Reads until `condition` holds; Failure when the time is up or the socket closes first, with the refusals the daemon sent."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds
        while not condition(self):
            left = deadline - loop.time()
            if left <= 0:
                refused = [m.get("text") for m in self.messages if m.get("type") == "error"]
                raise Failure(f"{what}: not within {seconds:g} s (the FM radio {radio_state(self.topics, 'fm')!r}, the Mercury radio {radio_state(self.topics, 'hf')!r}, refusals {refused})")
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
        """The settings in force as the topic `config` tells them: its `values`, and a radio's own `radio/<id>/<key>` (and `email/radio`) wherever the daemon tells them, in `values` as breakdown 1.11
        words it or in `radio_values` beside it, which the round's wire keeps apart so that the form of before shows none of them."""
        told = self.topics.get("config") or {}
        return {**(told.get("values") or {}), **(told.get("radio_values") or {})}

    async def set_config(self, values: dict[str, str], seconds: float) -> None:
        """Saves settings as the settings form does, and waits until the topic `config` has them; a refusal is a Failure with the daemon's words."""
        since = await self.send({"cmd": "set_config", "values": values})
        await self.until(f"the settings {', '.join(values)} saved", lambda p: p.refusal(since, "set_config") is not None or all(p.config().get(k) == v for k, v in values.items()), seconds)
        if refused := self.refusal(since, "set_config"):
            raise Failure(f"set_config was refused: {refused.get('text')}")

    def close(self) -> None:
        self.connection.close()


async def give_radio(page: PageSocket, kind: str, radio_type: str, values: dict[str, str], seconds: float) -> int:
    """Makes the first radio of a kind one of `radio_type`, enabled, with its own `values` (by the radio's keys: `keying`, `sound_card` ...), the way the page does it: the radio commands (`radio_add` when the
    station has no radio of the kind, `radio_change`) and `radio/<id>/<key>` in `set_config`. Waits until the daemon tells it so; a refusal is a Failure. The radio's id."""
    await page.until(f"the settings and the radios told (the topic {page.wire})", lambda p: "config" in p.topics and RADIOS in p.topics, seconds)      # (a hello without it is a Failure, before the wait)
    radio = next(iter(live_radios(page.topics, kind)), None)
    if radio is None:
        since = await page.send({"cmd": "radio_add", "type": radio_type})
        await page.until(f"a {radio_type} radio added", lambda p: p.refusal(since, "radio_add") is not None or any(m.get("type") == "radio_added" for m in p.messages[since:]), seconds)
        if refused := page.refusal(since, "radio_add"):
            raise Failure(f"radio_add was refused: {refused.get('text')}")
        added = next(m for m in page.messages[since:] if m.get("type") == "radio_added")["id"]
        await page.until(f"radio {added} told", lambda p: str(added) in (p.topics.get(RADIOS) or {}), seconds)
        radio = page.topics[RADIOS][str(added)]
    id = radio["id"]
    change = {key: value for key, value in (("type", radio_type), ("enabled", True)) if radio.get(key) != value}
    if change:
        since = await page.send({"cmd": "radio_change", "radio": id, **change})
        await page.until(f"radio {id} made {change}", lambda p: p.refusal(since, "radio_change") is not None or all(((p.topics.get(RADIOS) or {}).get(str(id)) or {}).get(k) == v for k, v in change.items()), seconds)
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
        say(f"over /ws the FM radio is {state} and {packets} packets came")
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
