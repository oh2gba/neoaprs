#!/usr/bin/env python3
"""What the upgrade check of scripts/check-installs asks of an installed NeoAPRS, in its container.

install-probe.py seed   --command PROGRAM --data FOLDER --out FILE
install-probe.py verify --command PROGRAM --data FOLDER --in FILE --version V"""

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
from collections.abc import Awaitable, Callable
from typing import Any


def load_smoke() -> ModuleType:
    """Load scripts/smoke.py as a module; with -I the script's folder is not on the path."""
    path = Path(__file__).resolve().with_name("smoke.py")
    spec = importlib.util.spec_from_file_location("smoke", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["smoke"] = module
    spec.loader.exec_module(module)
    return module


smoke = load_smoke()

# The station's own settings; its radios are handled below.
SETTINGS = {"station/call": "OH2TST"}
# A station with both radios: the FM radio is the fake TNC of --port, the HF radio the Dummy.
HF_TYPE = "dummy-hf"
MESSAGE_TO, MESSAGE_TEXT = "OH2XYZ", "kept over the upgrade"
# A current release is given the FM radio first (a new installation has none): radio 1, --port.
FM_TYPE = "kiss"


class OldRelease:
    """A release before separate radios: its FM radio is on from the start (topic `tnc`), its HF
    radio is the settings `hf/enabled` and `hf/profile`."""

    TOPIC = "tnc"
    HF_SETTINGS = {"hf/enabled": "true", "hf/profile": HF_TYPE}

    @staticmethod
    def is_one(hello: dict[str, Any]) -> bool:
        """Whether the daemon of this hello is such a release: it lists no topic `radios`."""
        return smoke.RADIOS not in (hello.get("topics") or [])

    @staticmethod
    def fm_state(topics: dict[str, Any]) -> str | None:
        return (topics.get(OldRelease.TOPIC) or {}).get("state")

    @staticmethod
    def has_hf(config: dict[str, str]) -> bool:
        return all(config.get(key) == value for key, value in OldRelease.HF_SETTINGS.items())


class Seen:
    """What a page WebSocket connection has told: the hello and the topics."""

    def __init__(self, page: "smoke.PageSocket") -> None:
        self.hello, self.topics = page.hello, page.topics
        self.errors = [str(m.get("text")) for m in page.messages if m.get("type") == "error"]


async def follow(
    base: str,
    ready: Callable[[Seen], bool],
    seconds: float,
    work: Callable[["smoke.PageSocket"], Awaitable[None]] | None = None,
) -> Seen:
    """Open /ws as the page does, run `work` on it, and read until `ready(seen)` or the time is
    up."""
    page = await smoke.PageSocket.open(base)
    try:
        if work is not None:
            await work(page)
        try:
            await page.until("what was waited for", lambda p: ready(Seen(p)), seconds)
        except smoke.Failure:
            seen = Seen(page)
            raise smoke.Failure(
                f"within {seconds:g} s the page was not told what was waited for (settings {has_settings(seen)}, message {has_message(seen)}, {len(stations_of(seen))} stations, "
                f"the FM radio {fm_state(seen)!r}, errors {seen.errors})"
            ) from None
        return Seen(page)
    finally:
        page.close()


def wait_for_page(daemon: "subprocess.Popen[bytes]", log: Path, offset: int, seconds: float) -> str:
    """Return the page address the daemon logged, from `offset` on."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if daemon.poll() is not None:
            raise smoke.Failure(f"the daemon ended with exit code {daemon.returncode} before the page was up")
        try:
            found = re.search(
                r"web page at (http://127\.0\.0\.1:\d+/)", log.read_bytes()[offset:].decode("utf-8", errors="replace")
            )
        except OSError:
            found = None
        if found:
            return found.group(1)
        time.sleep(0.1)
    raise smoke.Failure(f"no 'web page at' line in the log within {seconds:g} s")


def has_message(seen: Seen) -> bool:
    return any(row.get("text") == MESSAGE_TEXT for row in (seen.topics.get("messages") or {}).values())


def has_settings(seen: Seen) -> bool:
    """Return whether the station's settings and its HF radio are there (the topic `radios`)."""
    config = (seen.topics.get("config") or {}).get("values") or {}
    if not all(config.get(key) == value for key, value in SETTINGS.items()):
        return False
    if OldRelease.is_one(seen.hello):
        return OldRelease.has_hf(config)
    return any(radio.get("type") == HF_TYPE and radio.get("enabled") for radio in smoke.live_radios(seen.topics, "hf"))


def fm_state(seen: Seen) -> str | None:
    """Return the FM radio's state (`connected`, `waiting`, ...) from the topic `radios`."""
    return OldRelease.fm_state(seen.topics) if OldRelease.is_one(seen.hello) else smoke.radio_state(seen.topics, "fm")


def stations_of(seen: Seen) -> list[str]:
    return sorted(seen.topics.get("stations") or {})


def seed_ready(seen: Seen) -> bool:
    return has_settings(seen) and has_message(seen) and bool(stations_of(seen)) and fm_state(seen) == "connected"


def run_with_daemon(args: argparse.Namespace, work: Any) -> None:
    """Run the daemon of --command on --data with a fake TNC, call `work(base)`, then stop and
    check."""
    program = [args.command]
    data = Path(args.data)
    tnc = smoke.FakeTnc(Path(args.capture).read_bytes())
    log = data / smoke.LOG
    # The folder holds the first daemon's log, whose page address is not this one's.
    before = log.stat().st_size if log.exists() else 0
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


async def give_radios(page: "smoke.PageSocket", seconds: float) -> None:
    """Turn both radios on: by settings on an old release, else by radio commands."""
    if OldRelease.is_one(page.hello):
        await page.set_config(OldRelease.HF_SETTINGS, seconds)
        return
    await smoke.give_radio(page, "fm", FM_TYPE, {}, seconds)
    await smoke.give_radio(page, "hf", HF_TYPE, {}, seconds)


async def seed_commands(page: "smoke.PageSocket", seconds: float) -> None:
    """Return what the seed asks of the old daemon: settings, both radios and one message."""
    await page.until("the settings told", lambda p: "config" in p.topics, seconds)
    await page.set_config(SETTINGS, seconds)
    await give_radios(page, seconds)
    await page.send({"cmd": "send_message", "to": MESSAGE_TO, "text": MESSAGE_TEXT})


def seed(args: argparse.Namespace) -> None:
    def work(base: str) -> None:
        seen = asyncio.run(follow(base, seed_ready, args.timeout, lambda page: seed_commands(page, args.timeout)))
        stations = stations_of(seen)
        Path(args.out).write_text(
            json.dumps(
                {
                    "stations": stations,
                    "message": MESSAGE_TEXT,
                    "settings": SETTINGS,
                    "hf_radio": HF_TYPE,
                    "from_version": seen.hello.get("version"),
                }
            ),
            encoding="utf-8",
        )
        smoke.say(
            f"the old daemon ({seen.hello.get('version')}) has {len(stations)} stations, one message and both radios set"
        )

    run_with_daemon(args, work)


def verify(args: argparse.Namespace) -> None:
    expected = json.loads(Path(args.input).read_text(encoding="utf-8"))

    def work(base: str) -> None:
        seen = asyncio.run(
            follow(
                base,
                lambda each: bool(each.hello) and has_message(each) and has_settings(each) and bool(stations_of(each)),
                args.timeout,
            )
        )
        version = seen.hello.get("version")
        if version != args.version:
            raise smoke.Failure(
                f"the daemon says it is {version!r}, not {args.version!r}: the old program is still the one that runs"
            )
        missing = sorted(set(expected["stations"]) - set(stations_of(seen)))
        if missing:
            raise smoke.Failure(f"stations of the old daemon are gone: {', '.join(missing)}")
        smoke.say(
            f"the new daemon ({version}) has the {len(expected['stations'])} stations, the message and the settings of {expected['from_version']}"
        )

    run_with_daemon(args, work)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="What the upgrade check asks of an installed NeoAPRS: seed the old daemon's data, verify the new one's."
    )
    parser.add_argument("action", choices=["seed", "verify"])
    parser.add_argument("--command", required=True, metavar="PATH", help="the neoaprs command")
    parser.add_argument(
        "--data", required=True, metavar="FOLDER", help="the data folder of the daemon (the same for both)"
    )
    parser.add_argument("--out", metavar="FILE", help="seed: where what the old daemon has is written")
    parser.add_argument("--in", dest="input", metavar="FILE", help="verify: what seed wrote")
    parser.add_argument("--version", metavar="V", help="verify: the version the new daemon must say")
    parser.add_argument(
        "--capture",
        default=str(smoke.FIXTURE),
        metavar="FILE",
        help="the KISS capture the fake TNC plays; default %(default)s",
    )
    parser.add_argument(
        "--timeout", type=float, default=90.0, metavar="SEC", help="how long each wait may take; default %(default)s"
    )
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
