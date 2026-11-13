#!/usr/bin/env python3
"""What the upgrade check of scripts/check-installs asks of an installed NeoAPRS, inside its container: the daemon of the OLD release is given something to keep, and the daemon of the NEW build, installed over it, must
have all of it. Run with the Python that has neoaprs installed (/opt/neoaprs/bin/python3 -I for a .deb: it uses Tornado's WebSocket client), next to scripts/smoke.py, whose fake TNC and start of a daemon it uses.

  install-probe.py seed   --command PROGRAM --data FOLDER --out FILE   starts the daemon on FOLDER with a fake KISS TNC (the FM radio) and the settings of a station with an HF radio (the Dummy HF radio: both radios
                                                                      are on), waits until stations are heard, sends one message, writes what it saw to FILE and stops the daemon the way a service manager does
  install-probe.py verify --command PROGRAM --data FOLDER --in FILE --version V   starts the daemon of PROGRAM on the same FOLDER and must find every station, the message and the settings of FILE, the version V
                                                                      in its hello, and a clean stop (exit code 0, `NeoAPRS ended`, a database that passes its integrity check)

Only what the page's WebSocket has told since the first release of the two radios is used: the topics `stations`, `messages` and `config`, the commands `set_config` and `send_message`, and the `hello` of a connection.
Nothing is sent to a radio (the Dummy radio makes its traffic up, and the daemon is started with NEOAPRS_NO_DEVICES) and nothing leaves the loopback. Exit code 0: all is well; 1: the first thing that was not."""
import argparse
import asyncio
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from collections.abc import Callable
from typing import Any



def load_smoke() -> ModuleType:
    """scripts/smoke.py, next to this file, as a module: the fake TNC and the start and stop of a daemon. (Run with -I, as the .deb's Python is, the folder of the script is not on the path.)"""
    path = Path(__file__).resolve().with_name("smoke.py")
    spec = importlib.util.spec_from_file_location("smoke", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["smoke"] = module
    spec.loader.exec_module(module)
    return module


smoke = load_smoke()

SETTINGS = {"station/call": "OH2TST", "hf/enabled": "true", "hf/profile": "dummy-hf"}      # a station with both radios: the FM radio is the fake TNC given by --port
MESSAGE_TO, MESSAGE_TEXT = "OH2XYZ", "kept over the upgrade"


class Seen:
    """What a connection to the page's WebSocket has told: the hello, and the topics as the page keeps them."""

    def __init__(self) -> None:
        self.hello: dict[str, Any] = {}
        self.topics: dict[str, Any] = {}
        self.errors: list[str] = []


async def follow(base: str, ready: Callable[[Seen], bool], seconds: float, send: list[tuple[Callable[[Seen], bool], dict[str, Any]]] | None = None) -> Seen:
    """Opens /ws as the page does and reads until `ready(seen)` says all is there or the time is up. Each of `send` is a command with the condition that must hold before it is sent: the next one waits for the last one's answer."""
    from tornado.websocket import websocket_connect
    seen = Seen()
    connection = await websocket_connect("ws://" + base.removeprefix("http://") + "ws", connect_timeout=15)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    commands = list(send or [])
    try:
        while True:
            if commands and "config" in seen.topics and commands[0][0](seen):
                await connection.write_message(json.dumps(commands.pop(0)[1]))
            if ready(seen) and not commands:
                return seen
            left = deadline - loop.time()
            if left <= 0:
                raise smoke.Failure(f"within {seconds:g} s the page was not told what was waited for (settings {has_settings(seen)}, message {has_message(seen)}, {len(stations_of(seen))} stations, the TNC {(seen.topics.get('tnc') or {}).get('state')!r}, errors {seen.errors})")
            try:
                raw = await asyncio.wait_for(connection.read_message(), min(left, 1.0))
            except TimeoutError:
                continue
            if raw is None:
                raise smoke.Failure("the daemon closed the WebSocket")
            message = json.loads(raw)
            if message.get("type") == "hello":
                seen.hello = message
            elif message.get("type") == "error":
                seen.errors.append(str(message.get("text")))
            else:
                smoke.apply(seen.topics, message)
    finally:
        connection.close()


def wait_for_page(daemon: "subprocess.Popen[bytes]", log: Path, offset: int, seconds: float) -> str:
    """The address this daemon says its page is at: the first line of the log, from `offset` on, that says so."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if daemon.poll() is not None:
            raise smoke.Failure(f"the daemon ended with exit code {daemon.returncode} before the page was up")
        try:
            found = re.search(r"web page at (http://127\.0\.0\.1:\d+/)", log.read_bytes()[offset:].decode("utf-8", errors="replace"))
        except OSError:
            found = None
        if found:
            return found.group(1)
        time.sleep(0.1)
    raise smoke.Failure(f"no 'web page at' line in the log within {seconds:g} s")


def has_message(seen: Seen) -> bool:
    return any(row.get("text") == MESSAGE_TEXT for row in (seen.topics.get("messages") or {}).values())


def has_settings(seen: Seen) -> bool:
    config = (seen.topics.get("config") or {}).get("values") or {}
    return all(config.get(key) == value for key, value in SETTINGS.items())


def stations_of(seen: Seen) -> list[str]:
    return sorted(seen.topics.get("stations") or {})


def seed_ready(seen: Seen) -> bool:
    return has_settings(seen) and has_message(seen) and bool(stations_of(seen)) and (seen.topics.get("tnc") or {}).get("state") == "connected"


def run_with_daemon(args: argparse.Namespace, work: Any) -> None:
    """The daemon of --command on --data with a fake TNC: `work(base)` is what is done while it runs; then the stop and the checks of the end."""
    program = [args.command]
    data = Path(args.data)
    tnc = smoke.FakeTnc(Path(args.capture).read_bytes())
    log = data / smoke.LOG
    before = log.stat().st_size if log.exists() else 0                  # (the log of the first daemon is in the folder: its page address is not the one of this daemon)
    daemon = smoke.start_daemon(program, data, tnc)
    try:
        base = wait_for_page(daemon, log, before, args.timeout)
        work(base)
        smoke.check_the_end(data, smoke.stop_gracefully(daemon, args.timeout))
    except smoke.Failure as error:
        print(f"install-probe: FAILED: {error}\n--- the end of the log ---\n{smoke.log_tail(data)}", file=sys.stderr)
        raise
    finally:
        if daemon.poll() is None:
            daemon.kill()
            daemon.wait()
        tnc.close()


def seed(args: argparse.Namespace) -> None:
    def work(base: str) -> None:
        commands = [(lambda seen: True, {"cmd": "set_config", "values": SETTINGS}), (has_settings, {"cmd": "send_message", "to": MESSAGE_TO, "text": MESSAGE_TEXT})]
        seen = asyncio.run(follow(base, seed_ready, args.timeout, commands))
        stations = stations_of(seen)
        Path(args.out).write_text(json.dumps({"stations": stations, "message": MESSAGE_TEXT, "settings": SETTINGS, "from_version": seen.hello.get("version")}), encoding="utf-8")
        smoke.say(f"the old daemon ({seen.hello.get('version')}) has {len(stations)} stations, one message and both radios set")
    run_with_daemon(args, work)


def verify(args: argparse.Namespace) -> None:
    expected = json.loads(Path(args.input).read_text(encoding="utf-8"))

    def work(base: str) -> None:
        seen = asyncio.run(follow(base, lambda each: bool(each.hello) and has_message(each) and has_settings(each) and bool(stations_of(each)), args.timeout))
        version = seen.hello.get("version")
        if version != args.version:
            raise smoke.Failure(f"the daemon says it is {version!r}, not {args.version!r}: the old program is still the one that runs")
        missing = sorted(set(expected["stations"]) - set(stations_of(seen)))
        if missing:
            raise smoke.Failure(f"stations of the old daemon are gone: {', '.join(missing)}")
        smoke.say(f"the new daemon ({version}) has the {len(expected['stations'])} stations, the message and the settings of {expected['from_version']}")
    run_with_daemon(args, work)


def main() -> int:
    parser = argparse.ArgumentParser(description="What the upgrade check asks of an installed NeoAPRS: seed the old daemon's data, verify the new one's.")
    parser.add_argument("action", choices=["seed", "verify"])
    parser.add_argument("--command", required=True, metavar="PATH", help="the neoaprs command")
    parser.add_argument("--data", required=True, metavar="FOLDER", help="the data folder of the daemon (the same for both)")
    parser.add_argument("--out", metavar="FILE", help="seed: where what the old daemon has is written")
    parser.add_argument("--in", dest="input", metavar="FILE", help="verify: what seed wrote")
    parser.add_argument("--version", metavar="V", help="verify: the version the new daemon must say")
    parser.add_argument("--capture", default=str(smoke.FIXTURE), metavar="FILE", help="the KISS capture the fake TNC plays; default %(default)s")
    parser.add_argument("--timeout", type=float, default=90.0, metavar="SEC", help="how long each wait may take; default %(default)s")
    args = parser.parse_args()
    if (args.action == "seed" and not args.out) or (args.action == "verify" and not (args.input and args.version)):
        parser.error("seed needs --out, verify needs --in and --version")
    try:
        (seed if args.action == "seed" else verify)(args)
    except smoke.Failure:
        return 1
    smoke.say("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
