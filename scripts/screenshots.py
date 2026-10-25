"""Takes the screenshots of the README and the project page (site/): a daemon of its own on a temporary data folder, a made-up day on the air (scripts/demoscene.py), Chromium through Playwright.

    uv run --with playwright --with pillow python scripts/screenshots.py                  # all of them into site/shots/, seven of them also into docs/screenshots/
    uv run --with playwright --with pillow python scripts/screenshots.py --only map weather
    python scripts/screenshots.py --chromium /path/to/chrome --no-sandbox                  # a browser Playwright did not install, or one that cannot make its sandbox

Nothing touches a radio: the daemon's TNC is a KISS server on a TCP port of the loopback that this script serves (the `kiss-tcp` profile), and the fresh folder of the setup guide is given that port on the
command line. The footer's version is hidden in every shot and the newer version of the update shot is made from VERSION, so the shots do not go old with a release: they are retaken when the page changes. The map for street level is linked or copied from a PMTiles file you name (`--basemap`, default `data/basemap.pmtiles` of this clone; it is only read). Needs Playwright and, to
make the PNG files small, Pillow; `playwright install chromium` fetches the browser. Needs `uv sync` first (or `uv run`, which does it) so that `neoaprs` is importable."""
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
import sys
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ICON = ROOT / "neoaprs" / "desktop" / "icon.png"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import demoscene                                                  # noqa: E402  (the scene needs the path above)
from neoaprs import VERSION                                       # noqa: E402
from neoaprs.controller import Controller                         # noqa: E402

DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}
TABLET = {"width": 1024, "height": 768}
LIMIT_KB = 480                                                    # a PNG is made smaller than this (colours are reduced when it must be)
README_SHOTS = ("map", "weather", "messages", "beacon", "objects", "bulletins", "setup")
SETTINGS = {
    "station/call": "OH2GBA", "station/lat": f"{demoscene.HOME[0]}", "station/lon": f"{demoscene.HOME[1]}", "station/symbol_table": "/", "station/symbol_code": "-",
    "station/comment": "NeoAPRS in Espoo", "beacon/power_w": "5", "beacon/antenna_height_m": "10", "beacon/antenna_gain_db": "3", "messages/alert": "false", "tnc/profile": "kiss-tcp",
    "tcp/host": demoscene.HOST,
}
AFTER_THE_DAY = {"beacon/interval_min": "30", "station/status": "QRV 144.800 MHz FM", "messages/alert": "true", "web/network": "true"}          # (the day is played without the alert command, the beacon timer and the status: the page's daemon starts them)
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
            probe.bind((demoscene.HOST, GPSD_PORT))                  # (gpsd's own port when it is free, as the Beacon tab then shows what a gpsd user knows, else any free one)
            port = GPSD_PORT
        except OSError:
            port = 0
    return await asyncio.create_subprocess_exec(sys.executable, "-m", "neoaprs", "gps-replay", "--port", str(port), "--at", f"{demoscene.HOME[0]},{demoscene.HOME[1]}", "--kmh", "45", "--interval", "0.5",
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=env, cwd=ROOT)


def neoaprs_db_set(data: Path, key: str, value: str) -> None:
    subprocess.run([sys.executable, "-m", "neoaprs", "db", "--data", str(data), "set", key, value], check=True, capture_output=True, cwd=ROOT)


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
# The footer's "NeoAPRS <version>" is hidden in every shot (the space stays, so nothing moves), so that a new version makes no shot old: the shots are retaken when the page changes, not at each
# release. The one shot that still names versions is update.png: UPDATE_TO, and the installed one in the dialog's "You have NeoAPRS ...". (The page allows an inline style sheet: style-src
# 'unsafe-inline' of neoaprs/web/headers.py.)
HIDE_VERSION = ".panelfoot .version { visibility: hidden; }"


async def prepare(work: Path, radio: demoscene.DemoRadio, basemap: Path | None) -> Path:
    """The data folder of the operator: a database with the settings, the map, and the day played into it."""
    data = work / "demo"
    data.mkdir()
    ctl = Controller(data)
    await ctl.open_database()
    assert ctl.db is not None
    await ctl.db.close()
    for key, value in {**SETTINGS, "tcp/port": str(radio.port)}.items():
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
        self.receive_url = ""                                      # the page of the daemon that is set to Receive only (the "beacon-rx" shot)
        self.moving_url = ""                                       # the page of the daemon that follows a GPS (the "beacon-gps" shot)
        self.scheme = "light"                                      # the colour scheme of the shots being taken; a dark one is saved as NAME-dark.png
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
    """The Stations tab is the one a page opens on; on a tab bar too narrow for the nine tabs (a panel of 760 px is) the tabs are one button, "Messages" with a menu of them, which a phone's page has under its map button."""
    tab = page.locator("#tab-stations")
    if await tab.is_visible():
        await tab.click()
        return
    button = page.locator("#tabmenu-button")
    if await button.is_visible() and "Stations" not in await button.inner_text():
        await button.click()
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
    await page.locator("#set-update-now").click()                     # (Check now finds the newer version and opens the window by itself: closed again, so that it is not drawn over the Settings tab)
    await settle(page, 1500)
    await page.keyboard.press("Escape")
    await settle(page, 400)
    await open_stations_tab(page)                                     # (the Settings tab shows the daemon's own key and addresses: not under this shot)
    await settle(page, 400)
    await page.get_by_role("button", name=f"Update to {UPDATE_TO}").click()
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
    """The Beacon tab of a browser that speaks German: the page starts in the browser's language (seven are there)."""
    await s.since_start(45)
    page = await s.page(DESKTOP, tab="beacon", view=CITY, panel=WIDE_PANEL, locale="de-DE")
    await page.locator("#pane-beacon summary").filter(has_text="Erweitert").click()
    await settle(page, 400)
    await s.save(page, "beacon-de")


async def made_up_web(page: Any) -> None:
    """Puts the made-up access key and addresses (and the usual KISS port) in place of the daemon's own on a page that shows the Settings tab: the machine's own address and name never appear in a shot."""
    await page.evaluate("""([key, urls]) => {
        const put = () => {
            const field = document.getElementById("set-web-key");
            if (field) field.value = key;
            const port = document.getElementById("set-tcp-port");
            if (port) port.value = "8001";                        // (Direwolf's usual KISS port; the demo's own TNC listens where there was room)
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
    await page.locator("legend", has_text="Web page").scroll_into_view_if_needed()
    await made_up_web(page)
    await page.evaluate("document.querySelector('#pane-settings fieldset:has(#set-web-key)')?.scrollIntoView({block: 'start'})")
    await settle(page, 400)
    await s.save(page, "settings-web")


async def shot_settings_tnc(s: Shots, _: str) -> None:
    """Settings, the TNC group opened by its arrow: the type of TNC, the port and the speed, Find my radio and the Terminal (a connected radio keeps it folded to its one line)."""
    page = await s.page(DESKTOP, tab="settings", view=CITY, panel=560)
    await made_up_web(page)
    await page.locator("#pane-settings .radiohead").click()
    await settle(page, 600)
    await page.evaluate("document.querySelector('#pane-settings .radiostatus')?.scrollIntoView({block: 'start'})")
    await settle(page, 400)
    await s.save(page, "settings-tnc")


async def shot_beacon_rx(s: Shots, _: str) -> None:
    """The Beacon tab of a station that is set to Receive only (the daemon's setting station/transmit: the amber badge in the header, beside the title) and has the Beacon Off: the status block says Beacon off with its pill off, and what belongs to the beacon is grey."""
    page = await s.page(DESKTOP, tab="beacon", view=CITY, panel=WIDE_PANEL, url=s.receive_url)
    await settle(page, 400)
    await s.save(page, "beacon-rx")


async def shot_phone_beacon_rx(s: Shots, _: str) -> None:
    """A phone set to Receive only with the Beacon Off: the amber badge beside the title and, under the tab bar, the Beacon tab with its status block saying Beacon off and the fields of the beacon grey."""
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
    """The Beacon tab of a moving station: Position is A GPS via gpsd (its address under it), the status block has the GPS with its fix and the line of SmartBeaconing under it, the Beacon choice is On (SmartBeaconing) and Travelling By car; our own station drives round a block on the map (the gpsd is `neoaprs gps-replay`)."""
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
    await settle(page, 400)
    await s.save(page, "settings")


async def shot_packets(s: Shots, _: str) -> None:
    page = await s.page(DESKTOP, tab="packets", view=CITY, panel=760)
    await s.save(page, "packets")


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


def make_thumbs(out: Path) -> None:
    """thumbs/NAME.png next to each shot: 640 px wide (270 for a phone), what the gallery of the site loads before a picture is opened."""
    from PIL import Image
    (out / "thumbs").mkdir(exist_ok=True)
    for path in sorted(out.glob("*.png")):
        if path.name == "og.png":
            continue
        image = Image.open(path).convert("RGB")
        width = 270 if path.name.startswith("phone-") else 640
        small = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS).quantize(128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        small.save(out / "thumbs" / path.name, optimize=True)
    print(f"thumbs/: {len(list((out / 'thumbs').glob('*.png')))} files")


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


def make_og(out: Path) -> None:
    """og.png, 1200x630: the map shot on the dark blue of the icon, the name and the pitch beside it (what a link to the site shows)."""
    from PIL import Image, ImageDraw
    source = out / "map.png"
    if not source.exists():
        return
    card = Image.new("RGB", (1200, 630), (20, 44, 82))
    shot = Image.open(source).convert("RGB")
    shot = shot.resize((round(shot.width * 0.62), round(shot.height * 0.62)), Image.LANCZOS)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, shot.width, shot.height), radius=18, fill=255)
    card.paste(shot, (468, 112), mask)
    draw = ImageDraw.Draw(card)
    draw.text((56, 150), "NeoAPRS", font=_font(84, True), fill=(255, 255, 255))
    for i, line in enumerate(("A modern, easy-to-use", "APRS client for Windows,", "Linux and the Raspberry Pi")):
        draw.text((58, 262 + i * 40), line, font=_font(28, False), fill=(190, 214, 245))
    if ICON.exists():
        mark = Image.open(ICON).convert("RGBA").resize((72, 72), Image.LANCZOS)
        card.paste(mark, (58, 56), mark)
    card.save(out / "og.png", optimize=True)
    print("og.png")


EXTRAS = ("thumbs", "og")                                          # what is made from the shots, with no browser
SHOTS: dict[str, Shot] = {
    "map": shot_map, "stations": shot_stations, "station": shot_station, "weather": shot_weather, "messages": shot_messages, "email": shot_email, "bulletins": shot_bulletins,
    "objects": shot_objects, "objects-form": shot_objects_form, "beacon": shot_beacon, "settings": shot_settings, "packets": shot_packets, "phone-map": shot_phone_map, "phone-bulletins": shot_phone_bulletins, "phone-weather": shot_phone_weather,
    "cards": shot_cards, "stations-menu": shot_stations_menu, "update": shot_update, "beacon-de": shot_beacon_de, "phone-messages": shot_phone_messages, "tablet": shot_tablet, "setup": shot_setup, "chain": shot_chain, "chain-failed": shot_chain_failed, "settings-web": shot_settings_web, "phone-key": shot_phone_key,
    "station-details": shot_station_details, "settings-tnc": shot_settings_tnc, "beacon-rx": shot_beacon_rx, "phone-beacon-rx": shot_phone_beacon_rx,
    "nearby": shot_nearby, "beacon-gps": shot_beacon_gps,
}
DARK_TOO = ("map", "stations", "station", "weather", "messages", "email", "bulletins", "objects", "objects-form", "beacon", "settings", "packets", "phone-map", "phone-bulletins", "phone-weather", "cards", "stations-menu", "update", "beacon-de", "phone-messages", "tablet", "setup", "chain", "chain-failed", "settings-web", "phone-key", "station-details", "settings-tnc", "beacon-rx", "phone-beacon-rx", "nearby", "beacon-gps")


def in_the_dark(shot: Shot) -> Shot:
    async def dark(s: Shots, fresh_url: str) -> None:
        s.scheme = "dark"
        try:
            await shot(s, fresh_url)
        finally:
            s.scheme = "light"
    return dark


SHOTS.update({f"{name}-dark": in_the_dark(SHOTS[name]) for name in DARK_TOO})


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "site" / "shots", help="where the PNG files go (default %(default)s)")
    parser.add_argument("--docs", type=Path, default=ROOT / "docs" / "screenshots", help="where the README's shots are copied (default %(default)s); 'none' leaves them out")
    parser.add_argument("--only", nargs="*", metavar="NAME", help=f"take only these of: {', '.join([*SHOTS, *EXTRAS])}")
    parser.add_argument("--basemap", type=Path, default=ROOT / "data" / "basemap.pmtiles", help="a PMTiles map of the area for street level (default %(default)s); without it only the placeholder is drawn")
    parser.add_argument("--chromium", default=os.environ.get("CHROMIUM"), help="the browser's executable, when Playwright's own is not installed")
    parser.add_argument("--no-sandbox", action="store_true", help="start the browser without its sandbox (a container, a user namespace that is refused)")
    parser.add_argument("--keep", action="store_true", help="keep the temporary data folders and say where they are")
    args = parser.parse_args(argv)
    os.environ["NEOAPRS_UPDATE_CHECK"] = "0"                          # (no daemon of the shots asks the version page: the header shows no newer-version link)
    logging.getLogger("neoaprs").setLevel(logging.ERROR)              # (the day has a message that fails, on purpose: the log's warning about it is not news)
    chosen = sorted(args.only or SHOTS, key=lambda name: not name.startswith("setup"))      # (the guide's shots first: its daemon hears the air of the day, our own bulletins repeated among it, and the guide's table is to be empty)
    if unknown := [n for n in chosen if n not in SHOTS and n not in EXTRAS]:
        parser.error(f"no such shot: {', '.join(unknown)}")
    taking = [n for n in chosen if n in SHOTS]
    args.out.mkdir(parents=True, exist_ok=True)
    if taking:
        await take(args, taking)
    if args.only is None or "thumbs" in chosen:
        make_thumbs(args.out)
    if args.only is None or "og" in chosen:
        make_og(args.out)
    return 0


async def take(args: argparse.Namespace, chosen: list[str]) -> None:
    from playwright.async_api import async_playwright
    work = Path(tempfile.mkdtemp(prefix="neoaprs-shots-"))
    radio = demoscene.DemoRadio()
    await radio.start()
    daemons: list[Daemon] = []
    servers: list[asyncio.Server] = []
    gpsds: list[asyncio.subprocess.Process] = []
    try:
        data = await prepare(work, radio, args.basemap if args.basemap.exists() else None)
        updating: Daemon | None = None
        if {"update", "update-dark"} & set(chosen):
            copy_data(data, work / "updating")
            versions = await serve_version(UPDATE_TO)
            servers.append(versions)
            neoaprs_db_set(work / "updating", "update/url", f"http://{demoscene.HOST}:{versions.sockets[0].getsockname()[1]}/version.php")
            updating = Daemon(work / "updating", env={"NEOAPRS_INSTALL_KIND": "windows-installer"})        # (a simulated install: Update now is offered, and would only rehearse)
            daemons.append(updating)
        receiving: Daemon | None = None
        if {"beacon-rx", "beacon-rx-dark", "phone-beacon-rx", "phone-beacon-rx-dark"} & set(chosen):
            copy_data(data, work / "receiving")
            neoaprs_db_set(work / "receiving", "station/transmit", "false")
            neoaprs_db_set(work / "receiving", "beacon/interval_min", "0")
            receiving = Daemon(work / "receiving")                                                   # (the same day on the air, with station/transmit false: Receive only, and the beacon Off)
            daemons.append(receiving)
        moving: Daemon | None = None
        if {"beacon-gps", "beacon-gps-dark"} & set(chosen):
            gpsd = await start_gps_replay()
            gpsds.append(gpsd)
            assert gpsd.stdout is not None
            address = (await asyncio.wait_for(gpsd.stdout.readline(), 20)).decode().strip()          # (its first line: 127.0.0.1:PORT, a free port of the loopback)
            copy_data(data, work / "moving")
            for key, value in {"gps/source": "gpsd", "gps/host": address, "beacon/interval_min": "30"}.items():       # (30 is On for a moving station: SmartBeaconing, travelling by car as it is by default)
                neoaprs_db_set(work / "moving", key, value)
            moving = Daemon(work / "moving")
            daemons.append(moving)
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
        update_url = await updating.start() if updating else ""
        receive_url = await receiving.start() if receiving else ""
        moving_url = await moving.start() if moving else ""
        async with async_playwright() as p:
            options: dict[str, Any] = {"args": ["--no-sandbox"] if args.no_sandbox else []}
            if args.chromium:
                options["executable_path"] = args.chromium
            browser = await p.chromium.launch(**options)
            shots = Shots(browser, url, args.out)
            shots.update_url = update_url
            shots.receive_url = receive_url
            shots.moving_url = moving_url
            for name in chosen:
                await SHOTS[name](shots, fresh_url)
            await browser.close()
        if args.docs.name != "none":
            args.docs.mkdir(parents=True, exist_ok=True)
            for name in README_SHOTS:
                if (args.out / f"{name}.png").exists() and name in chosen:
                    shutil.copyfile(args.out / f"{name}.png", args.docs / f"{name}.png")
    finally:
        for daemon in daemons:
            await daemon.stop()
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
