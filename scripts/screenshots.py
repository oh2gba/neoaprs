"""Takes the screenshots of the README and the project page (site/): a daemon of its own on a temporary data folder, a made-up day on the air (scripts/demoscene.py), Chromium through Playwright.

    uv run --with playwright --with pillow python scripts/screenshots.py                  # everything: every shot light and dark into site/shots/, their thumbnails and WebP copies, og.png,
                                                                                          # seven of them into docs/screenshots/, and the sizes site/index.html declares made those of the files
    uv run --with playwright --with pillow python scripts/screenshots.py --only map weather    # these, with their thumbnails and WebP copies (og.png too when map is one of them)
    python scripts/screenshots.py --chromium /path/to/chrome --no-sandbox                  # a browser Playwright did not install, or one that cannot make its sandbox
    python scripts/screenshots.py --check                                                  # no browser: every shot has its files, and every picture of site/ is declared at the size of its file

Nothing touches a radio: the daemon's TNC is a KISS server on a TCP port of the loopback that this script serves (the `kiss-tcp` profile), and the fresh folder of the setup guide is given that port on the
command line. The HF radio of the two HF shots is given through the page, as the operator gives it (scripts/smoke.py `give_radio`: the radio commands). The version
beside Check now is hidden in every shot and the newer version of the update shot is made from VERSION, so the shots do not go old with a release: they are retaken when the page changes. The map for street level is linked or copied from a PMTiles file you name (`--basemap`, default `data/basemap.pmtiles` of this clone; it is only read): a run into site/shots/ or with no --only refuses to start without it, since the placeholder map would replace the site's. Needs Playwright and, to
make the PNG files small, Pillow; `playwright install chromium` fetches the browser. Needs `uv sync` first (or `uv run`, which does it) so that `neoaprs` is importable.

At the end the run says what of site/shots/ and docs/screenshots/ it did not write, and why (not asked for, a shot that needs what is not here such as the Mercury program, a shot that failed), and a picture of site/
still declared at another size than its file: a run with no --only that leaves anything exits 1. What it never makes is said too: the icons (scripts/make-icon.py) and GitHub's link preview, a setting of the repository."""
import argparse
import asyncio
import io
import logging
import os
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
from pathlib import Path, PurePosixPath
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ICON = ROOT / "neoaprs" / "desktop" / "icon.png"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import demoscene                                                  # noqa: E402  (the scene needs the path above)
import smoke                                                      # noqa: E402  (the page's socket and the radios on either wire)
from neoaprs import VERSION                                       # noqa: E402
from neoaprs.controller import Controller                         # noqa: E402
from neoaprs import mercury as mercuryrules                        # noqa: E402
from neoaprs.mercuryhelper import find as find_mercury             # noqa: E402
from neoaprs.mercuryspeaker import SpeakerAudio                    # noqa: E402

DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}
TABLET = {"width": 1024, "height": 768}
LIMIT_KB = 480                                                    # a PNG is made smaller than this (colours are reduced when it must be)
README_SHOTS = ("map", "weather", "messages", "beacon", "objects", "bulletins", "setup")
SETTINGS = {
    "station/call": "OH2GBA", "station/lat": f"{demoscene.HOME[0]}", "station/lon": f"{demoscene.HOME[1]}", "station/symbol_table": "/", "station/symbol_code": "-",
    "station/comment": "NeoAPRS in Espoo", "beacon/power_w": "5", "beacon/antenna_height_m": "10", "beacon/antenna_gain_db": "3", "messages/alert": "false", "radio/1/tcp_host": demoscene.HOST,
}
RADIO_TYPE = "kiss-tcp"                                              # the operator's radio, radio 1: the demo's own KISS TNC over TCP
AFTER_THE_DAY = {"beacon/interval_min": "30", "station/status": "145.500MHz QRV", "messages/alert": "true", "web/network": "true"}          # (the day is played without the alert command, the beacon timer and the status: the page's daemon starts them)
GPSD_PORT = 2947                                                    # (gpsd's usual port: what the fake gpsd of the beacon-gps shot listens on when it is free)
SHOWN_KEY = "k7m2-x9pq-4hrt"                                       # what the Settings shot shows as the access key, and the addresses: the daemon's own key is made at random for the run and never shown
SHOWN_URLS = ["http://192.168.1.20:7303/", "http://neoaprs-pi.local:7303/"]


class Daemon:
    """`python -m neoaprs` as a child process, its page's port read from its log."""

    def __init__(self, data: Path, *extra: str, env: dict[str, str] | None = None) -> None:
        self.data, self.extra, self.env = data, extra, env or {}
        self.proc: asyncio.subprocess.Process | None = None
        self.url = ""
        self.log: list[str] = []

    async def start(self) -> str:
        env = {k: v for k, v in os.environ.items() if not k.startswith("NEOAPRS_")}
        env["NEOAPRS_UPDATE_CHECK"] = "0"                        # (a made-up day: the daemon does not ask the version page)
        env["NEOAPRS_SERIAL_PATTERN"] = "/nonexistent/none*"     # (the search for the radio looks at ports that match nothing: no serial device of this machine is ever opened)
        env["NEOAPRS_NO_DEVICES"] = "1"                          # (no device, sound card or Mercury of this machine and nothing but this computer, whatever a shot sets: neoaprs/nodevices.py; the Mercury of the settings-hf shot is given by --hf-port)
        env.update(self.env)
        self.proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "neoaprs", "--data", str(self.data), "--web-port", "0", *self.extra, env=env, cwd=ROOT,
                                                         stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        asyncio.create_task(self._drain())
        logfile = self.data / "neoaprs.log"                      # (the log has the line; stderr only the warnings)
        async with asyncio.timeout(60):
            while not self.url:
                await asyncio.sleep(0.2)
                if self.proc.returncode is not None:
                    raise RuntimeError("the daemon ended:\n" + "\n".join(self.log[-20:]))
                if logfile.exists() and (found := re.search(r"web page at (http://\S+?)/?\s", logfile.read_text(errors="replace") + "\n")):
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


async def start_gps_replay() -> asyncio.subprocess.Process:
    """`neoaprs gps-replay`: a gpsd that is not one, on a free port of the loopback, which drives a made-up car round a block that starts at the home of the scene, a little faster than real time (the daemon of the beacon-gps shot reads it)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("NEOAPRS_")}
    with socket.socket() as probe:
        try:
            probe.bind((demoscene.HOST, GPSD_PORT))                  # (gpsd's own port when it is free, as the My station tab then shows what a gpsd user knows, else any free one)
            port = GPSD_PORT
        except OSError:
            port = 0
    return await asyncio.create_subprocess_exec(sys.executable, "-m", "neoaprs", "gps-replay", "--port", str(port), "--at", f"{demoscene.HOME[0]},{demoscene.HOME[1]}", "--kmh", "45", "--interval", "0.5",
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=env, cwd=ROOT)


def neoaprs_db_set(data: Path, key: str, value: str) -> None:
    subprocess.run([sys.executable, "-m", "neoaprs", "db", "--data", str(data), "set", key, value], check=True, capture_output=True, cwd=ROOT)


def neoaprs_db_add_radio(data: Path, radio_type: str) -> None:
    """A radio of the type added to the data folder, before its daemon's first start: the database numbers it."""
    subprocess.run([sys.executable, "-m", "neoaprs", "db", "--data", str(data), "radios", "add", radio_type], check=True, capture_output=True, cwd=ROOT)


async def give_hf_radio(url: str, radio_type: str, values: dict[str, str]) -> None:
    """The HF radio of a daemon that is up, given through its page as the operator gives it (smoke.give_radio: `radio_add` or `radio_change` and its own keys). `neoaprs db set` of an HF key is refused on a folder whose daemon ran without an HF radio, which every copy of the day's folder is."""
    page = await smoke.PageSocket.open(url)
    try:
        await hf_radio_given(page, radio_type, values, 60.0)
    finally:
        page.close()


async def hf_radio_given(page: smoke.PageSocket, radio_type: str, values: dict[str, str], seconds: float) -> None:
    """give_hf_radio on an open socket. A Mercury radio is the one --hf-port names (the station's first Mercury radio: the lowest id of one not removed), and its modem, the Mercury on pipes, must be `running`
    before its shot is taken: another Mercury radio before it, or a modem that does not come up, is a Failure, which leaves its shots out with the reason, never a picture of a Mercury radio with no modem."""
    id = await smoke.give_radio(page, "hf", radio_type, values, seconds)
    if radio_type != "mercury":
        return
    first = min((int(key) for key, row in (page.topics.get(smoke.RADIOS) or {}).items() if row.get("type") == "mercury" and not row.get("removed")), default=id)
    if first != id:
        raise smoke.Failure(f"the Mercury radio given is radio {id}, and --hf-port names radio {first}")
    await page.until("the Mercury modem of the HF radio running", lambda p: smoke.modem_state(p.topics, "hf", id) == "running", seconds)


def put_map(source: Path, target: Path) -> None:
    """The map file in a data folder: the page's server does not follow a symbolic link out of the folder, so it is a hard link, else a copy (the source is only read)."""
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def copy_data(source: Path, target: Path) -> None:
    """A copy of the operator's data folder (a daemon is not running on it): the map is linked, not copied."""
    shutil.copytree(source, target, copy_function=lambda a, b: put_map(Path(a), Path(b)) if str(a).endswith(".pmtiles") else shutil.copy2(a, b))


async def serve_version(version: str) -> asyncio.Server:
    """A version page on a port of the loopback that says `version` is the latest: the daemon of the update shot asks it, and nothing else is ever asked."""
    body = f'{{"version": "{version}", "url": "https://github.com/oh2gba/neoaprs/releases/tag/v{version}", "message": ""}}'.encode()

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    return await asyncio.start_server(answer, demoscene.HOST, 0)


def next_version(version: str) -> str:
    """The made-up newer version the update shot's version page announces: the patch number of `version` plus one (0.8.0 is followed by 0.8.1; 1.0.0-rc1 by 1.0.1), so that no number is kept by hand here."""
    major, minor, patch = version.split("-")[0].split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


UPDATE_TO = next_version(VERSION)                                  # (the version page of the update shot says this one is out: always one past the version of this tree)
# The "NeoAPRS <version>" beside Check now is hidden in every shot (the space stays, so nothing moves), so that a new version makes no shot old: the shots are retaken when the page changes, not at each
# release. The one shot that still names versions is update.png: UPDATE_TO, and the installed one in the dialog's "You have NeoAPRS ...". (The page allows an inline style sheet: style-src
# 'unsafe-inline' of neoaprs/web/headers.py.)
HIDE_VERSION = ".updateversion { visibility: hidden; }"


async def prepare(work: Path, radio: demoscene.DemoRadio, basemap: Path | None) -> Path:
    """The data folder of the operator: a database with the settings, the map, and the day played into it."""
    data = work / "demo"
    data.mkdir()
    ctl = Controller(data)
    await ctl.open_database()
    assert ctl.db is not None
    await ctl.db.close()
    neoaprs_db_add_radio(data, RADIO_TYPE)
    for key, value in {**SETTINGS, "radio/1/tcp_port": str(radio.port)}.items():
        neoaprs_db_set(data, key, value)
    if basemap is not None:
        put_map(basemap, data / "basemap.pmtiles")
    played = await demoscene.history(data, radio)
    print(f"the day: {played} events, {len(radio.sent)} frames sent to the radio")
    letters = "abcdefghjkmnpqrstuvwxyz23456789"
    neoaprs_db_set(data, "web/key", "-".join("".join(secrets.choice(letters) for _ in range(4)) for _ in range(3)))
    for key, value in AFTER_THE_DAY.items():
        neoaprs_db_set(data, key, value)
    return data


# ---- the browser

class Shots:
    def __init__(self, browser: Any, url: str, out: Path) -> None:
        self.browser, self.url, self.out = browser, url, out
        self.written: dict[str, int] = {}
        self.update_url = ""                                       # the page of the daemon that has an update on offer (the "update" shot)
        self.receive_url = ""                                      # the page of the daemon that is set to RX only (the "beacon-rx" shot)
        self.moving_url = ""                                       # the page of the daemon that follows a GPS (the "beacon-gps" shot)
        self.hf_url = ""                                           # the page of the daemon with the HF radio on as the Dummy HF radio (the "stations-hf" shot)
        self.hf_mercury_url = ""                                   # the page of the daemon whose HF radio is the Mercury modem, a real one on pipes that hears silence (the "settings-hf" shot)
        self.scheme = "light"                                      # the colour scheme of the shots being taken; a dark one is saved as NAME-dark.png
        self.contexts: list[Any] = []                              # the browser contexts of the shot being taken (a shot that fails leaves its own open: they are closed after it)
        self.started = asyncio.get_running_loop().time()

    async def since_start(self, seconds: float) -> None:
        """Waits until the daemon has run this long (the first beacon and status of its timers go out some seconds after the start)."""
        left = self.started + seconds - asyncio.get_running_loop().time()
        if left > 0:
            await asyncio.sleep(left)

    async def page(self, size: dict[str, int], scheme: str | None = None, tab: str = "stations", view: tuple[float, float, float] | None = None, panel: int | None = None,
                   wx_hours: str | None = None, url: str | None = None, wait_ms: int = 5000, scale: int = 1, headers: dict[str, str] | None = None,
                   phone_view: str | None = None, locale: str = "en-GB") -> Any:
        context = await self.browser.new_context(viewport=size, color_scheme=scheme or self.scheme, device_scale_factor=scale, locale=locale, timezone_id="Europe/Helsinki",
                                                 extra_http_headers=headers)
        keys = {"tab": tab, "panel": "open"}
        if view:
            keys["mapview"] = f'{{"lat":{view[0]},"lon":{view[1]},"zoom":{view[2]}}}'
        if panel:
            keys["panelwidth"] = str(panel)
        if wx_hours:
            keys["wxhours"] = wx_hours
        if phone_view:
            keys["view"] = phone_view                              # (a phone shows the map or the panel, one at a time)
        script = "".join(f"try{{localStorage.setItem('NeoAPRS.{k}',{v!r})}}catch(e){{}};" for k, v in keys.items())
        await context.add_init_script(script)
        self.contexts.append(context)
        page = await context.new_page()
        await page.goto(url or self.url)
        await page.add_style_tag(content=HIDE_VERSION)
        await page.wait_for_timeout(wait_ms)
        return page

    async def save(self, page: Any, name: str, clip: dict[str, int] | None = None) -> None:
        await page.mouse.move(2, 2)                                # (the pointer is not left on a row or a marker)
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
    """The PNG optimised: re-saved with the best compression, and with its colours reduced (adaptive palette) only when it is still over the limit."""
    from PIL import Image
    image = Image.open(io.BytesIO(png)).convert("RGB")
    for colours in (0, 256, 192, 128, 96):
        buffer = io.BytesIO()
        (image if colours == 0 else image.quantize(colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)).save(buffer, "PNG", optimize=True)
        if buffer.tell() <= LIMIT_KB * 1024 or colours == 96:
            return buffer.getvalue()
    raise AssertionError("unreachable")


async def settle(page: Any, ms: int = 1500) -> None:
    await page.wait_for_timeout(ms)


async def open_stations_tab(page: Any) -> None:
    """The Stations tab is the one a page opens on, and the second of the bar: it is in the row at every width of the panel but the narrowest, where it is under the More button, which a phone's page has under its Map button."""
    tab = page.locator("#tab-stations")
    if await tab.is_visible():
        await tab.click()
        return
    await page.locator("#tabmenu-button").click()
    await page.get_by_role("menuitem", name="Stations").click()


async def pick_station(page: Any, call: str, wait: int = 4500, add: bool = False) -> None:
    """The row of `call` in the Stations table clicked: its card opens; with `add` (Ctrl+click) beside the cards that are open."""
    await open_stations_tab(page)
    await page.locator("#pane-stations tbody tr", has_text=call).first.click(modifiers=["Control"] if add else [])
    await page.wait_for_timeout(wait)


# the views of the map: (lat, lon, zoom)
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
    await pick_station(page, "OH2ZMA-9")
    await s.save(page, "station")


async def shot_station_details(s: Shots, _: str) -> None:
    """The card of a station that runs a Kenwood TH-D74 with Details open: the Device row, the antenna of its PHG report with the arrow of the direction it favours, and the Packets, in all and in the last hour."""
    page = await s.page(DESKTOP, view=(60.232, 24.946, 10.3), panel=480)                    # (a wide map: the station's marker is clear of its card at the bottom left)
    await pick_station(page, "OH2ZPK", wait=2500)
    await page.locator('.cardstack .card[data-call="OH2ZPK"]').get_by_text("Details", exact=True).click()
    await settle(page, 800)
    await s.save(page, "station-details")


async def shot_weather(s: Shots, _: str) -> None:
    """Two weather stations, their cards side by side over the map: the same graphs, each on the same value axis in both."""
    page = await s.page(DESKTOP, view=(60.08, 24.62, 9.6), panel=560)                      # (a map wide enough for two whole cards: the oldest card closes when there is not)
    await pick_station(page, "OH2ZWB", wait=1500)
    await pick_station(page, "OH2ZWA", add=True)
    await s.save(page, "weather")


async def shot_cards(s: Shots, _: str) -> None:
    """Two stations that can be messaged, their cards over the map with Close all and Message these 2 at its top left; the second card has been dragged by its head to another place, and the first stays where it was."""
    page = await s.page(DESKTOP, view=(60.20, 24.95, 9.6), panel=560)
    await pick_station(page, "OH2ZMA-9", wait=1500)
    await pick_station(page, "OH2ZPK", add=True)
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


async def shot_stations_menu(s: Shots, _: str) -> None:
    """The menu of a row of the Stations table, opened with a right-click: Message, the four questions, Show on map, Copy call, the QRZ page, Forget."""
    page = await s.page(DESKTOP, view=OVERVIEW, panel=900)
    row = page.locator("#pane-stations tbody tr", has_text="OH2ZMA-9").first                  # (a row near the top: its menu then fits the picture the project page crops it to)
    box = await row.bounding_box()
    assert box is not None
    await row.click(button="right", position={"x": min(box["width"] - 60, 330), "y": box["height"] / 2})
    await settle(page, 600)
    await s.save(page, "stations-menu")


async def shot_update(s: Shots, _: str) -> None:
    """The window of an update (the daemon of this shot is told by a version page of its own that a newer version is out, and plays a Windows install): what is new, Update now and the steps by hand."""
    page = await s.page(DESKTOP, tab="settings", view=CITY, panel=WIDE_PANEL, url=s.update_url)
    await page.locator("#set-update-now").click()                     # (Check now finds the newer version: the Update mark of the header and the Update button of the row say so)
    await settle(page, 1500)
    await page.locator(".updateline .btn").click()                    # (the button of the row opens the window of the update)
    await page.locator(".updatedialog-hand summary").click()
    await settle(page, 800)
    await s.save(page, "update")


async def open_thread(s: Shots, call: str, scale: int = 1, size: dict[str, int] = DESKTOP) -> Any:
    """The Messages tab, wide enough for the list beside the conversation (lib/layout.ts MESSAGES_WIDE), with the conversation of `call` open."""
    page = await s.page(size, tab="messages", view=CITY, panel=760, scale=scale)
    await page.locator("#pane-messages").get_by_text(call).first.click()
    await settle(page)
    await settle(page, 600)
    return page


async def shot_messages(s: Shots, _: str) -> None:
    page = await open_thread(s, "OH2ZPK")
    await s.save(page, "messages")


async def thread_clip(page: Any, most: int) -> dict[str, int]:
    """The thread of the open conversation from its top to the bottom of its last message (at most `most` pixels): the close-up of the chains."""
    await page.evaluate("document.querySelector('#pane-messages .bubbles').scrollTop = 0")
    box = await page.locator("#pane-messages .bubbles").bounding_box()
    last = await page.locator("#pane-messages .bubbles .bubble").last.bounding_box()
    height = min(round(last["y"] + last["height"] - box["y"]) + 12, round(box["height"]), most)
    return {"x": round(box["x"]), "y": round(box["y"]), "width": round(box["width"]), "height": height}


WIDE_PANEL = 760                                                         # (the width at which the tab bar shows all its tabs, so that the tab on show is seen: Beacon, Settings)
TALL = {"width": 1440, "height": 1250}                                  # (a taller window, so that the thread has room: the close-ups are cut out of it)


async def shot_chain(s: Shots, _: str) -> None:
    """The thread of the main conversation, close up: the delivery chain of each message, at twice the pixels."""
    page = await open_thread(s, "OH2ZPK", scale=2, size=TALL)
    await s.save(page, "chain", clip=await thread_clip(page, 760))


async def shot_chain_failed(s: Shots, _: str) -> None:
    """A message that failed after its four attempts."""
    page = await open_thread(s, "OH2ZXA", scale=2, size=TALL)
    await s.save(page, "chain-failed", clip=await thread_clip(page, 330))


async def shot_email(s: Shots, _: str) -> None:
    """The mail list with Check email over it, and a mail being written at the bottom: the address, the text and the characters left."""
    page = await s.page(DESKTOP, tab="email", view=CITY, panel=560)
    await page.fill("#mail-to", "jane@example.com")
    await page.fill("#mail-text", "Antenna is up, see you at the net")
    await settle(page, 400)
    await s.save(page, "email")


async def shot_bulletins(s: Shots, _: str) -> None:
    """The message board: the box to post to it (a draft in it, with the characters left), our two entries marked ours among the heard ones."""
    page = await s.page(DESKTOP, tab="bulletins", view=CITY, panel=560)
    await page.fill("#post-text", "Road works on the ring road, expect delays")
    await settle(page, 400)
    await s.save(page, "bulletins")


GPS_VIEW = (60.2285, 24.7225, 13.6)                                     # (the block of the made-up drive, which starts at HOME)
OBJECTS = (60.19, 24.749, 11.3)                                         # the view with all of our objects on it


async def shot_objects(s: Shots, _: str) -> None:
    """The Objects tab: our objects and items, how often each was sent and when it goes out next; they are on the map with the dashed ring of the ones that are ours."""
    page = await s.page(DESKTOP, tab="objects", view=OBJECTS, panel=560)
    await s.save(page, "objects")


async def shot_objects_form(s: Shots, _: str) -> None:
    """The form under the list of our objects with a row selected: the object NETCTRL in it, the button reading Save (no row selected, the same form adds an object and reads Add)."""
    page = await s.page(DESKTOP, tab="objects", view=OBJECTS, panel=560)
    await page.locator('#pane-objects .ownobject[data-name="NETCTRL"]').click()
    await settle(page, 600)
    await s.save(page, "objects-form")


async def shot_beacon(s: Shots, _: str) -> None:
    await s.since_start(45)
    page = await s.page(DESKTOP, tab="beacon", view=CITY, panel=WIDE_PANEL)
    await page.locator("#pane-beacon summary", has_text="Advanced").click()                        # (the Path choice: Recommended for the symbol)
    await settle(page, 400)
    await s.save(page, "beacon")


async def shot_beacon_de(s: Shots, _: str) -> None:
    """The My station tab of a browser that speaks German: the page starts in the browser's language (nine are there)."""
    await s.since_start(45)
    page = await s.page(DESKTOP, tab="beacon", view=CITY, panel=WIDE_PANEL, locale="de-DE")
    await page.locator("#pane-beacon summary").filter(has_text="Erweitert").click()
    await settle(page, 400)
    await s.save(page, "beacon-de")


GROUP_GAP = 8                                                           # (what the page leaves between two groups of the Settings tab: a picture starts and ends in the gap)
WHOLE_GROUPS = """([first, gap]) => {
    const pane = document.querySelector('#pane-settings');
    const form = pane.querySelector('.settings');
    form.style.paddingBottom = '700px';                                 // (room to scroll the group to the top: the end of the tab is not the end of the picture)
    const at = (e) => e.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop;
    const groups = [...form.children].filter((e) => e.tagName === 'FIELDSET');
    pane.scrollTop = first ? at(form.querySelector(first)) - gap : 0;
    const edge = pane.getBoundingClientRect().bottom;
    const cut = groups.find((g) => g.getBoundingClientRect().bottom > edge);
    if (!cut) return;
    const before = groups[groups.indexOf(cut) - 1];
    const end = Math.min(edge, before ? before.getBoundingClientRect().bottom + gap / 2 : cut.getBoundingClientRect().top);
    pane.style.clipPath = `inset(0 0 ${edge - end}px 0)`;               // (what is below the last whole group is not drawn: the panel's own colour shows)
}"""


async def whole_groups(page: Any, first: str | None = None) -> None:
    """The Settings tab shown in whole groups: the group `first` (a selector of its fieldset; none is the top of the tab) scrolled to the top of the panel, and the first group that does not end in the view not drawn, so that no row of a picture is cut at its edge."""
    await page.evaluate(WHOLE_GROUPS, [first, GROUP_GAP])
    await settle(page, 400)


async def made_up_web(page: Any) -> None:
    """Puts the made-up access key and addresses (and the usual KISS port) in place of the daemon's own on a page that shows the Settings tab: the machine's own address and name never appear in a shot."""
    await page.evaluate("""([key, urls]) => {
        const put = () => {
            const field = document.getElementById("set-web-key");
            if (field) field.value = key;
            for (const port of document.querySelectorAll('#set-tcp-port, [id$="-tcp_port"]')) port.value = "8001";       // (Direwolf's usual KISS port; the demo's own TNC listens where there was room. The field's id of today, and a radio's own, radio-ID-tcp_port, as 1.12 of the round names it)
            const inputs = [...document.querySelectorAll('[id^="set-web-url-"]')];
            while (inputs.length && inputs.length < urls.length) { const copy = inputs[0].cloneNode(true); inputs[0].parentElement.append(copy); inputs.push(copy); }
            inputs.forEach((input, i) => { if (i < urls.length) input.value = urls[i]; else input.remove(); });
        };
        put();
        setInterval(put, 25);                                   // (the page draws the settings again when the radio's state changes, and puts its own key and addresses back: they are put over again)
    }""", [SHOWN_KEY, SHOWN_URLS])


async def shot_settings_web(s: Shots, _: str) -> None:
    """Settings, the Web page group: the switch on, the access key and where to open the page (the daemon's own key and addresses are replaced by made-up ones on the screen)."""
    page = await s.page(DESKTOP, tab="settings", view=CITY, panel=560)                  # (the width the project page crops it to)
    await made_up_web(page)
    await whole_groups(page, "fieldset:has(#set-web-key)")
    await s.save(page, "settings-web")


async def shot_settings_tnc(s: Shots, _: str) -> None:
    """Settings, the TNC group opened by its arrow: the type of TNC, the port and the speed, Find my radio and the Terminal (a connected radio keeps it folded to its one line)."""
    page = await s.page(DESKTOP, tab="settings", view=CITY, panel=560)
    await made_up_web(page)
    await page.locator("#pane-settings .radiostatus .statushead").click()
    await settle(page, 600)
    await whole_groups(page, "fieldset:has(.radiostatus)")
    await s.save(page, "settings-tnc")


async def shot_beacon_rx(s: Shots, _: str) -> None:
    """The My station tab of a station that is set to RX only (the daemon's setting station/transmit: the RX only mark on the warn plate in the header, beside the title) and has the Beacon Off: the status block has its pill off on the warn plate and says RX only: nothing is sent, and what belongs to the beacon is grey."""
    page = await s.page(DESKTOP, tab="beacon", view=CITY, panel=WIDE_PANEL, url=s.receive_url)
    await settle(page, 400)
    await s.save(page, "beacon-rx")


async def shot_phone_beacon_rx(s: Shots, _: str) -> None:
    """A phone set to RX only with the Beacon Off: the RX only mark on the warn plate beside the title and, under the tab bar, the My station tab with its status block saying RX only: nothing is sent and the fields of the beacon grey."""
    page = await s.page(PHONE, tab="beacon", view=CITY, phone_view="panel", url=s.receive_url)
    await s.save(page, "phone-beacon-rx")


NEARBY = (60.19, 24.80, 8.5)                                            # (the map the range circle is fitted on is flown to by the page itself: this is only where it starts)


async def shot_nearby(s: Shots, _: str) -> None:
    """The Nearby tab with a digipeater selected: its row is highlighted and the map has been zoomed so that its whole range circle (from its PHG) is in view; the digipeater is OH2RCH-2 of Kumpula, which repeated most of what we heard."""
    page = await s.page(DESKTOP, tab="nearby", view=NEARBY, panel=640)                       # (wide enough for the help line of each list to be one line: the four lists end above the foot of the panel)
    await page.locator('#pane-nearby tr[data-call="OH2RCH-2"]').first.click()
    await settle(page, 3500)                                              # (the map flies to the circle)
    await s.save(page, "nearby")


async def shot_beacon_gps(s: Shots, _: str) -> None:
    """The My station tab of a moving station: Position is A GPS via gpsd (its address under it), the status block has the GPS with its fix and the line of SmartBeaconing under it, the Beacon choice is On (SmartBeaconing) and Travelling By car; our own station drives round a block on the map (the gpsd is `neoaprs gps-replay`)."""
    await s.since_start(80)
    page = await s.page(DESKTOP, tab="beacon", view=GPS_VIEW, panel=WIDE_PANEL, url=s.moving_url)
    await settle(page, 600)
    await s.save(page, "beacon-gps")


async def shot_phone_key(s: Shots, _: str) -> None:
    """What a phone on the network sees before it is let in: a request that says it came through a proxy counts as from the network, so the daemon asks for the key."""
    page = await s.page(PHONE, headers={"X-Forwarded-For": "192.168.1.50"}, wait_ms=3000)
    await page.fill("#access-key", SHOWN_KEY)
    await s.save(page, "phone-key")


async def shot_settings(s: Shots, _: str) -> None:
    page = await s.page(DESKTOP, tab="settings", view=CITY, panel=WIDE_PANEL)
    await made_up_web(page)
    await whole_groups(page)
    await s.save(page, "settings")


async def shot_packets(s: Shots, _: str) -> None:
    page = await s.page(DESKTOP, tab="packets", view=CITY, panel=760)
    await s.save(page, "packets")


HF_WORLD = (57.9, 20.2, 4.5)                                       # the view of the map that holds the Dummy HF radio's made-up stations (Turku to Warsaw) and the day's stations round Helsinki


SHOWN_CARDS = ["USB Audio CODEC", "Built-in Audio"]                 # what the Settings shot shows as the sound cards: the machine's own cards (which the daemon lists from the real Mercury) never appear in a shot


class PipeMercury:
    """The shipped Mercury started on its fifo backend for the "settings-hf" shot: it hears silence and plays into a pipe that is drained and not heard (the speaker thread with no player), keys nothing, and serves its KISS and control ports on the loopback for a daemon started with --hf-port, so that the HF radio's box shows the Mercury modem connected, with the sound card, the keying, Tune, Test and the frequency, and no sound card of this machine is opened."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.audio = SpeakerAudio(folder, player=lambda: None)
        self.proc: subprocess.Popen[bytes] | None = None
        self.kiss_port = 0

    def start(self) -> str:
        program = find_mercury() or find_mercury(ROOT / ".venv" / "tools")                  # (`uv run --with playwright` runs this in an environment of its own, whose prefix has no tools/: the checkout's venv has them)
        if program is None:
            raise RuntimeError("no Mercury in this checkout: build it with scripts/build-mercury --install")
        if not self.audio.prepare():
            raise RuntimeError("the pipes for Mercury could not be made")
        while True:
            with socket.socket() as a, socket.socket() as b:
                a.bind((demoscene.HOST, 0))
                port = a.getsockname()[1]
                try:
                    b.bind((demoscene.HOST, port + mercuryrules.CONTROL_PORT - mercuryrules.BROADCAST_PORT))
                except OSError:
                    continue
            break
        self.kiss_port = port
        ini = self.folder / "mercury-shot.ini"
        ini.write_text(mercuryrules.ini_text(mercuryrules.keying_of("vox")), encoding="utf-8")
        env = dict(os.environ)
        conf = Path(program[0]).resolve().parent / "share" / "alsa" / "alsa.conf"
        if conf.is_file():
            env["ALSA_CONFIG_PATH"] = str(conf)
        argv = [*program, "-C", str(ini), "-m", "1", "-x", "fifo", "-i", str(self.audio.capture), "-o", str(self.audio.playback), "-b", str(port), "-p", str(port + mercuryrules.CONTROL_PORT - mercuryrules.BROADCAST_PORT), "-P", "none"]
        self.proc = subprocess.Popen(argv, cwd=str(self.folder), stdin=subprocess.DEVNULL, stdout=(self.folder / "mercury-shot.log").open("wb"), stderr=subprocess.STDOUT, env=env)
        self.audio.start()
        return f"socket://{demoscene.HOST}:{port}"

    def stop(self) -> None:
        self.audio.stop()
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


async def shot_settings_hf(s: Shots, _: str) -> None:
    """Settings, the Radio group of a station with both radios: the FM radio box folded to its status line (its TNC is connected) and the HF radio box opened by its arrow, with the radio type (the Mercury modem, a real one on pipes), the sound card and the keying (the machine's own cards replaced by made-up names on the screen), Tune and Test, and the frequency."""
    page = await s.page(DESKTOP, tab="settings", view=CITY, panel=560, url=s.hf_mercury_url)
    await made_up_web(page)
    await page.locator("#pane-settings fieldset.subbox", has_text="HF radio").locator(".statushead").click()
    await settle(page, 600)
    await page.evaluate("""(names) => {
        const put = () => {
            const box = [...document.querySelectorAll("#pane-settings fieldset.subbox")].find((f) => f.textContent.includes("HF radio"));
            const selects = box ? [...box.querySelectorAll("select")] : [];
            const cards = selects[1];                              // (the type, the sound card, the keying)
            if (!cards) return;
            [...cards.options].forEach((option, i) => { if (i < names.length) option.textContent = names[i]; else option.remove(); });
            while (cards.options.length < names.length) { const o = document.createElement("option"); o.textContent = names[cards.options.length]; cards.append(o); }
        };
        put();
        setInterval(put, 25);
    }""", SHOWN_CARDS)
    await settle(page, 300)
    await whole_groups(page, "fieldset:has(.radiostatus)")
    await s.save(page, "settings-hf")


async def shot_stations_hf(s: Shots, _: str) -> None:
    """The Stations table of a station with both radios, the map zoomed out to hold both: the day's stations round Helsinki tagged FM, and the six made-up stations of the Dummy HF radio, hundreds of kilometres away, tagged HF. The HF radio is given through the page once the daemon is up; their first beacons come within two minutes of that."""
    page = await s.page(DESKTOP, tab="stations", view=HF_WORLD, panel=760, url=s.hf_url)
    rows = page.locator("#pane-stations tbody tr", has_text="HF")
    async with asyncio.timeout(170):
        while await rows.count() < 6:
            await page.wait_for_timeout(1000)
    await settle(page, 2500)
    await s.save(page, "stations-hf")


async def shot_phone_map(s: Shots, _: str) -> None:
    page = await s.page(PHONE, view=(60.19, 24.80, 9.4))
    await s.save(page, "phone-map")


async def shot_phone_bulletins(s: Shots, _: str) -> None:
    page = await s.page(PHONE, tab="bulletins", view=(60.19, 24.80, 9.4), phone_view="panel")
    await s.save(page, "phone-bulletins")


async def shot_phone_messages(s: Shots, _: str) -> None:
    """A phone shows one thing at a time: here the conversation, with its back arrow, the bubbles and the box to write in at the bottom."""
    page = await s.page(PHONE, tab="messages", view=CITY, phone_view="panel")
    await page.locator("#pane-messages").get_by_text("OH2ZPK").first.click()
    await settle(page)
    await s.save(page, "phone-messages")


async def shot_phone_weather(s: Shots, _: str) -> None:
    """A tap on a row of the Stations table shows the map and the card of the station as a sheet at the bottom, opened up with a tap on its grip."""
    page = await s.page(PHONE, tab="stations", view=(60.15, 24.80, 11), phone_view="panel")
    await pick_station(page, "OH2ZWA", wait=3000)
    await page.locator(".sheet-grip").click()                      # (a tap on the grip opens the sheet up: the graphs)
    await settle(page, 2500)
    await s.save(page, "phone-weather")


async def shot_tablet(s: Shots, _: str) -> None:
    """A tablet: the map and a panel of 380 to 420 px side by side, here the Messages tab with a conversation open."""
    page = await s.page(TABLET, tab="messages", view=CITY)
    await page.locator("#pane-messages").get_by_text("OH2ZPK").first.click()
    await settle(page)
    await s.save(page, "tablet")


async def shot_setup(s: Shots, fresh_url: str) -> None:
    """The guide of a folder with no call, at its Position step: the call typed in, the Location row (Choose on map and the place at its side) with its entry for the coordinates open from the start, as a station with no place has it."""
    page = await s.page(DESKTOP, url=fresh_url, wait_ms=3500)
    await page.locator(".setup input").first.fill("OH2GBA")
    await page.get_by_role("button", name="Next").click()
    await page.wait_for_timeout(600)
    await page.fill("#setup-lat", str(demoscene.HOME[0]))
    await page.fill("#setup-lon", str(demoscene.HOME[1]))
    await page.wait_for_timeout(2500)
    await s.save(page, "setup")


def thumbs_of(out: Path, names: set[str] | None = None, skip: Collection[str] = ()) -> list[Path]:
    """The shots whose thumbnails and WebP copies make_thumbs makes: with `names`, only those (the ones a run with --only took); else every PNG but og.png; never those of `skip`, the shots a run
    asked for and did not take, whose PNG is an earlier run's (copies made again from it would pass for this run's)."""
    return [path for path in sorted(out.glob("*.png")) if path.name != "og.png" and (names is None or path.stem in names) and path.stem not in skip]


def make_thumbs(out: Path, names: set[str] | None = None, skip: Collection[str] = ()) -> int:
    """thumbs/NAME.png next to each shot: 640 px wide (270 for a phone), what the page shows before a picture is opened; and NAME.webp beside every shot and thumb, which the page offers first; for the
    shots of thumbs_of. How many shots had theirs made."""
    from PIL import Image
    (out / "thumbs").mkdir(exist_ok=True)
    made = 0
    for path in thumbs_of(out, names, skip):
        image = Image.open(path).convert("RGB")
        width = 270 if path.name.startswith("phone-") else 640
        small = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS).quantize(128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        small.save(out / "thumbs" / path.name, optimize=True)
        image.save(path.with_suffix(".webp"), quality=82, method=6)                                       # (the page offers the WebP first: a third of the PNG's bytes)
        image.resize(small.size, Image.LANCZOS).save((out / "thumbs" / path.name).with_suffix(".webp"), quality=80, method=6)
        made += 1
    print(f"thumbs/: {made} shots' thumbnails, and a .webp beside each picture")
    return made


def _font(size: int, bold: bool) -> Any:
    from PIL import ImageFont
    names = ("NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "arialbd.ttf") if bold else ("NotoSans-Regular.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf")
    for name in names:
        for folder in ("", "/usr/share/fonts/truetype/noto/", "/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/truetype/liberation/", "C:/Windows/Fonts/"):
            try:
                return ImageFont.truetype(folder + name, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


PITCH = "A modern, easy-to-use APRS client for Windows, macOS, Linux and the Raspberry Pi"      # the systems as the site's own first lines name them (site/index.html: the title and the line under the name)
PITCH_WIDTH = 396                                                  # the room for the pitch beside the map: from its left edge (58) to 14 px before the map (468)


def lines_of(text: str, fits: Callable[[str], bool]) -> list[str]:
    """`text` cut at its spaces into lines that each fit (a word longer than the room is a line of its own)."""
    lines: list[str] = []
    for word in text.split():
        if lines and fits(f"{lines[-1]} {word}"):
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def make_og(out: Path) -> bool:
    """og.png, 1200x630: the map shot on the petrol of the icon, the name and the pitch beside it (what a link to the site shows); False when there is no map shot to draw it from."""
    from PIL import Image, ImageDraw
    source = out / "map.png"
    if not source.exists():
        return False
    card = Image.new("RGB", (1200, 630), (10, 42, 61))                # petrol #0a2a3d, the icon's tile
    shot = Image.open(source).convert("RGB")
    shot = shot.resize((round(shot.width * 0.62), round(shot.height * 0.62)), Image.LANCZOS)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, shot.width, shot.height), radius=18, fill=255)
    card.paste(shot, (468, 112), mask)
    draw = ImageDraw.Draw(card)
    draw.text((56, 150), "NeoAPRS", font=_font(84, True), fill=(255, 255, 255))
    font = _font(28, False)
    for i, line in enumerate(lines_of(PITCH, lambda text: draw.textlength(text, font=font) <= PITCH_WIDTH)):
        draw.text((58, 262 + i * 40), line, font=font, fill=(166, 215, 212))       # mint #a6d7d4, as the site's dark band has it on petrol: 9.4 to 1
    if ICON.exists():
        mark = Image.open(ICON).convert("RGBA").resize((72, 72), Image.LANCZOS)
        card.paste(mark, (58, 56), mark)
    card.save(out / "og.png", optimize=True)
    print("og.png")
    return True


EXTRAS = ("thumbs", "og")                                          # what is made from the shots, with no browser
SHOTS: dict[str, Shot] = {
    "map": shot_map, "stations": shot_stations, "station": shot_station, "weather": shot_weather, "messages": shot_messages, "email": shot_email, "bulletins": shot_bulletins,
    "objects": shot_objects, "objects-form": shot_objects_form, "beacon": shot_beacon, "settings": shot_settings, "packets": shot_packets, "phone-map": shot_phone_map, "phone-bulletins": shot_phone_bulletins, "phone-weather": shot_phone_weather,
    "cards": shot_cards, "stations-menu": shot_stations_menu, "update": shot_update, "beacon-de": shot_beacon_de, "phone-messages": shot_phone_messages, "tablet": shot_tablet, "setup": shot_setup, "chain": shot_chain, "chain-failed": shot_chain_failed, "settings-web": shot_settings_web, "phone-key": shot_phone_key,
    "station-details": shot_station_details, "settings-tnc": shot_settings_tnc, "beacon-rx": shot_beacon_rx, "phone-beacon-rx": shot_phone_beacon_rx,
    "nearby": shot_nearby, "beacon-gps": shot_beacon_gps, "settings-hf": shot_settings_hf, "stations-hf": shot_stations_hf,
}
DARK_TOO = ("map", "stations", "station", "weather", "messages", "email", "bulletins", "objects", "objects-form", "beacon", "settings", "packets", "phone-map", "phone-bulletins", "phone-weather", "cards", "stations-menu", "update", "beacon-de", "phone-messages", "tablet", "setup", "chain", "chain-failed", "settings-web", "phone-key", "station-details", "settings-tnc", "beacon-rx", "phone-beacon-rx", "nearby", "beacon-gps", "settings-hf", "stations-hf")


def in_the_dark(shot: Shot) -> Shot:
    async def dark(s: Shots, fresh_url: str) -> None:
        s.scheme = "dark"
        try:
            await shot(s, fresh_url)
        finally:
            s.scheme = "light"
    return dark


SHOTS.update({f"{name}-dark": in_the_dark(SHOTS[name]) for name in DARK_TOO})


# ---- the files: what a run leaves, and the sizes the site declares

SITE = ROOT / "site"
SITE_URL = "https://neo.oh2gba.eu/"                                # (where og:image points: its file is site/ under it)


def image_size(path: Path) -> tuple[int, int] | None:
    """The width and height of a PNG or WebP file read from its header (no Pillow needed); None for a file that is neither or cannot be read."""
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
    if chunk == b"VP8 ":                                            # (lossy: the frame's 14-bit sizes after its start code)
        return struct.unpack("<H", head[26:28])[0] & 0x3FFF, struct.unpack("<H", head[28:30])[0] & 0x3FFF
    if chunk == b"VP8L":                                            # (lossless: 14 bits each, less one, after the signature byte)
        bits = int.from_bytes(head[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X":                                            # (extended: the canvas, 24 bits each, less one)
        return int.from_bytes(head[24:27], "little") + 1, int.from_bytes(head[27:30], "little") + 1
    return None


IMG = re.compile(r"<img\b[^>]*>")
PICTURE = re.compile(r"<picture\b.*?</picture>", re.S)


def _attr(tag: str, name: str) -> str | None:
    found = re.search(rf'\b{name}="([^"]*)"', tag)
    return found.group(1) if found else None


def wrong_sizes(site: Path = SITE) -> list[str]:
    """What the pages of the site declare at another size than the file's: an <img> of a PNG or WebP of the site whose width and height are not the file's, the dark copy a <picture> offers in the same
    box at another size, and og:image:width and height against og.png; a line for each, [] when all agree."""
    wrong: list[str] = []
    for page in sorted(site.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        for tag in IMG.findall(html):
            src, size = _attr(tag, "src"), image_size(site / (_attr(tag, "src") or ""))
            if src is None or size is None:
                continue
            declared = (_attr(tag, "width"), _attr(tag, "height"))
            if declared != (str(size[0]), str(size[1])):
                wrong.append(f"{page.name}: {src} is declared {declared[0]}x{declared[1]}, the file is {size[0]}x{size[1]}")
        for picture in PICTURE.findall(html):
            tag = next(iter(IMG.findall(picture)), "")
            src = _attr(tag, "src") or ""
            dark = f"{PurePosixPath(src).with_suffix('')}-dark{PurePosixPath(src).suffix}"          # (an address of the page: its slashes, on Windows too)
            if f'srcset="{dark}"' in picture and (size := image_size(site / src)) is not None and (dark_size := image_size(site / dark)) not in (None, size):
                wrong.append(f"{page.name}: {dark} is {dark_size[0]}x{dark_size[1]} in the box of {src}, {size[0]}x{size[1]}")
        og = re.search(rf'<meta property="og:image" content="{re.escape(SITE_URL)}([^"]+)">', html)
        if og and (size := image_size(site / og.group(1))) is not None:
            for name, value in (("width", size[0]), ("height", size[1])):
                said = re.search(rf'<meta property="og:image:{name}" content="(\d+)">', html)
                if said and said.group(1) != str(value):
                    wrong.append(f"{page.name}: og:image:{name} says {said.group(1)}, {og.group(1)} is {value}")
    return wrong


def sized(html: str, site: Path) -> tuple[str, list[str]]:
    """A page with the width and height of each <img> of a file of the site made the file's, and og:image:width and height og.png's; and what changed."""
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
            html, count = re.subn(rf'(<meta property="og:image:{name}" content=")(?!{value}")\d+(">)', rf"\g<1>{value}\g<2>", html)
            changed += [f"og:image:{name} -> {value}"] if count else []
    return html, changed


def fix_sizes(site: Path = SITE) -> list[str]:
    """Writes into the pages of the site the sizes of their pictures' files (`sized`); what it changed, a line each. The dark copies' sizes are the files' own: a line of wrong_sizes, never written."""
    changed: list[str] = []
    for page in sorted(site.glob("*.html")):
        html = page.read_text(encoding="utf-8", newline="")
        new, lines = sized(html, site)
        if new != html:
            page.write_text(new, encoding="utf-8", newline="")          # (its line ends as they are: Windows would write CRLF into every line)
        changed += [f"{page.name}: {line}" for line in lines]
    return changed


def missing_files(out: Path, docs: Path | None) -> list[str]:
    """What a whole run makes and is not there: each shot's PNG and WebP, its thumbnail in both, og.png, and the README's copies; and the PNG of the folder that no shot makes."""
    wanted = [out / f"{folder}{name}{suffix}" for name in SHOTS for folder in ("", "thumbs/") for suffix in (".png", ".webp")]
    wanted += [out / "og.png", *(docs / f"{name}.png" for name in README_SHOTS if docs is not None)]
    missing = [path.relative_to(path.parents[1] if path.parent.name == "thumbs" else path.parent).as_posix() for path in wanted if not path.is_file()]
    return missing + [f"{path.name} is made by no shot" for path in sorted(out.glob("*.png")) if path.stem not in SHOTS and path.name != "og.png"]


@dataclass
class Run:
    """What one run took, and for what it did not, why: by shot, and by "thumbs", "og" and "docs" for what is made from the shots."""
    started: float = field(default_factory=time.time)
    taken: list[str] = field(default_factory=list)
    why_not: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)                 # what was made, but not as a run with everything makes it
    sizes: list[str] = field(default_factory=list)                 # what the site still declares at another size than its file once the sizes are written (wrong_sizes: a dark copy of another size)


def why_left(run: Run, out: Path, docs: Path | None, path: Path) -> str:
    """Why a file of site/shots/ or docs/screenshots/ was not written by this run."""
    stem, thumb = path.stem, path.parent.name == "thumbs"
    if docs is not None and path.parent == docs:
        return run.why_not.get(stem) or run.why_not.get("docs") or ("not asked for (--only)" if stem not in run.taken else "not copied")
    if stem == "og":
        return run.why_not.get("og", "og.png not drawn")
    if stem not in SHOTS:
        return "made by no shot of this script: left as it is"
    if stem in run.why_not:
        return run.why_not[stem]
    if stem not in run.taken:
        return "not asked for (--only)"
    return run.why_not.get("thumbs", "its thumbnail or WebP copy not made") if thumb or path.suffix == ".webp" else "not written"


def leftovers(run: Run, out: Path, docs: Path | None) -> dict[str, list[str]]:
    """The files of site/shots/ (its thumbnails too) and docs/screenshots/ this run did not write, by the reason; and every file of a shot asked for and not taken, whatever its time (a copy made
    again from its earlier PNG is not this run's picture)."""
    files = [(out.parent, f) for f in (*out.glob("*.png"), *out.glob("*.webp"), *(out / "thumbs").glob("*.png"), *(out / "thumbs").glob("*.webp"))]
    files += [(docs.parent, f) for f in docs.glob("*.png")] if docs is not None and docs.is_dir() else []
    left: dict[str, list[str]] = {}
    for base, path in sorted(files):
        if path.stat().st_mtime < run.started - MTIME_SLACK_SEC or (path.stem in run.why_not and path.stem in SHOTS):
            left.setdefault(why_left(run, out, docs, path), []).append(path.relative_to(base).as_posix())
    return left


MTIME_SLACK_SEC = 1.0                                              # (a file's time is the system's coarse clock, which may be a little behind time.time() when the run starts)
NEVER_MADE_HERE = "not made by this script: the icons (scripts/make-icon.py; ui/public/icons by hand), and GitHub's link preview, a setting of the repository (upload site/shots/og.png)"


def say_what_was_left(run: Run, out: Path, docs: Path | None) -> int:
    """The end of a run: the shots asked for and not taken with why, the files it did not write with why, what it made otherwise than a whole run would, and what the site still declares at another
    size than its file; how many shots, files and sizes were left (a run with no --only exits 1 for any, as --check does)."""
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

EXTRA_DAEMONS = {"updating": ("update", "update-dark"), "receiving": ("beacon-rx", "beacon-rx-dark", "phone-beacon-rx", "phone-beacon-rx-dark"), "moving": ("beacon-gps", "beacon-gps-dark"),
                 "hf": ("stations-hf", "stations-hf-dark"), "hf-mercury": ("settings-hf", "settings-hf-dark")}       # the shots each extra daemon is for (a copy of the day's folder, set otherwise)


def cannot_take() -> dict[str, str]:
    """The shots this checkout cannot take, with why."""
    if find_mercury() is None and find_mercury(ROOT / ".venv" / "tools") is None:
        return {name: "no Mercury in this checkout: scripts/build-mercury --install" for name in EXTRA_DAEMONS["hf-mercury"]}
    return {}


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "site" / "shots", help="where the PNG files go (default %(default)s)")
    parser.add_argument("--docs", type=Path, default=ROOT / "docs" / "screenshots", help="where the README's shots are copied (default %(default)s); 'none' leaves them out")
    parser.add_argument("--only", nargs="*", metavar="NAME", help=f"take only these of: {', '.join([*SHOTS, *EXTRAS])}")
    parser.add_argument("--basemap", type=Path, default=ROOT / "data" / "basemap.pmtiles", help="a PMTiles map of the area for street level (default %(default)s); without it only the placeholder is drawn")
    parser.add_argument("--chromium", default=os.environ.get("CHROMIUM"), help="the browser's executable, when Playwright's own is not installed")
    parser.add_argument("--no-sandbox", action="store_true", help="start the browser without its sandbox (a container, a user namespace that is refused)")
    parser.add_argument("--keep", action="store_true", help="keep the temporary data folders and say where they are")
    parser.add_argument("--check", action="store_true", help="take nothing: say what of site/shots/ and docs/screenshots/ is missing and which picture of site/ is declared at another size than its file; exit 1 for any")
    args = parser.parse_args(argv)
    docs = None if args.docs.name == "none" else args.docs
    if args.check:
        found = [*missing_files(args.out, docs), *wrong_sizes(SITE)]
        for line in found:
            print(line)
        return 1 if found else 0
    chosen = sorted(args.only or SHOTS, key=lambda name: not name.startswith("setup"))      # (the guide's shots first: its daemon hears the air of the day, our own bulletins repeated among it, and the guide's table is to be empty)
    if unknown := [n for n in chosen if n not in SHOTS and n not in EXTRAS]:
        parser.error(f"no such shot: {', '.join(unknown)}")
    if not args.basemap.exists() and any(n in SHOTS for n in chosen) and (args.only is None or args.out.resolve() == (SITE / "shots").resolve()):
        parser.error(f"there is no street map at {args.basemap}: name one with --basemap FILE (the site's shots are not drawn on the placeholder map)")
    try:
        import PIL  # noqa: F401
        if any(n in SHOTS for n in chosen):
            import playwright.async_api  # noqa: F401
    except ImportError as e:
        parser.error(f"{e.name} is not installed: run it with uv run --with playwright --with pillow (and playwright install chromium once)")
    os.environ["NEOAPRS_UPDATE_CHECK"] = "0"                          # (no daemon of the shots asks the version page: the header shows no newer-version link)
    logging.getLogger("neoaprs").setLevel(logging.ERROR)              # (the day has a message that fails, on purpose: the log's warning about it is not news)
    run = Run()
    run.why_not.update({name: why for name, why in cannot_take().items() if name in chosen})
    taking = [n for n in chosen if n in SHOTS and n not in run.why_not]
    args.out.mkdir(parents=True, exist_ok=True)
    if taking:
        if not args.basemap.exists():
            run.notes.append(f"the street maps are the placeholder: there is no {args.basemap} (--basemap)")
        await take(args, taking, run)
    made_from_all = args.only is None or "thumbs" in chosen
    if made_from_all or run.taken:
        make_thumbs(args.out, None if made_from_all else set(run.taken), skip={name for name in run.why_not if name in SHOTS})
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
    """Takes the shots `chosen` into args.out (and the README's into args.docs); what it took is in `run`, and for each it did not, why."""
    from playwright.async_api import async_playwright
    work = Path(tempfile.mkdtemp(prefix="neoaprs-shots-"))
    radio = demoscene.DemoRadio()
    await radio.start()
    daemons: list[Daemon] = []
    servers: list[asyncio.Server] = []
    gpsds: list[asyncio.subprocess.Process] = []
    modems: list[PipeMercury] = []
    try:
        data = await prepare(work, radio, args.basemap if args.basemap.exists() else None)
        wanted = {key for key, shots in EXTRA_DAEMONS.items() if set(shots) & set(chosen)}
        for key in wanted:
            copy_data(data, work / key)                                                               # (each extra daemon on a copy of the day, made while no daemon runs on it)
        main_daemon = Daemon(data)
        daemons.append(main_daemon)
        url = await main_daemon.start()
        radio.feed(demoscene.on_air("OH2ZMA-9", demoscene.position(60.164, 24.88, "/>", "Pekka on the road", course=96, knots=46), path="OH2RCH-2*", destination="APOT21"))    # (a packet heard just now: the radio status says when the last one came)
        (work / "fresh").mkdir()
        if (data / "basemap.pmtiles").exists():
            put_map(data / "basemap.pmtiles", work / "fresh" / "basemap.pmtiles")
        fresh = Daemon(work / "fresh", "--port", radio.url)
        daemons.append(fresh)
        fresh_url = await fresh.start() if {"setup", "setup-dark"} & set(chosen) else ""
        print("the page:", url, " the fresh one:", fresh_url)

        async def started(daemon: Daemon) -> str:
            daemons.append(daemon)
            return await daemon.start()

        async def updating() -> str:
            versions = await serve_version(UPDATE_TO)
            servers.append(versions)
            neoaprs_db_set(work / "updating", "update/url", f"http://{demoscene.HOST}:{versions.sockets[0].getsockname()[1]}/version.php")
            return await started(Daemon(work / "updating", env={"NEOAPRS_INSTALL_KIND": "windows-installer"}))        # (a simulated install: Update now is offered, and would only rehearse)

        async def receiving() -> str:
            neoaprs_db_set(work / "receiving", "station/transmit", "false")
            neoaprs_db_set(work / "receiving", "beacon/interval_min", "0")
            return await started(Daemon(work / "receiving"))                                       # (the same day on the air, with station/transmit false: RX only, and the beacon Off)

        async def moving() -> str:
            gpsd = await start_gps_replay()
            gpsds.append(gpsd)
            assert gpsd.stdout is not None
            address = (await asyncio.wait_for(gpsd.stdout.readline(), 20)).decode().strip()          # (its first line: 127.0.0.1:PORT, a free port of the loopback)
            for key, value in {"gps/source": "gpsd", "gps/host": address, "beacon/interval_min": "30"}.items():       # (30 is On for a moving station: SmartBeaconing, travelling by car as it is by default)
                neoaprs_db_set(work / "moving", key, value)
            return await started(Daemon(work / "moving"))

        async def hf() -> str:
            hf_url = await started(Daemon(work / "hf", env={"PATH": "/nonexistent"}))               # (the same day on the air and the Dummy HF radio beside it; with no player on the PATH its frames are not played through this machine's speakers)
            await give_hf_radio(hf_url, "dummy-hf", {})
            return hf_url

        async def hf_mercury() -> str:
            pipes = PipeMercury(work / "hf-mercury")
            modems.append(pipes)
            mercury_url = await started(Daemon(work / "hf-mercury", "--hf-port", pipes.start()))   # (the same day on the air and the Mercury modem beside it, a real one on pipes that hears silence and keys nothing:
            await give_hf_radio(mercury_url, "mercury", {"keying": "vox", "sound_card": ""})        #  the radio given through the page is radio 2, which --hf-port names)
            return mercury_url

        starts: dict[str, Callable[[], Awaitable[str]]] = {"updating": updating, "receiving": receiving, "moving": moving, "hf": hf, "hf-mercury": hf_mercury}
        urls: dict[str, str] = {}
        for key in sorted(wanted):
            try:
                urls[key] = await starts[key]()
            except (RuntimeError, TimeoutError, OSError, subprocess.CalledProcessError, smoke.Failure) as e:
                run.why_not.update({name: f"its daemon did not come up: {e}" for name in EXTRA_DAEMONS[key] if name in chosen})
        async with async_playwright() as p:
            options: dict[str, Any] = {"args": ["--no-sandbox"] if args.no_sandbox else []}
            if args.chromium:
                options["executable_path"] = args.chromium
            browser = await p.chromium.launch(**options)
            shots = Shots(browser, url, args.out)
            shots.update_url, shots.receive_url, shots.moving_url = urls.get("updating", ""), urls.get("receiving", ""), urls.get("moving", "")
            shots.hf_url, shots.hf_mercury_url = urls.get("hf", ""), urls.get("hf-mercury", "")
            for name in chosen:
                if name in run.why_not:
                    continue
                try:
                    await SHOTS[name](shots, fresh_url)
                    run.taken.append(name)
                except Exception as e:                                                             # (a shot that fails is said at the end; the others are taken)
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
        for modem in modems:
            modem.stop()
        for gpsd in gpsds:
            if gpsd.returncode is None:
                gpsd.terminate()
                await gpsd.wait()
        for server in servers:
            server.close()
        await radio.stop()
        if args.keep:
            print("kept:", work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
