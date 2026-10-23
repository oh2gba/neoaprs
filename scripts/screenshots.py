"""Takes the screenshots of the README and the project page (site/): a daemon of its own on a temporary data folder, a made-up day on the air (scripts/demoscene.py), Chromium through Playwright.

    uv run --with playwright --with pillow python scripts/screenshots.py                  # all of them into site/shots/, seven of them also into docs/screenshots/
    uv run --with playwright --with pillow python scripts/screenshots.py --only map weather
    python scripts/screenshots.py --chromium /path/to/chrome --no-sandbox                  # a browser Playwright did not install, or one that cannot make its sandbox

Nothing touches a radio: the daemon's TNC is a KISS server on a TCP port of the loopback that this script serves (the `kiss-tcp` profile), and the fresh folder of the setup guide is given that port on the
command line. The map for street level is linked or copied from a PMTiles file you name (`--basemap`, default `data/basemap.pmtiles` of this clone; it is only read). Needs Playwright and, to
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
from neoaprs.controller import Controller                         # noqa: E402

DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}
LIMIT_KB = 480                                                    # a PNG is made smaller than this (colours are reduced when it must be)
README_SHOTS = ("map", "weather", "messages", "beacon", "objects", "bulletins", "setup")
SETTINGS = {
    "station/call": "OH2GBA", "station/lat": f"{demoscene.HOME[0]}", "station/lon": f"{demoscene.HOME[1]}", "station/symbol_table": "/", "station/symbol_code": "-",
    "station/comment": "NeoAPRS in Espoo", "beacon/power_w": "5", "beacon/antenna_height_m": "10", "beacon/antenna_gain_db": "3", "messages/alert": "false", "tnc/profile": "kiss-tcp",
    "tcp/host": demoscene.HOST,
}
AFTER_THE_DAY = {"beacon/interval_min": "30", "station/status": "QRV 144.800 MHz FM", "messages/alert": "true", "web/network": "true"}          # (the day is played without the alert command, the beacon timer and the status: the page's daemon starts them)
SHOWN_KEY = "k7m2-x9pq-4hrt"                                       # what the Settings shot shows as the access key, and the addresses: the daemon's own key is made at random for the run and never shown
SHOWN_URLS = ["http://192.168.1.20:7303/", "http://neoaprs-pi.local:7303/"]


class Daemon:
    """`python -m neoaprs` as a child process, its page's port read from its log."""

    def __init__(self, data: Path, *extra: str) -> None:
        self.data, self.extra = data, extra
        self.proc: asyncio.subprocess.Process | None = None
        self.url = ""
        self.log: list[str] = []

    async def start(self) -> str:
        env = {k: v for k, v in os.environ.items() if not k.startswith("NEOAPRS_")}
        env["NEOAPRS_UPDATE_CHECK"] = "0"                        # (a made-up day: the daemon does not ask the version page)
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


def neoaprs_db_set(data: Path, key: str, value: str) -> None:
    subprocess.run([sys.executable, "-m", "neoaprs", "db", "--data", str(data), "set", key, value], check=True, capture_output=True, cwd=ROOT)


def put_map(source: Path, target: Path) -> None:
    """The map file in a data folder: the page's server does not follow a symbolic link out of the folder, so it is a hard link, else a copy (the source is only read)."""
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


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
        self.scheme = "light"                                      # the colour scheme of the shots being taken; a dark one is saved as NAME-dark.png
        self.started = asyncio.get_running_loop().time()

    async def since_start(self, seconds: float) -> None:
        """Waits until the daemon has run this long (the first beacon and status of its timers go out some seconds after the start)."""
        left = self.started + seconds - asyncio.get_running_loop().time()
        if left > 0:
            await asyncio.sleep(left)

    async def page(self, size: dict[str, int], scheme: str | None = None, tab: str = "stations", view: tuple[float, float, float] | None = None, panel: int | None = None,
                   wx_hours: str | None = None, url: str | None = None, wait_ms: int = 5000, scale: int = 1, headers: dict[str, str] | None = None) -> Any:
        context = await self.browser.new_context(viewport=size, color_scheme=scheme or self.scheme, device_scale_factor=scale, locale="en-GB", timezone_id="Europe/Helsinki",
                                                 extra_http_headers=headers)
        keys = {"tab": tab, "panel": "open"}
        if view:
            keys["mapview"] = f'{{"lat":{view[0]},"lon":{view[1]},"zoom":{view[2]}}}'
        if panel:
            keys["panelwidth"] = str(panel)
        if wx_hours:
            keys["wxhours"] = wx_hours
        script = "".join(f"try{{localStorage.setItem('NeoAPRS.{k}',{v!r})}}catch(e){{}};" for k, v in keys.items())
        await context.add_init_script(script)
        page = await context.new_page()
        await page.goto(url or self.url)
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


async def pick_station(page: Any, call: str, wait: int = 4500) -> None:
    await page.locator("#tab-stations").click()
    await page.locator("#pane-stations tbody tr", has_text=call).first.click()
    await page.wait_for_timeout(wait)


# the views of the map: (lat, lon, zoom)
OVERVIEW = (60.205, 24.80, 9.6)
CITY = (60.185, 24.78, 11.2)

Shot = Callable[[Shots, str], Awaitable[None]]


async def shot_map(s: Shots, _: str) -> None:
    page = await s.page(DESKTOP, view=OVERVIEW)
    await s.save(page, "map")


async def shot_stations(s: Shots, _: str) -> None:
    page = await s.page(DESKTOP, view=OVERVIEW, panel=900)
    await s.save(page, "stations")


async def shot_station(s: Shots, _: str) -> None:
    page = await s.page(DESKTOP, view=(60.165, 24.78, 11.6))
    await pick_station(page, "OH2ZMA-9")
    await s.save(page, "station")


async def shot_weather(s: Shots, _: str) -> None:
    page = await s.page(DESKTOP, view=(60.19, 24.78, 11))
    await pick_station(page, "OH2ZWA")
    await s.save(page, "weather")


async def open_thread(s: Shots, call: str, scale: int = 1, size: dict[str, int] = DESKTOP) -> Any:
    """The Messages tab with the conversation of `call` open."""
    page = await s.page(size, tab="messages", view=CITY, panel=560, scale=scale)
    await page.locator("#pane-messages").get_by_text(call).first.click()
    await settle(page, 1500)
    return page


async def shot_messages(s: Shots, _: str) -> None:
    page = await open_thread(s, "OH2ZPK")
    await s.save(page, "messages")


async def thread_clip(page: Any, most: int) -> dict[str, int]:
    """The thread of the open conversation from its top to the bottom of its last message (at most `most` pixels): the close-up of the chains."""
    await page.evaluate("document.querySelector('#pane-messages .thread').scrollTop = 0")
    box = await page.locator("#pane-messages .thread").bounding_box()
    last = await page.locator("#pane-messages .thread .msg").last.bounding_box()
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
    page = await s.page(DESKTOP, tab="email", view=CITY, panel=560)
    await s.save(page, "email")


async def shot_bulletins(s: Shots, _: str) -> None:
    """The message board: the box to post to it (a draft in it, with the characters left), our two entries marked ours among the heard ones."""
    page = await s.page(DESKTOP, tab="bulletins", view=CITY, panel=560)
    await page.fill("#post-text", "Road works on the ring road, expect delays")
    await settle(page, 400)
    await s.save(page, "bulletins")


OBJECTS = (60.19, 24.749, 11.3)                                         # the view with all of our objects on it


async def shot_objects(s: Shots, _: str) -> None:
    """The Objects tab: our objects and items, how often each was sent and when it goes out next; they are on the map with the dashed ring of the ones that are ours."""
    page = await s.page(DESKTOP, tab="objects", view=OBJECTS, panel=560)
    await s.save(page, "objects")


async def shot_objects_form(s: Shots, _: str) -> None:
    """The form of an object being changed."""
    page = await s.page(DESKTOP, tab="objects", view=OBJECTS, panel=560)
    await page.get_by_role("button", name="Edit NETCTRL").click()
    await settle(page, 600)
    await s.save(page, "objects-form")


async def shot_beacon(s: Shots, _: str) -> None:
    await s.since_start(45)
    page = await s.page(DESKTOP, tab="beacon", view=CITY, panel=WIDE_PANEL)
    await s.save(page, "beacon")


async def made_up_web(page: Any) -> None:
    """Puts the made-up access key and addresses in place of the daemon's own on a page that shows the Settings tab: the machine's own address and name never appear in a shot."""
    await page.evaluate("""([key, urls]) => {
        const put = () => {
            const field = document.getElementById("set-web-key");
            if (field) field.value = key;
            const inputs = [...document.querySelectorAll('[id^="set-web-url-"]')];
            while (inputs.length && inputs.length < urls.length) { const copy = inputs[0].cloneNode(true); inputs[0].parentElement.append(copy); inputs.push(copy); }
            inputs.forEach((input, i) => { if (i < urls.length) input.value = urls[i]; else input.remove(); });
        };
        put();
        setInterval(put, 25);                                   // (the page draws the settings again when the radio's state changes, and puts its own key and addresses back: they are put over again)
    }""", [SHOWN_KEY, SHOWN_URLS])


async def shot_settings_web(s: Shots, _: str) -> None:
    """Settings, the Web page group: the switch on, the access key and where to open the page (the daemon's own key and addresses are replaced by made-up ones on the screen)."""
    page = await s.page(DESKTOP, tab="settings", view=CITY, panel=WIDE_PANEL)
    await page.locator("legend", has_text="Web page").scroll_into_view_if_needed()
    await made_up_web(page)
    await page.evaluate("document.querySelector('#pane-settings fieldset:has(#set-web-key)')?.scrollIntoView({block: 'start'})")
    await settle(page, 400)
    await s.save(page, "settings-web")


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
    page = await s.page(PHONE, tab="bulletins", view=(60.19, 24.80, 9.4))
    await s.save(page, "phone-bulletins")


async def shot_phone_weather(s: Shots, _: str) -> None:
    page = await s.page(PHONE, view=(60.19, 24.78, 11))
    await pick_station(page, "OH2ZWA")
    await s.save(page, "phone-weather")


async def shot_setup(s: Shots, fresh_url: str) -> None:
    """The guide of a folder with no call, at its symbol step, the call and the position typed in."""
    page = await s.page(DESKTOP, url=fresh_url, wait_ms=3500)
    await page.locator(".setup input").first.fill("OH2GBA")
    await page.get_by_role("button", name="Next").click()
    await page.fill("#setup-lat", str(demoscene.HOME[0]))
    await page.fill("#setup-lon", str(demoscene.HOME[1]))
    await page.wait_for_timeout(1500)
    await page.get_by_role("button", name="Next").click()
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
    "setup": shot_setup, "chain": shot_chain, "chain-failed": shot_chain_failed, "settings-web": shot_settings_web, "phone-key": shot_phone_key,
}
DARK_TOO = ("map", "stations", "station", "weather", "messages", "email", "bulletins", "objects", "objects-form", "beacon", "settings", "packets", "phone-map", "phone-bulletins", "phone-weather", "setup", "chain", "chain-failed", "settings-web", "phone-key")


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
    chosen = args.only or list(SHOTS)
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
    try:
        data = await prepare(work, radio, args.basemap if args.basemap.exists() else None)
        main_daemon = Daemon(data)
        daemons.append(main_daemon)
        url = await main_daemon.start()
        (work / "fresh").mkdir()
        if (data / "basemap.pmtiles").exists():
            put_map(data / "basemap.pmtiles", work / "fresh" / "basemap.pmtiles")
        fresh = Daemon(work / "fresh", "--port", radio.url)
        daemons.append(fresh)
        fresh_url = await fresh.start() if {"setup", "setup-dark"} & set(chosen) else ""
        print("the page:", url, " the fresh one:", fresh_url)
        async with async_playwright() as p:
            options: dict[str, Any] = {"args": ["--no-sandbox"] if args.no_sandbox else []}
            if args.chromium:
                options["executable_path"] = args.chromium
            browser = await p.chromium.launch(**options)
            shots = Shots(browser, url, args.out)
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
        await radio.stop()
        if args.keep:
            print("kept:", work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
