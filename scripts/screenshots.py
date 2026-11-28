"""Take the screenshots of the README and the project page (site/) from a made-up day on the air.

    uv run --with playwright --with pillow python scripts/screenshots.py
        everything: every shot light and dark into site/shots/ with thumbnails and WebP copies,
        og.png, eight of them into docs/screenshots/, and the sizes site/index.html declares
    ... scripts/screenshots.py --only map weather
        these shots, with thumbnails and WebP copies (og.png too with map)
    python scripts/screenshots.py --chromium /path/to/chrome --no-sandbox
        a browser Playwright did not install, or one that cannot make its sandbox
    python scripts/screenshots.py --check
        no browser: every shot has its files and every site/ picture its file's size

Nothing touches a radio: they are Dummy ones. The street-level map comes from the PMTiles file
named by `--basemap` (default `data/basemap.pmtiles`); a full run refuses to start without it. Needs
Playwright (`playwright install chromium`), Pillow and `uv sync`. At the end the run says what
it did not write and why; a run with no --only that leaves anything exits 1."""

import argparse
import asyncio
import base64
import io
import json
import logging
import os
import random
import re
import secrets
import shutil
import signal
import socket
import subprocess
import struct
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ICON = ROOT / "neoaprs" / "desktop" / "icon.png"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import demoscene  # noqa: E402  (the scene needs the path above)
import demotraffic  # noqa: E402  (the made-up aircraft and ships of the layers shot)
import demoships  # noqa: E402  (its receiver's port)
from neoaprs import VERSION  # noqa: E402
from neoaprs.controller import Controller  # noqa: E402
from neoaprs.mercury import SUGGESTED  # noqa: E402
from neoaprs.mercuryscope import (  # noqa: E402
    HISTORY_HEADER,
    HISTORY_ROW,
    MODEM_BINS,
    MODEM_RATE,
    ROW_BINS,
    ROW_FIRST_BIN,
    SIGNAL_HI_HZ,
    SIGNAL_LO_HZ,
    KeptRow,
    ScopeRow,
    byte_of_db,
    history_frame,
    row_frame,
)
from neoaprs.web.scopefeed import radio_header  # noqa: E402

DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}
TABLET = {"width": 1024, "height": 768}
LIMIT_KB = 480
README_SHOTS = ("map", "weather", "messages", "beacon", "objects", "bulletins", "setup", "layers")
SETTINGS = {
    "station/call": "OH2GBA",
    "station/lat": f"{demoscene.HOME[0]}",
    "station/lon": f"{demoscene.HOME[1]}",
    "station/symbol_table": "/",
    "station/symbol_code": "-",
    "station/comment": "NeoAPRS in Espoo",
    "beacon/power_w": "5",
    "beacon/antenna_height_m": "10",
    "beacon/antenna_gain_db": "3",
    "messages/alert": "false",
    "radio/1/tcp_host": demoscene.HOST,
}
RADIO_TYPE = "kiss-tcp"
DAY_RADIO = demoscene.DEMO_RADIO
RADIOS: tuple[tuple[str, str, str], ...] = (
    ("fm", "dummy", "2 m"),
    ("hf", "dummy-hf", "40 m"),
    ("lora", "dummy-lora", ""),
)
# The station of the shots, in the order of their boxes: (kind, type, name). Every type is a
# Dummy one that opens no device, never Mercury or Direwolf (they start a modem on the sound card).
LABELS = {"fm": "2 m", "hf": "40 m", "lora": "LoRa"}
FORBIDDEN_TYPES = ("mercury", "mercury-own", "direwolf", "direwolf-300")  # the types no shot may use
# The day is played without the alert command, the beacon timer and the status; the page's
# daemon starts them.
AFTER_THE_DAY = {
    "beacon/interval_min": "30",
    "station/status": "145.500MHz QRV",
    "messages/alert": "true",
    "web/network": "true",
}
GPSD_PORT = 2947
# What the Settings shot shows as the access key and the phone-code address; the daemon's own
# key is random and never shown.
SHOWN_KEY = "k7m2-x9pq-4hrt"
SHOWN_URL = "http://192.168.1.20:7303/"
# Its symbol "shown" is the code of SHOWN_URL with SHOWN_KEY, held to uqr by qr.test.ts.
QR_FIXTURE = ROOT / "ui" / "src" / "lib" / "qr.fixture.json"
QR_QUIET = 4


class Daemon:
    """`python -m neoaprs` as a child process, its page's port read from its log."""

    def __init__(self, data: Path, *extra: str, env: dict[str, str] | None = None) -> None:
        self.data, self.extra, self.env = data, extra, env or {}
        self.proc: asyncio.subprocess.Process | None = None
        self.url = ""
        self.log: list[str] = []

    async def start(self) -> str:
        env = {k: v for k, v in os.environ.items() if not k.startswith("NEOAPRS_")}
        env["NEOAPRS_UPDATE_CHECK"] = "0"
        env["NEOAPRS_SERIAL_PATTERN"] = "/nonexistent/none*"
        # No device, sound card or Mercury is used and nothing but this computer is reached
        # (neoaprs/nodevices.py); the Dummy radios' air is made up.
        env["NEOAPRS_NO_DEVICES"] = "1"
        # No player of raw audio is found, so the Dummy HF radio never plays frames aloud (as in
        # tests/conftest.py).
        env["NEOAPRS_PLAYER_PATH"] = "/nonexistent/neoaprs-shots-players"
        env.update(self.env)
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "neoaprs",
            "--data",
            str(self.data),
            "--web-port",
            "0",
            *self.extra,
            env=env,
            cwd=ROOT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        asyncio.create_task(self._drain())
        logfile = self.data / "neoaprs.log"  # the log has the line; stderr only the warnings
        async with asyncio.timeout(60):
            while not self.url:
                await asyncio.sleep(0.2)
                if self.proc.returncode is not None:
                    raise RuntimeError("the daemon ended:\n" + "\n".join(self.log[-20:]))
                if logfile.exists() and (
                    found := re.search(r"web page at (http://\S+?)/?\s", logfile.read_text(errors="replace") + "\n")
                ):
                    self.url = found.group(1) + "/"
        return self.url

    async def _drain(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        while line := await self.proc.stdout.readline():
            self.log.append(line.decode(errors="replace").rstrip())

    async def stop(self) -> None:
        if self.proc is None or self.proc.returncode is not None:
            return
        self.proc.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(self.proc.wait(), 15)
        except TimeoutError:
            self.proc.kill()
            await self.proc.wait()


async def start_traffic() -> asyncio.subprocess.Process:
    """Start scripts/demotraffic.py (aircraft on 127.0.0.1:7391, ships on 7392); refuse if a port
    is held."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(HERE / "demotraffic.py"),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=ROOT,
    )
    assert process.stdout is not None
    try:
        line = (await asyncio.wait_for(process.stdout.readline(), 20)).decode(errors="replace").strip()
    except TimeoutError:
        line = ""
    if not line.startswith("listening"):
        await stop_process(process)
        raise RuntimeError(
            f"the made-up aircraft and ships did not start on ports {demotraffic.PORT} and {demoships.AIS_PORT} of this computer: is another demotraffic or demo-daemon --traffic running?"
        )
    return process


async def stop_process(process: asyncio.subprocess.Process) -> None:
    """A child process ended: asked to, and killed when it does not within 10 s."""
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), 10)
    except TimeoutError:
        process.kill()
        await process.wait()


async def start_gps_replay() -> asyncio.subprocess.Process:
    """Start `neoaprs gps-replay`, a fake gpsd on a free loopback port driving a car round a block
    at the scene's home, a little faster than real time."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("NEOAPRS_")}
    with socket.socket() as probe:
        try:
            probe.bind((demoscene.HOST, GPSD_PORT))
            port = GPSD_PORT
        except OSError:
            port = 0
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "neoaprs",
        "gps-replay",
        "--port",
        str(port),
        "--at",
        f"{demoscene.HOME[0]},{demoscene.HOME[1]}",
        "--kmh",
        "45",
        "--interval",
        "0.5",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
        cwd=ROOT,
    )


def neoaprs_db_set(data: Path, key: str, value: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "neoaprs", "db", "--data", str(data), "set", key, value],
        check=True,
        capture_output=True,
        cwd=ROOT,
    )


def neoaprs_db_add_radio(data: Path, radio_type: str, name: str = "") -> int:
    """Add a radio of the type (and name) to a data folder with no daemon running; return its id."""
    if radio_type in FORBIDDEN_TYPES:
        raise ValueError(f"no shot uses the {radio_type} type: it would start a modem on the sound card")
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "neoaprs",
            "db",
            "--data",
            str(data),
            "radios",
            "add",
            radio_type,
            *([name] if name else []),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    found = re.match(r"radio (\d+) ", done.stdout)
    if found is None:
        raise RuntimeError(f"radios add {radio_type}: no radio said: {done.stdout.strip()!r}")
    return int(found.group(1))


async def give_radios(data: Path) -> dict[str, int]:
    """Give the station of the shots its radios once the day is played: radio 1 becomes the first of
    RADIOS and keeps its frames, the others are added; return each id by kind."""
    (fm_kind, fm_type, _), *others = RADIOS
    ctl = Controller(data)
    await ctl.open_database()
    assert ctl.db is not None
    try:
        changed = await ctl.store.change_radio(DAY_RADIO, type=fm_type)
    finally:
        await ctl.db.close()
    if not changed:
        raise RuntimeError(f"radio {DAY_RADIO} could not be made the {fm_type} radio")
    ids = {fm_kind: DAY_RADIO} | {kind: neoaprs_db_add_radio(data, type, name) for kind, type, name in others}
    return ids


def put_map(source: Path, target: Path) -> None:
    """Put the map file in a data folder as a hard link (the server will not follow a symlink),
    else a copy."""
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def copy_data(source: Path, target: Path) -> None:
    """Copy the operator's data folder (no daemon running); the map is linked, not copied."""
    shutil.copytree(
        source,
        target,
        copy_function=lambda a, b: put_map(Path(a), Path(b)) if str(a).endswith(".pmtiles") else shutil.copy2(a, b),
    )


async def serve_version(version: str) -> asyncio.Server:
    """Serve a version page on a loopback port saying `version` is the latest; nothing else is
    asked."""
    return await serve_json(
        f'{{"version": "{version}", "url": "https://github.com/oh2gba/neoaprs/releases/tag/v{version}", "message": ""}}'.encode()
    )


def port_of(server: asyncio.Server) -> int:
    return int(server.sockets[0].getsockname()[1])


# Who planned the two HF tests: two of the day's cast (scripts/demoscene.py).
SKED_CALLS = ("OH2ZPK", "OH3ZHK")
SKED_DIAL = dict(SUGGESTED)["40 m"]  # the dial of both: the 40 m one the page suggests


def made_up_board(now: datetime) -> bytes:
    """Return the HF test board the hf-tests shot reads: two tests on 40 m, by two of the day's
    cast."""
    day = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    times = (
        (day + timedelta(days=1, hours=17), day + timedelta(days=1, hours=18, minutes=30)),
        (day + timedelta(days=2, hours=6, minutes=30), day + timedelta(days=2, hours=8)),
    )
    notes = ("Beacons every 10 min, messages welcome", "Morning path to the south, 10 W")
    rows = [
        {
            "id": id,
            "call": call,
            "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dial": SKED_DIAL,
            "note": note,
        }
        for id, call, (start, end), note in zip(("5c0a1e7b2d94", "e83f6a0c51b7"), SKED_CALLS, times, notes, strict=True)
    ]
    return json.dumps({"v": 1, "closed": False, "skeds": rows}).encode()


async def serve_json(body: bytes) -> asyncio.Server:
    """Serve `body` as JSON on a loopback port for every request (the version page, the HF test
    board)."""

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    return await asyncio.start_server(answer, demoscene.HOST, 0)


def next_version(version: str) -> str:
    """Return a made-up newer version, `version` with its patch number plus one (1.0.0-rc1 gives
    1.0.1)."""
    major, minor, patch = version.split("-")[0].split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


# The update shot's version page says this one is out: always one past this tree's version.
UPDATE_TO = next_version(VERSION)
# The "NeoAPRS <version>" beside Check now is hidden in every shot (its space stays), so a new
# version makes no shot old. The page allows an inline style sheet (neoaprs/web/headers.py).
HIDE_VERSION = ".updateversion { visibility: hidden; }"


async def prepare(work: Path, radio: demoscene.DemoRadio, basemap: Path | None) -> tuple[Path, dict[str, int]]:
    """Prepare the operator's data folder: settings, the map, the day played, then the radios of the
    shots; return each radio's id by kind."""
    data = work / "demo"
    data.mkdir()
    ctl = Controller(data)
    await ctl.open_database()
    assert ctl.db is not None
    await ctl.db.close()
    if neoaprs_db_add_radio(data, RADIO_TYPE, RADIOS[0][2]) != DAY_RADIO:
        raise RuntimeError(f"the day's radio is not radio {DAY_RADIO}")
    for key, value in {**SETTINGS, f"radio/{DAY_RADIO}/tcp_port": str(radio.port)}.items():
        neoaprs_db_set(data, key, value)
    if basemap is not None:
        put_map(basemap, data / "basemap.pmtiles")
    played = await demoscene.history(data, radio)
    print(f"the day: {played} events, {len(radio.sent)} frames sent to the radio")
    letters = "abcdefghjkmnpqrstuvwxyz23456789"
    neoaprs_db_set(data, "web/key", "-".join("".join(secrets.choice(letters) for _ in range(4)) for _ in range(3)))
    for key, value in AFTER_THE_DAY.items():
        neoaprs_db_set(data, key, value)
    ids = await give_radios(data)
    print("the radios:", ", ".join(f"{LABELS[kind]} (radio {id})" for kind, id in ids.items()))
    return data, ids


# ---- the browser


class Shots:
    def __init__(self, browser: Any, url: str, out: Path) -> None:
        self.browser, self.url, self.out = browser, url, out
        self.written: dict[str, int] = {}
        self.update_url = ""
        self.receive_url = ""
        self.moving_url = ""
        self.skeds_url = ""
        self.layers_url = ""
        self.radios: dict[str, int] = {}  # the id of each radio of the shots, by its kind
        self.scheme = "light"
        # The browser contexts of the shot being taken (a failed shot leaves its own open).
        self.contexts: list[Any] = []
        self.started = asyncio.get_running_loop().time()

    async def since_start(self, seconds: float) -> None:
        """Wait until the daemon has run this long; its first beacon and status go out some
        seconds after start."""
        left = self.started + seconds - asyncio.get_running_loop().time()
        if left > 0:
            await asyncio.sleep(left)

    async def page(
        self,
        size: dict[str, int],
        scheme: str | None = None,
        tab: str = "stations",
        view: tuple[float, float, float] | None = None,
        panel: int | None = None,
        wx_hours: str | None = None,
        url: str | None = None,
        wait_ms: int = 5000,
        scale: int = 1,
        headers: dict[str, str] | None = None,
        phone_view: str | None = None,
        locale: str = "en-GB",
        stored: dict[str, str] | None = None,
        init: str = "",
    ) -> Any:
        context = await self.browser.new_context(
            viewport=size,
            color_scheme=scheme or self.scheme,
            device_scale_factor=scale,
            locale=locale,
            timezone_id="Europe/Helsinki",
            extra_http_headers=headers,
        )
        keys = {"tab": tab, "panel": "open", **(stored or {})}
        if view:
            keys["mapview"] = f'{{"lat":{view[0]},"lon":{view[1]},"zoom":{view[2]}}}'
        if panel:
            keys["panelwidth"] = str(panel)
        if wx_hours:
            keys["wxhours"] = wx_hours
        if phone_view:
            keys["view"] = phone_view  # a phone shows the map or the panel, one at a time
        script = "".join(f"try{{localStorage.setItem('NeoAPRS.{k}',{v!r})}}catch(e){{}};" for k, v in keys.items())
        await context.add_init_script(script)
        if init:
            # Before the page's own scripts: the made-up waterfall's socket.
            await context.add_init_script(init)
        self.contexts.append(context)
        page = await context.new_page()
        await page.goto(url or self.url)
        await page.add_style_tag(content=HIDE_VERSION)
        await page.wait_for_timeout(wait_ms)
        return page

    async def save(self, page: Any, name: str, clip: dict[str, int] | None = None) -> None:
        await page.mouse.move(2, 2)  # the pointer is not left on a row or a marker
        await page.wait_for_timeout(300)
        raw = await page.screenshot(clip=clip)
        data = shrink(raw)
        name = name + ("-dark" if self.scheme == "dark" else "")
        (self.out / f"{name}.png").write_bytes(data)
        self.written[name] = len(data)
        print(f"{name}.png  {len(data) // 1024} KB")
        await page.context.close()
        if page.context in self.contexts:
            self.contexts.remove(page.context)

    async def close_left(self) -> None:
        """Closes what a shot that failed left open."""
        for context in self.contexts:
            await context.close()
        self.contexts.clear()


def shrink(png: bytes) -> bytes:
    """Re-save the PNG with the best compression, reducing colours only if it is still over the
    limit."""
    from PIL import Image

    image = Image.open(io.BytesIO(png)).convert("RGB")
    for colours in (0, 256, 192, 128, 96):
        buffer = io.BytesIO()
        (
            image
            if colours == 0
            else image.quantize(colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        ).save(buffer, "PNG", optimize=True)
        if buffer.tell() <= LIMIT_KB * 1024 or colours == 96:
            return buffer.getvalue()
    raise AssertionError("unreachable")


async def settle(page: Any, ms: int = 1500) -> None:
    await page.wait_for_timeout(ms)


async def open_stations_tab(page: Any) -> None:
    """Open the Stations tab, the second of the bar (under More on the narrowest panel, which a
    phone has under Map)."""
    tab = page.locator("#tab-stations")
    if await tab.is_visible():
        await tab.click()
        return
    await page.locator("#tabmenu-button").click()
    await page.get_by_role("menuitem", name="Stations").click()


# The Dummy radios' stations are all heard by then (the HF cities' last first beacon is 118 s
# after start); a station heard first goes to the top and would move every row under it.
TABLE_STILL_SEC = 125


async def pick_station(s: Shots, page: Any, call: str, wait: int = 4500, add: bool = False) -> None:
    """Click the row of `call` in the Stations table to open its card (Ctrl+click with `add`),
    once the table has all its stations so that the row does not move under the click."""
    await s.since_start(TABLE_STILL_SEC)
    await open_stations_tab(page)
    await page.locator("#pane-stations tbody tr", has_text=call).first.click(modifiers=["Control"] if add else [])
    await page.wait_for_timeout(wait)


# The map views: (lat, lon, zoom).
OVERVIEW = (60.205, 24.80, 9.6)
CITY = (60.185, 24.78, 11.2)

Shot = Callable[[Shots, str], Awaitable[None]]


async def shot_map(s: Shots, _: str) -> None:
    page = await s.page(DESKTOP, view=(60.19, 24.76, 9.3), panel=WIDE_PANEL)
    await s.save(page, "map")


async def shot_stations(s: Shots, _: str) -> None:
    page = await s.page(DESKTOP, view=OVERVIEW, panel=900)
    await s.save(page, "stations")


async def shot_station(s: Shots, _: str) -> None:
    page = await s.page(DESKTOP, view=(60.165, 24.78, 11.6))
    await pick_station(s, page, "OH2ZMA-9")
    await s.save(page, "station")


async def shot_station_details(s: Shots, _: str) -> None:
    """The card of a station running a Kenwood TH-D74 with Details open: Device row, PHG antenna
    with its arrow, and the Packets counts."""
    page = await s.page(DESKTOP, view=(60.232, 24.946, 10.3), panel=480)
    await pick_station(s, page, "OH2ZPK", wait=2500)
    await page.locator('.cardstack .card[data-call="OH2ZPK"]').get_by_text("Details", exact=True).click()
    await settle(page, 800)
    await s.save(page, "station-details")


async def shot_weather(s: Shots, _: str) -> None:
    """Two weather stations, their cards side by side over the map, the graphs on the same value
    axes."""
    page = await s.page(DESKTOP, view=(60.08, 24.62, 9.6), panel=560)
    await pick_station(s, page, "OH2ZWB", wait=1500)
    await pick_station(s, page, "OH2ZWA", add=True)
    await s.save(page, "weather")


async def shot_cards(s: Shots, _: str) -> None:
    """Two messageable stations with Close all and Message these 2 at the top left; the second card
    has been dragged by its head and the first stays."""
    page = await s.page(DESKTOP, view=(60.20, 24.95, 9.6), panel=560)
    await pick_station(s, page, "OH2ZMA-9", wait=1500)
    await pick_station(s, page, "OH2ZPK", add=True)
    head = await page.locator('.cardstack .card[data-call="OH2ZPK"] .card-head').bounding_box()
    assert head is not None
    x, y = head["x"] + head["width"] / 3, head["y"] + head["height"] / 2
    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.mouse.move(x, y - 150, steps=8)
    await page.mouse.move(x + 6, y - 420, steps=8)
    await page.mouse.up()
    await settle(page, 600)
    await s.save(page, "cards")


def tag_of(page: Any, where: str, label: str) -> Any:
    """Return the tags of the radio `label` in the part of the page `where` names (TagMark's
    `.tag`)."""
    return page.locator(f"{where} .tag", has_text=re.compile(rf"^\s*{re.escape(label)}\s*$"))


def heard_on(page: Any, label: str) -> Any:
    """The rows of the Stations table with the tag of the radio `label` in their Heard on cell."""
    return page.locator("#pane-stations tbody tr").filter(has=tag_of(page, "td.heard", label))


async def until_tagged(page: Any, where: str, seconds: float, most: int = 1) -> None:
    """Wait until the part `where` shows the tags of every radio of the shots, `most` of each at
    least."""
    async with asyncio.timeout(seconds):
        while not all([await tag_of(page, where, label).count() >= most for label in LABELS.values()]):
            await page.wait_for_timeout(1000)


async def shot_stations_menu(s: Shots, _: str) -> None:
    """The right-click menu of a Stations row: the questions, Show on map, Copy call, QRZ,
    Forget; the Heard on column has stations of each radio, and the menu is of the first heard
    on HF."""
    page = await s.page(DESKTOP, view=OVERVIEW, panel=900)
    await until_tagged(page, "#pane-stations tbody td.heard", 200)
    row = heard_on(page, LABELS["hf"]).first
    box = await row.bounding_box()
    assert box is not None
    await row.click(button="right", position={"x": min(box["width"] - 60, 330), "y": box["height"] / 2})
    await settle(page, 600)
    await s.save(page, "stations-menu")


async def shot_update(s: Shots, _: str) -> None:
    """The update window: the daemon's version page says a newer version is out and plays a Windows
    install; what is new, Update now and the steps by hand."""
    page = await s.page(DESKTOP, tab="settings", view=CITY, panel=WIDE_PANEL, url=s.update_url)
    await made_up_web(page)
    await page.locator("#set-update-now").click()
    await settle(page, 1500)
    await page.locator(".updateline .btn").click()
    await page.locator(".updatedialog-hand summary").click()
    await settle(page, 800)
    await s.save(page, "update")


async def open_thread(s: Shots, call: str, scale: int = 1, size: dict[str, int] = DESKTOP) -> Any:
    """Open the Messages tab, wide enough for the list beside the conversation, with `call` open."""
    page = await s.page(size, tab="messages", view=CITY, panel=760, scale=scale)
    await page.locator("#pane-messages").get_by_text(call).first.click()
    await settle(page)
    await settle(page, 600)
    return page


async def shot_messages(s: Shots, _: str) -> None:
    page = await open_thread(s, "OH2ZPK")
    await s.save(page, "messages")


async def thread_clip(page: Any, most: int) -> dict[str, int]:
    """Return the clip of the open conversation from its top to its last message, at most `most`
    pixels."""
    await page.evaluate("document.querySelector('#pane-messages .bubbles').scrollTop = 0")
    box = await page.locator("#pane-messages .bubbles").bounding_box()
    last = await page.locator("#pane-messages .bubbles .bubble").last.bounding_box()
    height = min(round(last["y"] + last["height"] - box["y"]) + 12, round(box["height"]), most)
    return {"x": round(box["x"]), "y": round(box["y"]), "width": round(box["width"]), "height": height}


# The width at which the tab bar shows all its tabs, so the tab on show is seen.
WIDE_PANEL = 760
TALL = {"width": 1440, "height": 1250}


async def shot_chain(s: Shots, _: str) -> None:
    """The main conversation's thread close up: the delivery chain of each message, at twice the
    pixels."""
    page = await open_thread(s, "OH2ZPK", scale=2, size=TALL)
    await s.save(page, "chain", clip=await thread_clip(page, 760))


async def shot_chain_failed(s: Shots, _: str) -> None:
    """A message that failed after its four attempts."""
    page = await open_thread(s, "OH2ZXA", scale=2, size=TALL)
    await s.save(page, "chain-failed", clip=await thread_clip(page, 330))


async def shot_email(s: Shots, _: str) -> None:
    """The mail list with Check email over it and a mail being written: address, text, characters
    left."""
    page = await s.page(DESKTOP, tab="email", view=CITY, panel=560)
    await page.fill("#mail-to", "jane@example.com")
    await page.fill("#mail-text", "Antenna is up, see you at the net")
    await settle(page, 400)
    await s.save(page, "email")


async def shot_bulletins(s: Shots, _: str) -> None:
    """The message board: the box to post (a draft with characters left), our two entries marked
    ours."""
    page = await s.page(DESKTOP, tab="bulletins", view=CITY, panel=560)
    await page.fill("#post-text", "Road works on the ring road, expect delays")
    await settle(page, 400)
    await s.save(page, "bulletins")


GPS_VIEW = (60.2285, 24.7225, 13.6)
OBJECTS = (60.19, 24.749, 11.3)  # the view with all of our objects on it


async def shot_objects(s: Shots, _: str) -> None:
    """The Objects tab: our objects and items, how often each was sent and when next; on the map
    with the dashed ring of ours."""
    page = await s.page(DESKTOP, tab="objects", view=OBJECTS, panel=560)
    await s.save(page, "objects")


async def shot_objects_form(s: Shots, _: str) -> None:
    """The form under our objects with a row selected: NETCTRL in it, the button reading Save (Add
    when no row is selected)."""
    page = await s.page(DESKTOP, tab="objects", view=OBJECTS, panel=560)
    await page.locator('#pane-objects .ownobject[data-name="NETCTRL"]').click()
    await settle(page, 600)
    await s.save(page, "objects-form")


async def shot_beacon(s: Shots, _: str) -> None:
    await s.since_start(45)
    page = await s.page(DESKTOP, tab="beacon", view=CITY, panel=WIDE_PANEL)
    await page.locator("#pane-beacon summary", has_text="Advanced").click()
    await settle(page, 400)
    await s.save(page, "beacon")


async def shot_beacon_de(s: Shots, _: str) -> None:
    """The My station tab of a browser that speaks German: the page starts in the browser's
    language."""
    await s.since_start(45)
    page = await s.page(DESKTOP, tab="beacon", view=CITY, panel=WIDE_PANEL, locale="de-DE")
    await page.locator("#pane-beacon summary").filter(has_text="Erweitert").click()
    await settle(page, 400)
    await s.save(page, "beacon-de")


# What the page leaves between two groups of the Settings tab: a picture starts and ends in it.
GROUP_GAP = 8
WHOLE_GROUPS = """([first, gap]) => {
    const pane = document.querySelector('#pane-settings');
    const form = pane.querySelector('.settings');
    form.style.paddingBottom = '700px';                                 // (room to scroll the group to the top: the end of the tab is not the end of the picture)
    const at = (e) => e.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop;
    const groups = [...form.children].filter((e) => e.tagName === 'FIELDSET');
    pane.scrollTop = first ? at(form.querySelector(first)) - gap : 0;
    const top = pane.getBoundingClientRect().top, edge = pane.getBoundingClientRect().bottom;
    const cut = groups.find((g) => g.getBoundingClientRect().bottom > edge);
    if (!cut) return;
    const before = groups[groups.indexOf(cut) - 1];
    const end = Math.min(edge, before ? before.getBoundingClientRect().bottom + gap / 2 : cut.getBoundingClientRect().top);
    if (end <= top + gap) return;                                       // (no whole group in the view: the group at the top begins above it, the one a box inside it was scrolled to, or is taller than the view; it is not blanked)
    pane.style.clipPath = `inset(0 0 ${edge - end}px 0)`;               // (what is below the last whole group is not drawn: the panel's own colour shows)
}"""


async def whole_groups(page: Any, first: str | None = None) -> None:
    """Show the Settings tab in whole groups: the group `first` scrolled to the top (none: the
    top of the tab), the first group not ending in view not drawn, so no row is cut at the
    edge."""
    await page.evaluate(WHOLE_GROUPS, [first, GROUP_GAP])
    await settle(page, 400)


def shown_code() -> tuple[int, str]:
    """Return the size in modules and the path of the phone code of SHOWN_URL with SHOWN_KEY as
    the page draws it."""
    shown = json.loads(QR_FIXTURE.read_text(encoding="utf-8"))["shown"]
    if shown["text"] != f"{SHOWN_URL}#key={SHOWN_KEY}":
        raise SystemExit(f"{QR_FIXTURE.name}: the code 'shown' is not of {SHOWN_URL} with the made-up key")
    runs = [
        f"M{m.start() + QR_QUIET} {y + QR_QUIET}h{len(m[0])}v1h-{len(m[0])}z"
        for y, row in enumerate(shown["rows"])
        for m in re.finditer("1+", row)
    ]
    return len(shown["rows"]) + 2 * QR_QUIET, "".join(runs)


async def made_up_web(page: Any) -> None:
    """Put the made-up access key, phone code and usual KISS port on a Settings page in place of the
    daemon's own, so the machine's address, name and key never appear in a shot."""
    size, path = shown_code()
    await page.evaluate(
        """([key, size, path]) => {
        const put = () => {
            const field = document.getElementById("set-web-key");
            if (field) field.value = key;
            for (const port of document.querySelectorAll('[id$="-tcp_port"]')) port.value = "8001";       // (Direwolf's usual KISS port, should a radio of the shots be one reached over TCP: a radio's own field, set-radio-ID-tcp_port)
            const code = document.querySelector("svg.phonecode");
            if (code) {
                code.setAttribute("viewBox", `0 0 ${size} ${size}`);
                code.querySelector("rect")?.setAttribute("width", `${size}`);
                code.querySelector("rect")?.setAttribute("height", `${size}`);
                code.querySelector("path")?.setAttribute("d", path);
            }
        };
        put();
        setInterval(put, 25);                                   // (the page draws the settings again when the radio's state changes, and puts its own key and code back: they are put over again)
    }""",
        [SHOWN_KEY, size, path],
    )


async def shot_settings_web(s: Shots, _: str) -> None:
    """Settings, the Web page group: the switch on, the access key and phone code (made-up
    values)."""
    # The width the project page crops it to.
    page = await s.page(DESKTOP, tab="settings", view=CITY, panel=560)
    await made_up_web(page)
    await whole_groups(page, "fieldset:has(#set-web-key)")
    await s.save(page, "settings-web")


async def shot_settings_tnc(s: Shots, _: str) -> None:
    """Settings, the Radio group of the three radios: a box for each (Enable, Name, Remove and
    status line, folded to one line when connected), then Add radio."""
    page = await s.page(DESKTOP, tab="settings", view=CITY, panel=560)
    await made_up_web(page)
    await page.locator(f'#pane-settings fieldset.subbox[data-radio="{s.radios["lora"]}"]').wait_for()
    await whole_groups(page, "fieldset:has(#set-radio-add)")
    await s.save(page, "settings-tnc")


async def shot_beacon_rx(s: Shots, _: str) -> None:
    """The My station tab of a station set to RX only with the Beacon Off: the RX only switch on
    the warn plate, the status block saying nothing is sent, the beacon fields grey."""
    page = await s.page(DESKTOP, tab="beacon", view=CITY, panel=WIDE_PANEL, url=s.receive_url)
    await settle(page, 400)
    await s.save(page, "beacon-rx")


async def shot_phone_beacon_rx(s: Shots, _: str) -> None:
    """A phone set to RX only with the Beacon Off: the RX only switch at the right, and under
    the tab bar the My station tab with its status block and grey beacon fields."""
    page = await s.page(PHONE, tab="beacon", view=CITY, phone_view="panel", url=s.receive_url)
    await s.save(page, "phone-beacon-rx")


# The map the range circle is fitted on is flown to by the page itself; this is only the start.
NEARBY = (60.19, 24.80, 8.5)


async def shot_nearby(s: Shots, _: str) -> None:
    """The Nearby tab with a digipeater selected (OH2RCH-2 of Kumpula): its row highlighted and
    the map zoomed to hold its whole PHG range circle."""
    # Wide enough for each list's help line to be one line, so the lists end above the panel foot.
    page = await s.page(DESKTOP, tab="nearby", view=NEARBY, panel=640)
    await page.locator('#pane-nearby tr[data-call="OH2RCH-2"]').first.click()
    await settle(page, 3500)  # the map flies to the circle
    await s.save(page, "nearby")


async def shot_beacon_gps(s: Shots, _: str) -> None:
    """The My station tab of a moving station: Position A GPS via gpsd, the GPS fix and
    SmartBeaconing line, Beacon On (SmartBeaconing), Travelling By car; our station drives
    round a block."""
    await s.since_start(80)
    page = await s.page(DESKTOP, tab="beacon", view=GPS_VIEW, panel=WIDE_PANEL, url=s.moving_url)
    await settle(page, 600)
    await s.save(page, "beacon-gps")


async def shot_phone_key(s: Shots, _: str) -> None:
    """What a phone on the network sees before it is let in: a request via a proxy counts as from
    the network, so the daemon asks for the key."""
    page = await s.page(PHONE, headers={"X-Forwarded-For": "192.168.1.50"}, wait_ms=3000)
    await page.fill("#access-key", SHOWN_KEY)
    await s.save(page, "phone-key")


async def shot_settings(s: Shots, _: str) -> None:
    page = await s.page(DESKTOP, tab="settings", view=CITY, panel=WIDE_PANEL)
    await made_up_web(page)
    await whole_groups(page)
    await s.save(page, "settings")


async def shot_packets(s: Shots, _: str) -> None:
    """The packet log, newest first: each frame with the tag of the radio it came on."""
    page = await s.page(DESKTOP, tab="packets", view=CITY, panel=760)
    await until_tagged(page, "#pane-packets", 200)
    await s.save(page, "packets")


# The map view holding the Dummy HF radio's stations (Turku to Warsaw) and the day's near Helsinki.
HF_WORLD = (57.9, 20.2, 4.5)


async def shot_settings_hf(s: Shots, _: str) -> None:
    """Settings, the Radio group scrolled to the HF radio's box "40 m", opened by the arrow of
    its status line: the Dummy HF type's fields, with the LoRa box and Add radio under it."""
    page = await s.page(DESKTOP, tab="settings", view=CITY, panel=560)
    await made_up_web(page)
    box = page.locator(f'#pane-settings fieldset.subbox[data-radio="{s.radios["hf"]}"]')
    await box.locator(".radiostatus .statushead").first.click()
    await settle(page, 600)
    await whole_groups(page, f'fieldset.subbox[data-radio="{s.radios["hf"]}"]')
    await s.save(page, "settings-hf")


async def shot_stations_hf(s: Shots, _: str) -> None:
    """The Stations table of the three radios with the map zoomed out: the day's stations tagged
    2 m and the six Dummy HF stations hundreds of kilometres away tagged 40 m."""
    page = await s.page(DESKTOP, tab="stations", view=HF_WORLD, panel=760)
    async with asyncio.timeout(170):
        while await heard_on(page, LABELS["hf"]).count() < 6:
            await page.wait_for_timeout(1000)
    await settle(page, 2500)
    await s.save(page, "stations-hf")


# The made-up waterfall of the hf-tests shot: the Dummy HF radio has no scope, so the page socket
# claims one and answers `radio_scope` itself. The rows are frames in the daemon's own form:
# quiet 40 m noise, a faint carrier and DATAC3 frames 1200 to 1800 Hz above the dial.

SCOPE_ROW_SEC = 0.1  # ten rows a second, as the modem part makes them
SCOPE_LIVE_SEC = 30.0
SCOPE_KEPT_SEC = 120.0  # the rows kept of the shot: two minutes, the frames in them
FRAME_SEC = 3.8  # how long a frame is on the air
SCOPE_FRAMES = (
    (6.0, -19.0),
    (27.5, -23.0),
    (41.0, -17.5),
    (66.0, -21.5),
    (83.5, -25.0),
    (101.0, -18.0),
    (113.0, -22.0),
    (124.0, -20.0),
    (139.5, -23.5),
)
SCOPE_CARRIER = (2210.0, -38.0)  # a faint carrier somewhere in the passband (Hz, dB)
MADE_UP_MODEM = {
    "state": "running",
    "reason": "",
    "mode": "DATAC3",
    "keyed": False,
    "busy": False,
    "test": "",
    "snr": None,
    "frames_keyed": 0,
    "max_frame": 123,
    "sound_card": "",
    "frequencies": [{"band": band, "dial": dial} for band, dial in SUGGESTED],
    "keying": "vox",
    "scope": True,
    "tx_gain_db": 0,
    "tx_peak_dbfs": None,
    "rx_level": None,
}


def made_up_rows(seconds: float, seed: int = 40) -> list[ScopeRow]:
    """The rows of `seconds` of the made-up channel, one every SCOPE_ROW_SEC, the oldest first."""
    rand = random.Random(seed)  # noqa: S311  (a made-up channel, the same at every run: nothing secret is drawn)
    hz = [(ROW_FIRST_BIN + i) * MODEM_RATE / 2 / MODEM_BINS for i in range(ROW_BINS)]
    rows: list[ScopeRow] = []
    for step in range(round(seconds / SCOPE_ROW_SEC)):
        at = step * SCOPE_ROW_SEC
        frame = next((level for start, level in SCOPE_FRAMES if start <= at < start + FRAME_SEC), None)
        db = []
        for f in hz:
            noise = -51.0 + rand.gauss(0, 2.2) - (4.0 if f < 420 or f > 2550 else 0.0)
            if abs(f - SCOPE_CARRIER[0]) < 6:
                noise = max(noise, SCOPE_CARRIER[1] + rand.gauss(0, 0.8))
            if frame is not None and SIGNAL_LO_HZ <= f <= SIGNAL_HI_HZ:
                edge = min(f - SIGNAL_LO_HZ, SIGNAL_HI_HZ - f)
                noise = max(noise, frame + rand.gauss(0, 1.3) - (6.0 if edge < 25 else 0.0))
            db.append(noise)
        level = round((-39.0 if frame is not None else -45.0) + rand.gauss(0, 0.6))
        rows.append(ScopeRow(bytes(byte_of_db(value) for value in db), level, False))
    return rows


def scope_frames(radio: int, kept_sec: float = SCOPE_KEPT_SEC) -> tuple[bytes, list[bytes]]:
    """Return the frames of the made-up waterfall: the rows kept (a frame of the last
    `kept_sec`, daemon clock 0) and the rows after them, each named by the radio
    (radio_header) as the daemon sends them."""
    rows = made_up_rows(kept_sec + SCOPE_LIVE_SEC)
    kept = round(kept_sec / SCOPE_ROW_SEC)
    end = kept * SCOPE_ROW_SEC
    history = radio_header(radio) + history_frame(
        [KeptRow(i + 1, (i + 1) * SCOPE_ROW_SEC, row) for i, row in enumerate(rows[:kept])], end, 0.0
    )
    return history, [radio_header(radio) + row_frame(row) for row in rows[kept:]]


SCOPE_PAGE = """(() => {
  // The made-up waterfall of the HF radio of the hf-tests shot (scripts/screenshots.py): the page's socket says that radio has a scope, and its rows come from here.
  const P = %s;
  const bytes = (text) => Uint8Array.from(atob(text), (c) => c.charCodeAt(0));
  const kept = bytes(P.history);
  const live = P.live.map(bytes);
  const scoped = (row) => (row && typeof row === "object" && row.id === P.radio ? { ...row, can: { ...row.can, scope: true }, modem: { ...P.modem, ...(row.modem || {}), scope: true } } : row);
  const each = (rows) => (rows && typeof rows === "object" ? Object.fromEntries(Object.entries(rows).map(([key, row]) => [key, scoped(row)])) : rows);
  const told = (text) => {
    let message;
    try { message = JSON.parse(text); } catch { return text; }
    if (!message || message.topic !== "radios") return text;
    if (message.type === "state") message.value = each(message.value);
    else if (message.type === "patch" && Array.isArray(message.ops))
      message.ops = message.ops.map((op) => (op.op === "replace" ? { ...op, value: each(op.value) } : op.op === "del" ? op : { ...op, value: scoped(op.value) }));
    return JSON.stringify(message);
  };
  const Native = window.WebSocket;
  class ShotSocket extends Native {
    constructor(...args) {
      super(...args);
      this.shotHandler = null;
      this.shotTimer = 0;
      super.onmessage = (event) => {
        if (this.shotHandler) this.shotHandler(typeof event.data === "string" ? new MessageEvent("message", { data: told(event.data) }) : event);
      };
    }
    get onmessage() { return this.shotHandler; }
    set onmessage(handler) { this.shotHandler = handler; }
    send(data) {
      if (typeof data === "string" && data.includes("radio_scope")) {
        let command = null;
        try { command = JSON.parse(data); } catch { command = null; }
        if (command && command.cmd === "radio_scope" && command.radio === P.radio) return this.shotScope(command.on === true, command.seconds);
      }
      return super.send(data);
    }
    shotScope(on, seconds) {
      clearInterval(this.shotTimer);
      if (!on) return;
      // As the daemon does: only the rows of the seconds asked for, oldest first.
      const first = P.clockAt + 8;
      let from = first;
      const ages = new DataView(kept.buffer);
      while (seconds !== undefined && from < kept.length && ages.getUint32(from + 2, true) > seconds * 1000) from += P.rowBytes;
      const history = new Uint8Array(kept.length - (from - first));
      history.set(kept.subarray(0, first));
      history.set(kept.subarray(from), first);
      new DataView(history.buffer).setFloat64(P.clockAt, Date.now(), true);
      this.shotGive(history.buffer);
      let next = 0;
      this.shotTimer = setInterval(() => this.shotGive(live[next++ %% live.length].slice().buffer), P.everyMs);
    }
    shotGive(buffer) {
      if (this.readyState === Native.OPEN && this.shotHandler) this.shotHandler(new MessageEvent("message", { data: buffer }));
    }
    close(...args) {
      clearInterval(this.shotTimer);
      return super.close(...args);
    }
  }
  window.WebSocket = ShotSocket;
})();"""


def scope_page(radio: int, kept_sec: float = SCOPE_KEPT_SEC) -> str:
    """Return the script the hf-tests shot's browser runs before the page's own (SCOPE_PAGE),
    with `radio`'s rows; the browser suite's monitor card is given more."""
    history, live = scope_frames(radio, kept_sec)
    clock_at = len(radio_header(radio)) + struct.calcsize(HISTORY_HEADER.format[:2])
    given = {
        "radio": radio,
        "modem": MADE_UP_MODEM,
        "history": base64.b64encode(history).decode(),
        "live": [base64.b64encode(frame).decode() for frame in live],
        "clockAt": clock_at,
        "rowBytes": HISTORY_ROW.size + ROW_BINS,
        "everyMs": round(SCOPE_ROW_SEC * 1000),
    }
    return SCOPE_PAGE % json.dumps(given)


async def shot_hf_tests(s: Shots, _: str) -> None:
    """The HF tests tab with the two made-up tests (Join beside each, the form to plan one at the
    bottom), and over the map the Monitor card with the 40 m waterfall of the last two
    minutes."""
    page = await s.page(
        DESKTOP,
        tab="skeds",
        view=CITY,
        panel=560,
        url=s.skeds_url,
        stored={"monitor": "open"},
        init=scope_page(s.radios["hf"]),
    )
    async with asyncio.timeout(90):
        while await page.locator("#pane-skeds ul.board > li.sked").count() < len(SKED_CALLS):
            await page.wait_for_timeout(1000)
    await page.locator(".monitorcard canvas").first.wait_for(timeout=30000)
    await settle(page, 2500)
    await s.save(page, "hf-tests")


# 140 km across: the aircraft fly within 80 km of the station, the ships within 35 km of the sea.
LAYERS_VIEW = (60.18, 24.82, 8.0)
LAYERS_TICKED = {"layer.aircraft": "on", "layer.ships": "on"}
LAYERS_SETTINGS = {
    "map/aircraft": "receiver",
    "map/aircraft_host": f"{demotraffic.HOST}:{demotraffic.PORT}",
    "map/ships": "receiver",
    "map/ships_host": f"{demotraffic.HOST}:{demoships.AIS_PORT}",
}
COUNT_IS_A_NUMBER = """(sel) => /^[0-9]+$/.test((document.querySelector(sel)?.textContent ?? '').trim()) && Number(document.querySelector(sel).textContent.trim()) > 0"""


async def counted(page: Any, layer: str) -> None:
    """Wait until the row of `layer` in the open Layers box has a count above 0: the layer has
    drawn things."""
    await page.wait_for_function(
        COUNT_IS_A_NUMBER, arg=f'.layers-row[data-layer="{layer}"] .layers-count', timeout=60000
    )


async def shot_layers(s: Shots, _: str) -> None:
    """The map with the Layers box open: Tracks and ALOHA circle ticked, Locator grid not, and
    Aircraft and Ships ticked, each with its drawn count from the made-up receiver; aircraft
    and hulls among the stations."""
    page = await s.page(DESKTOP, view=LAYERS_VIEW, panel=480, url=s.layers_url, stored=LAYERS_TICKED, wait_ms=3000)
    await page.locator(".layers-toggle").click()
    await page.locator(".layers-box").wait_for(state="visible", timeout=10000)
    await counted(page, "aircraft")
    await counted(page, "ships")
    await settle(page, 2000)
    await s.save(page, "layers")


async def shot_phone_map(s: Shots, _: str) -> None:
    page = await s.page(PHONE, view=(60.19, 24.80, 9.4))
    await s.save(page, "phone-map")


async def shot_phone_bulletins(s: Shots, _: str) -> None:
    page = await s.page(PHONE, tab="bulletins", view=(60.19, 24.80, 9.4), phone_view="panel")
    await s.save(page, "phone-bulletins")


async def shot_phone_messages(s: Shots, _: str) -> None:
    """A phone shows one thing at a time: here the conversation, with its back arrow, bubbles and
    input."""
    page = await s.page(PHONE, tab="messages", view=CITY, phone_view="panel")
    await page.locator("#pane-messages").get_by_text("OH2ZPK").first.click()
    await settle(page)
    await s.save(page, "phone-messages")


async def shot_phone_weather(s: Shots, _: str) -> None:
    """A tap on a Stations row shows the map and the station's card as a bottom sheet, opened
    with a tap on its grip."""
    page = await s.page(PHONE, tab="stations", view=(60.15, 24.80, 11), phone_view="panel")
    await pick_station(s, page, "OH2ZWA", wait=3000)
    await page.locator(".sheet-grip").click()  # a tap on the grip opens the sheet up: the graphs
    await settle(page, 2500)
    await s.save(page, "phone-weather")


async def shot_tablet(s: Shots, _: str) -> None:
    """A tablet: the map and a 380 to 420 px panel side by side, here Messages with a
    conversation open."""
    page = await s.page(TABLET, tab="messages", view=CITY)
    await page.locator("#pane-messages").get_by_text("OH2ZPK").first.click()
    await settle(page)
    await s.save(page, "tablet")


async def shot_setup(s: Shots, fresh_url: str) -> None:
    """The guide of a folder with no call, at its Position step: the call typed in, the Location
    row with its coordinate entry open, as a station with no place has it."""
    page = await s.page(DESKTOP, url=fresh_url, wait_ms=3500)
    await page.locator(".setup input").first.fill("OH2GBA")
    await page.get_by_role("button", name="Next").click()
    await page.wait_for_timeout(600)
    await page.fill("#setup-lat", str(demoscene.HOME[0]))
    await page.fill("#setup-lon", str(demoscene.HOME[1]))
    await page.wait_for_timeout(2500)
    await s.save(page, "setup")


def thumbs_of(out: Path, names: set[str] | None = None, skip: Collection[str] = ()) -> list[Path]:
    """Return the shots whose thumbnails and WebP copies make_thumbs makes: `names`, else every
    PNG but og.png; never those of `skip`, whose PNG is an earlier run's."""
    return [
        path
        for path in sorted(out.glob("*.png"))
        if path.name != "og.png" and (names is None or path.stem in names) and path.stem not in skip
    ]


def make_thumbs(out: Path, names: set[str] | None = None, skip: Collection[str] = ()) -> int:
    """Make thumbs/NAME.png (640 px wide, 270 for a phone) and NAME.webp beside every shot and
    thumb, for the shots of thumbs_of; return how many shots had theirs made."""
    from PIL import Image

    (out / "thumbs").mkdir(exist_ok=True)
    made = 0
    for path in thumbs_of(out, names, skip):
        image = Image.open(path).convert("RGB")
        width = 270 if path.name.startswith("phone-") else 640
        small = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS).quantize(
            128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
        )
        small.save(out / "thumbs" / path.name, optimize=True)
        image.save(path.with_suffix(".webp"), quality=82, method=6)
        image.resize(small.size, Image.LANCZOS).save(
            (out / "thumbs" / path.name).with_suffix(".webp"), quality=80, method=6
        )
        made += 1
    print(f"thumbs/: {made} shots' thumbnails, and a .webp beside each picture")
    return made


def _font(size: int, bold: bool) -> Any:
    from PIL import ImageFont

    names = (
        ("NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "arialbd.ttf")
        if bold
        else ("NotoSans-Regular.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf")
    )
    for name in names:
        for folder in (
            "",
            "/usr/share/fonts/truetype/noto/",
            "/usr/share/fonts/truetype/dejavu/",
            "/usr/share/fonts/truetype/liberation/",
            "C:/Windows/Fonts/",
        ):
            try:
                return ImageFont.truetype(folder + name, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


# The systems as the site's own first lines name them (site/index.html).
PITCH = "A modern, easy-to-use APRS client for Windows, macOS, Linux and the Raspberry Pi"
# The room for the pitch beside the map: from its left edge (58) to 14 px before the map (468).
PITCH_WIDTH = 396


def lines_of(text: str, fits: Callable[[str], bool]) -> list[str]:
    """Cut `text` at its spaces into lines that each fit; a word longer than the room is a line
    of its own."""
    lines: list[str] = []
    for word in text.split():
        if lines and fits(f"{lines[-1]} {word}"):
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def make_og(out: Path) -> bool:
    """Make og.png, 1200x630: the map shot on the icon's petrol with the name and pitch; False if
    there is no map shot."""
    from PIL import Image, ImageDraw

    source = out / "map.png"
    if not source.exists():
        return False
    card = Image.new("RGB", (1200, 630), (10, 42, 61))  # petrol #0a2a3d, the icon's tile
    shot = Image.open(source).convert("RGB")
    shot = shot.resize((round(shot.width * 0.62), round(shot.height * 0.62)), Image.LANCZOS)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, shot.width, shot.height), radius=18, fill=255)
    card.paste(shot, (468, 112), mask)
    draw = ImageDraw.Draw(card)
    draw.text((56, 150), "NeoAPRS", font=_font(84, True), fill=(255, 255, 255))
    font = _font(28, False)
    for i, line in enumerate(lines_of(PITCH, lambda text: draw.textlength(text, font=font) <= PITCH_WIDTH)):
        # Mint #a6d7d4, as the site's dark band has it on petrol: 9.4 to 1.
        draw.text((58, 262 + i * 40), line, font=font, fill=(166, 215, 212))
    if ICON.exists():
        mark = Image.open(ICON).convert("RGBA").resize((72, 72), Image.LANCZOS)
        card.paste(mark, (58, 56), mark)
    card.save(out / "og.png", optimize=True)
    print("og.png")
    return True


EXTRAS = ("thumbs", "og")  # what is made from the shots, with no browser
SHOTS: dict[str, Shot] = {
    "map": shot_map,
    "stations": shot_stations,
    "station": shot_station,
    "weather": shot_weather,
    "messages": shot_messages,
    "email": shot_email,
    "bulletins": shot_bulletins,
    "objects": shot_objects,
    "objects-form": shot_objects_form,
    "beacon": shot_beacon,
    "settings": shot_settings,
    "packets": shot_packets,
    "phone-map": shot_phone_map,
    "phone-bulletins": shot_phone_bulletins,
    "phone-weather": shot_phone_weather,
    "cards": shot_cards,
    "stations-menu": shot_stations_menu,
    "update": shot_update,
    "beacon-de": shot_beacon_de,
    "phone-messages": shot_phone_messages,
    "tablet": shot_tablet,
    "setup": shot_setup,
    "chain": shot_chain,
    "chain-failed": shot_chain_failed,
    "settings-web": shot_settings_web,
    "phone-key": shot_phone_key,
    "station-details": shot_station_details,
    "settings-tnc": shot_settings_tnc,
    "beacon-rx": shot_beacon_rx,
    "phone-beacon-rx": shot_phone_beacon_rx,
    "nearby": shot_nearby,
    "beacon-gps": shot_beacon_gps,
    "settings-hf": shot_settings_hf,
    "stations-hf": shot_stations_hf,
    "hf-tests": shot_hf_tests,
    "layers": shot_layers,
}
DARK_TOO = (
    "map",
    "stations",
    "station",
    "weather",
    "messages",
    "email",
    "bulletins",
    "objects",
    "objects-form",
    "beacon",
    "settings",
    "packets",
    "phone-map",
    "phone-bulletins",
    "phone-weather",
    "cards",
    "stations-menu",
    "update",
    "beacon-de",
    "phone-messages",
    "tablet",
    "setup",
    "chain",
    "chain-failed",
    "settings-web",
    "phone-key",
    "station-details",
    "settings-tnc",
    "beacon-rx",
    "phone-beacon-rx",
    "nearby",
    "beacon-gps",
    "settings-hf",
    "stations-hf",
    "hf-tests",
    "layers",
)


def in_the_dark(shot: Shot) -> Shot:
    async def dark(s: Shots, fresh_url: str) -> None:
        s.scheme = "dark"
        try:
            await shot(s, fresh_url)
        finally:
            s.scheme = "light"

    return dark


SHOTS.update({f"{name}-dark": in_the_dark(SHOTS[name]) for name in DARK_TOO})


SITE = ROOT / "site"
SITE_URL = "https://neo.oh2gba.eu/"  # where og:image points: its file is site/ under it


def image_size(path: Path) -> tuple[int, int] | None:
    """Return the width and height of a PNG or WebP file read from its header (no Pillow); None
    if neither."""
    try:
        with path.open("rb") as f:
            head = f.read(30)
    except OSError:
        return None
    if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
        width, height = struct.unpack(">II", head[16:24])
        return width, height
    if head[:4] != b"RIFF" or head[8:12] != b"WEBP" or len(head) < 30:
        return None
    chunk = head[12:16]
    if chunk == b"VP8 ":
        return struct.unpack("<H", head[26:28])[0] & 0x3FFF, struct.unpack("<H", head[28:30])[0] & 0x3FFF
    if chunk == b"VP8L":
        bits = int.from_bytes(head[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X":  # extended: the canvas, 24 bits each, less one
        return int.from_bytes(head[24:27], "little") + 1, int.from_bytes(head[27:30], "little") + 1
    return None


IMG = re.compile(r"<img\b[^>]*>")
PICTURE = re.compile(r"<picture\b.*?</picture>", re.S)


def _attr(tag: str, name: str) -> str | None:
    found = re.search(rf'\b{name}="([^"]*)"', tag)
    return found.group(1) if found else None


def wrong_sizes(site: Path = SITE) -> list[str]:
    """Return a line for each declared size that differs from its file: <img> sizes, a
    <picture>'s dark copy at another size, and og:image width and height against og.png."""
    wrong: list[str] = []
    for page in sorted(site.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        for tag in IMG.findall(html):
            src, size = _attr(tag, "src"), image_size(site / (_attr(tag, "src") or ""))
            if src is None or size is None:
                continue
            declared = (_attr(tag, "width"), _attr(tag, "height"))
            if declared != (str(size[0]), str(size[1])):
                wrong.append(
                    f"{page.name}: {src} is declared {declared[0]}x{declared[1]}, the file is {size[0]}x{size[1]}"
                )
        for picture in PICTURE.findall(html):
            tag = next(iter(IMG.findall(picture)), "")
            src = _attr(tag, "src") or ""
            dark = f"{PurePosixPath(src).with_suffix('')}-dark{PurePosixPath(src).suffix}"
            if (
                f'srcset="{dark}"' in picture
                and (size := image_size(site / src)) is not None
                and (dark_size := image_size(site / dark)) not in (None, size)
            ):
                wrong.append(
                    f"{page.name}: {dark} is {dark_size[0]}x{dark_size[1]} in the box of {src}, {size[0]}x{size[1]}"
                )
        og = re.search(rf'<meta property="og:image" content="{re.escape(SITE_URL)}([^"]+)">', html)
        if og and (size := image_size(site / og.group(1))) is not None:
            for name, value in (("width", size[0]), ("height", size[1])):
                said = re.search(rf'<meta property="og:image:{name}" content="(\d+)">', html)
                if said and said.group(1) != str(value):
                    wrong.append(f"{page.name}: og:image:{name} says {said.group(1)}, {og.group(1)} is {value}")
    return wrong


def sized(html: str, site: Path) -> tuple[str, list[str]]:
    """Return a page with each <img> of a site file given the file's width and height, and og:image
    width and height og.png's; also what changed."""
    changed: list[str] = []

    def one(found: re.Match[str]) -> str:
        tag = found.group(0)
        size, declared = image_size(site / (_attr(tag, "src") or "")), (_attr(tag, "width"), _attr(tag, "height"))
        if size is None or None in declared or declared == (str(size[0]), str(size[1])):
            return tag
        changed.append(f"{_attr(tag, 'src')} {declared[0]}x{declared[1]} -> {size[0]}x{size[1]}")
        return re.sub(r'\bheight="\d*"', f'height="{size[1]}"', re.sub(r'\bwidth="\d*"', f'width="{size[0]}"', tag))

    html = IMG.sub(one, html)
    og = re.search(rf'<meta property="og:image" content="{re.escape(SITE_URL)}([^"]+)">', html)
    if og and (size := image_size(site / og.group(1))) is not None:
        for name, value in (("width", size[0]), ("height", size[1])):
            html, count = re.subn(
                rf'(<meta property="og:image:{name}" content=")(?!{value}")\d+(">)', rf"\g<1>{value}\g<2>", html
            )
            changed += [f"og:image:{name} -> {value}"] if count else []
    return html, changed


def fix_sizes(site: Path = SITE) -> list[str]:
    """Write into the site's pages the sizes of their pictures' files (`sized`); return a line
    per change. The dark copies' sizes are the files' own: a line of wrong_sizes, never
    written."""
    changed: list[str] = []
    for page in sorted(site.glob("*.html")):
        html = page.read_text(encoding="utf-8", newline="")
        new, lines = sized(html, site)
        if new != html:
            page.write_text(new, encoding="utf-8", newline="")
        changed += [f"{page.name}: {line}" for line in lines]
    return changed


def missing_files(out: Path, docs: Path | None) -> list[str]:
    """Return what a whole run makes and is missing: each shot's PNG and WebP, thumbnails,
    og.png, the README's copies; and the PNG of the folder that no shot makes."""
    wanted = [
        out / f"{folder}{name}{suffix}" for name in SHOTS for folder in ("", "thumbs/") for suffix in (".png", ".webp")
    ]
    wanted += [out / "og.png", *(docs / f"{name}.png" for name in README_SHOTS if docs is not None)]
    missing = [
        path.relative_to(path.parents[1] if path.parent.name == "thumbs" else path.parent).as_posix()
        for path in wanted
        if not path.is_file()
    ]
    return missing + [
        f"{path.name} is made by no shot"
        for path in sorted(out.glob("*.png"))
        if path.stem not in SHOTS and path.name != "og.png"
    ]


@dataclass
class Run:
    """What one run took and, for what it did not, why: by shot, and "thumbs", "og" and "docs"."""

    started: float = field(default_factory=time.time)
    taken: list[str] = field(default_factory=list)
    why_not: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # What the site still declares at another size than its file; wrong_sizes: a dark copy.
    sizes: list[str] = field(default_factory=list)


def why_left(run: Run, out: Path, docs: Path | None, path: Path) -> str:
    """Why a file of site/shots/ or docs/screenshots/ was not written by this run."""
    stem, thumb = path.stem, path.parent.name == "thumbs"
    if docs is not None and path.parent == docs:
        return (
            run.why_not.get(stem)
            or run.why_not.get("docs")
            or ("not asked for (--only)" if stem not in run.taken else "not copied")
        )
    if stem == "og":
        return run.why_not.get("og", "og.png not drawn")
    if stem not in SHOTS:
        return "made by no shot of this script: left as it is"
    if stem in run.why_not:
        return run.why_not[stem]
    if stem not in run.taken:
        return "not asked for (--only)"
    return (
        run.why_not.get("thumbs", "its thumbnail or WebP copy not made")
        if thumb or path.suffix == ".webp"
        else "not written"
    )


def leftovers(run: Run, out: Path, docs: Path | None) -> dict[str, list[str]]:
    """Return the files of site/shots/ and docs/screenshots/ this run did not write, by reason,
    and every file of a shot asked for and not taken (a copy made from its earlier PNG is not
    this run's)."""
    files = [
        (out.parent, f)
        for f in (
            *out.glob("*.png"),
            *out.glob("*.webp"),
            *(out / "thumbs").glob("*.png"),
            *(out / "thumbs").glob("*.webp"),
        )
    ]
    files += [(docs.parent, f) for f in docs.glob("*.png")] if docs is not None and docs.is_dir() else []
    left: dict[str, list[str]] = {}
    for base, path in sorted(files):
        if path.stat().st_mtime < run.started - MTIME_SLACK_SEC or (path.stem in run.why_not and path.stem in SHOTS):
            left.setdefault(why_left(run, out, docs, path), []).append(path.relative_to(base).as_posix())
    return left


# A file's time is the system's coarse clock, which may be a little behind time.time().
MTIME_SLACK_SEC = 1.0
NEVER_MADE_HERE = "not made by this script: the icons (scripts/make-icon.py; ui/public/icons by hand), and GitHub's link preview, a setting of the repository (upload site/shots/og.png)"


def say_what_was_left(run: Run, out: Path, docs: Path | None) -> int:
    """Say at the end of a run what was asked for and not taken, files not written, extras made
    otherwise and sizes declared wrongly; return the counts (a run with no --only exits 1 for
    any)."""
    for note in run.notes:
        print(f"note: {note}")
    not_taken = {name: why for name, why in run.why_not.items() if name in SHOTS}
    for name, why in not_taken.items():
        print(f"not taken: {name}: {why}")
    left = leftovers(run, out, docs)
    for why, names in left.items():
        print(f"not retaken ({why}): {len(names)} files: {', '.join(names)}")
    for line in run.sizes:
        print(f"site, at another size (--check fails on it): {line}")
    if not left and not not_taken and not run.sizes:
        print("everything of site/shots/ and docs/screenshots/ was written by this run")
    print(NEVER_MADE_HERE)
    return len(not_taken) + sum(len(names) for names in left.values()) + len(run.sizes)


# ---- the run

EXTRA_DAEMONS = {
    "updating": ("update", "update-dark"),
    "receiving": ("beacon-rx", "beacon-rx-dark", "phone-beacon-rx", "phone-beacon-rx-dark"),
    "moving": ("beacon-gps", "beacon-gps-dark"),
    # The shots each extra daemon is for (a copy of the day's folder, other radios).
    "skeds": ("hf-tests", "hf-tests-dark"),
    "layered": ("layers", "layers-dark"),
}


def docs_folder(out: Path, docs: Path) -> Path:
    """Return `docs`, or `none` when `out` is the run's own folder and `docs` is the default."""
    return (
        Path("none") if out.resolve() != (SITE / "shots").resolve() and docs == ROOT / "docs" / "screenshots" else docs
    )


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "site" / "shots", help="where the PNG files go (default %(default)s)"
    )
    parser.add_argument(
        "--docs",
        type=Path,
        default=ROOT / "docs" / "screenshots",
        help="where the README's shots are copied (default %(default)s); 'none' leaves them out",
    )
    parser.add_argument("--only", nargs="*", metavar="NAME", help=f"take only these of: {', '.join([*SHOTS, *EXTRAS])}")
    parser.add_argument(
        "--basemap",
        type=Path,
        default=ROOT / "data" / "basemap.pmtiles",
        help="a PMTiles map of the area for street level (default %(default)s); without it only the placeholder is drawn",
    )
    parser.add_argument(
        "--chromium",
        default=os.environ.get("CHROMIUM"),
        help="the browser's executable, when Playwright's own is not installed",
    )
    parser.add_argument(
        "--no-sandbox",
        action="store_true",
        help="start the browser without its sandbox (a container, a user namespace that is refused)",
    )
    parser.add_argument("--keep", action="store_true", help="keep the temporary data folders and say where they are")
    parser.add_argument(
        "--check",
        action="store_true",
        help="take nothing: say what of site/shots/ and docs/screenshots/ is missing and which picture of site/ is declared at another size than its file; exit 1 for any",
    )
    args = parser.parse_args(argv)
    args.docs = docs_folder(args.out, args.docs)
    docs = None if args.docs.name == "none" else args.docs
    if args.check:
        found = [*missing_files(args.out, docs), *wrong_sizes(SITE)]
        for line in found:
            print(line)
        return 1 if found else 0
    # The guide's shots first: its daemon hears the day's air, and its table must be empty.
    chosen = sorted(args.only or SHOTS, key=lambda name: not name.startswith("setup"))
    if unknown := [n for n in chosen if n not in SHOTS and n not in EXTRAS]:
        parser.error(f"no such shot: {', '.join(unknown)}")
    if (
        not args.basemap.exists()
        and any(n in SHOTS for n in chosen)
        and (args.only is None or args.out.resolve() == (SITE / "shots").resolve())
    ):
        parser.error(
            f"there is no street map at {args.basemap}: name one with --basemap FILE (the site's shots are not drawn on the placeholder map)"
        )
    try:
        import PIL  # noqa: F401

        if any(n in SHOTS for n in chosen):
            import playwright.async_api  # noqa: F401
    except ImportError as e:
        parser.error(
            f"{e.name} is not installed: run it with uv run --with playwright --with pillow (and playwright install chromium once)"
        )
    # No daemon of the shots asks the version page: the header shows no newer-version link.
    os.environ["NEOAPRS_UPDATE_CHECK"] = "0"
    # The day has a message that fails, on purpose: the log's warning about it is not news.
    logging.getLogger("neoaprs").setLevel(logging.ERROR)
    run = Run()
    taking = [n for n in chosen if n in SHOTS and n not in run.why_not]
    args.out.mkdir(parents=True, exist_ok=True)
    if taking:
        if not args.basemap.exists():
            run.notes.append(f"the street maps are the placeholder: there is no {args.basemap} (--basemap)")
        await take(args, taking, run)
    made_from_all = args.only is None or "thumbs" in chosen
    if made_from_all or run.taken:
        make_thumbs(
            args.out, None if made_from_all else set(run.taken), skip={name for name in run.why_not if name in SHOTS}
        )
    else:
        run.why_not["thumbs"] = "no shot taken"
    if args.only is None or "og" in chosen or "map" in run.taken:
        if not make_og(args.out):
            run.why_not["og"] = "there is no map.png to draw it from"
        elif "map" not in run.taken:
            run.notes.append("og.png is drawn from a map.png of an earlier run")
    else:
        run.why_not["og"] = "drawn only by a run with everything, --only og or --only map"
    if docs is None:
        run.why_not["docs"] = "--docs none"
    if args.out.resolve() == (SITE / "shots").resolve():
        for line in fix_sizes(SITE):
            print(f"site: {line}")
        run.sizes = wrong_sizes(SITE)
    left = say_what_was_left(run, args.out, docs)
    return 1 if args.only is None and left else 0


async def take(args: argparse.Namespace, chosen: list[str], run: Run) -> None:
    """Take the shots `chosen` into args.out (the README's into args.docs); `run` records why any
    is not taken."""
    from playwright.async_api import async_playwright

    work = Path(tempfile.mkdtemp(prefix="neoaprs-shots-"))
    radio = demoscene.DemoRadio()
    await radio.start()
    daemons: list[Daemon] = []
    servers: list[asyncio.Server] = []
    gpsds: list[asyncio.subprocess.Process] = []
    traffics: list[asyncio.subprocess.Process] = []
    try:
        data, ids = await prepare(work, radio, args.basemap if args.basemap.exists() else None)
        wanted = {key for key, shots in EXTRA_DAEMONS.items() if set(shots) & set(chosen)}
        for key in wanted:
            # Each extra daemon on a copy of the day, made while no daemon runs on it.
            copy_data(data, work / key)
        main_daemon = Daemon(data)
        daemons.append(main_daemon)
        # Its Dummy radios make up their air from its start: HF cities beacon within two minutes.
        url = await main_daemon.start()
        (work / "fresh").mkdir()
        if (data / "basemap.pmtiles").exists():
            put_map(data / "basemap.pmtiles", work / "fresh" / "basemap.pmtiles")
        # A new installation: no radio.
        fresh = Daemon(work / "fresh")
        daemons.append(fresh)
        fresh_url = await fresh.start() if {"setup", "setup-dark"} & set(chosen) else ""
        print("the page:", url, " the fresh one:", fresh_url)

        async def started(daemon: Daemon) -> str:
            daemons.append(daemon)
            return await daemon.start()

        async def updating() -> str:
            versions = await serve_version(UPDATE_TO)
            servers.append(versions)
            neoaprs_db_set(work / "updating", "update/url", f"http://{demoscene.HOST}:{port_of(versions)}/version.php")
            return await started(Daemon(work / "updating", env={"NEOAPRS_INSTALL_KIND": "windows-installer"}))

        async def receiving() -> str:
            neoaprs_db_set(work / "receiving", "station/transmit", "false")
            neoaprs_db_set(work / "receiving", "beacon/interval_min", "0")
            return await started(Daemon(work / "receiving"))

        async def moving() -> str:
            gpsd = await start_gps_replay()
            gpsds.append(gpsd)
            assert gpsd.stdout is not None
            address = (await asyncio.wait_for(gpsd.stdout.readline(), 20)).decode().strip()
            # 30 is On for a moving station: SmartBeaconing, travelling by car as by default.
            for key, value in {"gps/source": "gpsd", "gps/host": address, "beacon/interval_min": "30"}.items():
                neoaprs_db_set(work / "moving", key, value)
            return await started(Daemon(work / "moving"))

        async def skeds() -> str:
            board, versions = await serve_json(made_up_board(datetime.now(UTC))), await serve_version(VERSION)
            servers.extend((board, versions))
            neoaprs_db_set(work / "skeds", "update/url", f"http://{demoscene.HOST}:{port_of(versions)}/version.php")
            return await started(
                Daemon(
                    work / "skeds",
                    env={
                        "NEOAPRS_UPDATE_CHECK": "1",
                        "NEOAPRS_SKEDS_URL": f"http://{demoscene.HOST}:{port_of(board)}/skeds.json",
                    },
                )
            )
            # The board is read with the update check, and only from a server on this computer.

        async def layered() -> str:
            traffics.append(await start_traffic())
            for key, value in LAYERS_SETTINGS.items():
                # Aircraft and Ships read My own receiver, the made-up one.
                neoaprs_db_set(work / "layered", key, value)
            return await started(Daemon(work / "layered"))

        starts: dict[str, Callable[[], Awaitable[str]]] = {
            "updating": updating,
            "receiving": receiving,
            "moving": moving,
            "skeds": skeds,
            "layered": layered,
        }
        urls: dict[str, str] = {}
        for key in sorted(wanted):
            try:
                urls[key] = await starts[key]()
            except (RuntimeError, TimeoutError, OSError, subprocess.CalledProcessError) as e:
                run.why_not.update(
                    {name: f"its daemon did not come up: {e}" for name in EXTRA_DAEMONS[key] if name in chosen}
                )
        async with async_playwright() as p:
            options: dict[str, Any] = {"args": ["--no-sandbox"] if args.no_sandbox else []}
            if args.chromium:
                options["executable_path"] = args.chromium
            browser = await p.chromium.launch(**options)
            shots = Shots(browser, url, args.out)
            shots.update_url, shots.receive_url, shots.moving_url = (
                urls.get("updating", ""),
                urls.get("receiving", ""),
                urls.get("moving", ""),
            )
            shots.skeds_url, shots.radios, shots.layers_url = urls.get("skeds", ""), ids, urls.get("layered", "")
            for name in chosen:
                if name in run.why_not:
                    continue
                try:
                    await SHOTS[name](shots, fresh_url)
                    run.taken.append(name)
                # A shot that fails is said at the end; the others are taken.
                except Exception as e:
                    run.why_not[name] = f"failed: {e.__class__.__name__}: {str(e).splitlines()[0] if str(e) else ''}"
                    print(f"{name}: {run.why_not[name]}")
                    await shots.close_left()
            await browser.close()
        if args.docs.name != "none":
            args.docs.mkdir(parents=True, exist_ok=True)
            for name in README_SHOTS:
                if (args.out / f"{name}.png").exists() and name in run.taken:
                    shutil.copyfile(args.out / f"{name}.png", args.docs / f"{name}.png")
    finally:
        for daemon in daemons:
            await daemon.stop()
        for gpsd in gpsds:
            if gpsd.returncode is None:
                gpsd.terminate()
                await gpsd.wait()
        for traffic in traffics:
            await stop_process(traffic)
        for server in servers:
            server.close()
        await radio.stop()
        if args.keep:
            print("kept:", work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
