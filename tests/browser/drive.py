"""The browser suite's daemon and pages: scripts/demo-daemon on a folder of its own, and Chromium on its page."""

import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.browser.rules import FONT

ROOT = Path(__file__).resolve().parents[2]
PAGE_JS = Path(__file__).with_name("page.js")
LANGUAGES = ("en", "de", "es", "fi", "fr", "it", "ja", "nl", "pt-BR")
# The two languages whose catalogues have the most letters (ui/src/i18n): the longest words on the page
LONGEST = ("fr", "de")
WIDTHS = (390, 1280)
HEIGHT = {390: 844, 1280: 900}
TABS = ("messages", "stations", "nearby", "email", "bulletins", "skeds", "objects", "beacon", "packets", "settings")
CALL = "OH2TST"
HOME = (60.2231, 24.7152)  # the place of the demo's made-up world (scripts/demoscene.py)
RADIOS = ("dummy", "dummy-hf", "dummy-lora")
START_SEC = 90.0  # the longest a start may take (a limit, not how long it takes)
STEP_MS = 30_000  # the longest one step of the page may take
LOG_LINE = re.compile(r"web page at (http://\S+?)/?\s")
SHIPS_LINE = re.compile(r"Ships, My own receiver: (127\.0\.0\.1:\d+)")


def until(condition: Callable[[], object], timeout_sec: float, what: str) -> None:
    """Wait for `condition` to come true, looking every tenth of a second; fail after `timeout_sec`."""
    done = threading.Event()
    waited = 0.0
    while not condition():
        assert waited < timeout_sec, f"{what} did not come in {timeout_sec:g} s"
        done.wait(0.1)
        waited += 0.1


def browsers_folder() -> Path:
    """Where Playwright keeps its browsers: PLAYWRIGHT_BROWSERS_PATH, else its default for this user."""
    given = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if given and given != "0":
        return Path(given)
    home = Path.home()
    return (
        Path(os.environ.get("LOCALAPPDATA", home)) / "ms-playwright"
        if sys.platform == "win32"
        else home / "Library" / "Caches" / "ms-playwright"
        if sys.platform == "darwin"
        else home / ".cache" / "ms-playwright"
    )


def installed_chromium(folder: Path) -> Path | None:
    """The newest Chromium installed in `folder` by any version of Playwright, its headless shell first."""
    shapes = (
        "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        "chromium-*/chrome-linux64/chrome",
    )
    for shape in shapes:
        found = sorted(folder.glob(shape), key=lambda p: int(re.sub(r"\D", "", p.parts[-3]) or 0), reverse=True)
        if found:
            return found[0]
    return None


def launch(playwright: Any) -> Any:
    """Chromium: the build this Playwright wants, else the newest one installed; None when there is none.

    Never downloads one: `playwright install chromium` does that, asked for."""
    try:
        return playwright.chromium.launch()
    except Exception as e:
        if "Executable doesn't exist" not in str(e):
            raise
    other = installed_chromium(browsers_folder())
    return None if other is None else playwright.chromium.launch(executable_path=str(other))


def neoaprs_db(data: Path, *words: str) -> str:
    done = subprocess.run(
        [sys.executable, "-m", "neoaprs", "db", "--data", str(data), *words],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={**os.environ, "NEOAPRS_UPDATE_CHECK": "0"},
        check=True,
    )
    return done.stdout


@dataclass
class Demo:
    """scripts/demo-daemon on a folder of its own: a call, a place, the three Dummy radios, the made-up
    aircraft, ships and satellites, on ports the system hands out."""

    folder: Path
    call: str = CALL
    settings: dict[str, str] = field(default_factory=dict)  # more of the station's settings
    url: str = ""
    ships_address: str = ""
    process: subprocess.Popen[bytes] | None = None
    output: Path = field(init=False)

    def __post_init__(self) -> None:
        self.output = self.folder.parent / f"{self.folder.name}-demo-daemon.log"

    def prepare(self) -> None:
        if self.folder.exists():
            shutil.rmtree(self.folder)
        self.folder.mkdir(parents=True)
        place = {"station/call": self.call, "station/lat": str(HOME[0]), "station/lon": str(HOME[1])}
        for key, value in {**place, **self.settings}.items():
            if value:
                neoaprs_db(self.folder, "set", key, value)
        for kind in RADIOS:
            neoaprs_db(self.folder, "radios", "add", kind)

    def start(self) -> None:
        with self.output.open("wb") as out:
            self.process = subprocess.Popen(
                [sys.executable, str(ROOT / "scripts" / "demo-daemon"), "--data", str(self.folder), "--any-port"]
                + ["--traffic", "--satellites"],
                stdout=out,
                stderr=subprocess.STDOUT,
                cwd=ROOT,
            )
        log = self.folder / "neoaprs.log"

        def page_address() -> bool:
            assert self.process is not None and self.process.poll() is None, "demo-daemon ended: " + self.said()
            found = LOG_LINE.search(log.read_text(errors="replace") + "\n") if log.exists() else None
            self.url = found.group(1) + "/" if found else ""
            return bool(self.url)

        until(page_address, START_SEC, "the demo daemon's page")
        found = SHIPS_LINE.search(self.said())
        self.ships_address = found.group(1) if found else ""

    def said(self) -> str:
        return self.output.read_text(errors="replace") if self.output.exists() else ""

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(START_SEC)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(START_SEC)


@dataclass
class Faults:
    """What a page said wrong while a test drove it: console errors, uncaught errors, failed requests."""

    allowed: tuple[re.Pattern[str], ...]
    found: list[str] = field(default_factory=list)

    def note(self, what: str) -> None:
        if not any(pattern.search(what) for pattern in self.allowed):
            self.found.append(what)

    def watch(self, page: Any) -> None:
        page.on("console", lambda m: m.type == "error" and self.note(f"console error: {m.text}"))
        page.on("pageerror", lambda e: self.note(f"uncaught: {e}"))
        page.on("requestfailed", lambda r: self.note(f"request failed: {r.method} {r.url} {r.failure}"))
        page.on("response", lambda r: r.status >= 400 and self.note(f"answer {r.status}: {r.request.method} {r.url}"))


@contextmanager
def opened(
    browser: Any,
    url: str,
    faults: Faults,
    language: str = "en",
    width: int = 1280,
    tab: str = "stations",
    theme: str = "light",
    view: str = "panel",
    stored: dict[str, str] | None = None,
) -> Iterator[Any]:
    """A page of its own (a fresh context): the language, the tab and, on a phone, the panel or the map
    stored before it starts, as the person's earlier choices would be."""
    context = browser.new_context(
        viewport={"width": width, "height": HEIGHT.get(width, 900)},
        color_scheme=theme,
        locale="en-GB",
        timezone_id="Europe/Helsinki",
        service_workers="block",
    )
    keys = {"language": language, "tab": tab, "panel": "open", "view": view, **(stored or {})}
    context.add_init_script("".join(f"localStorage.setItem({('NeoAPRS.' + k)!r}, {v!r});" for k, v in keys.items()))
    context.add_init_script(path=str(PAGE_JS))
    context.add_init_script(
        f"document.addEventListener('DOMContentLoaded', () => document.documentElement.style.setProperty('--font', {FONT!r}));"
    )
    page = context.new_page()
    page.set_default_timeout(STEP_MS)
    faults.watch(page)
    try:
        page.goto(url)
        ready(page)
        yield page
    finally:
        context.close()


def ready(page: Any) -> None:
    """The page is up: its socket has brought the settings and the stations, its fonts are in."""
    page.wait_for_function(
        "() => document.querySelector('.app') && window.__neoSocket.topics.includes('config')"
        " && window.__neoSocket.topics.includes('stations') && document.fonts.status === 'loaded'"
    )
    settle(page)


def settle(page: Any, root: str = "body", frames: int = 10) -> None:
    """Every save answered and nothing under `root` moving for `frames` frames."""
    page.evaluate("([root, frames, live]) => NeoChecks.quiet(root, frames, live)", [root, frames, LIVE])


# What changes by itself while the page is looked at: the map, the tables of what is heard, the ages.
LIVE = (
    ".mapwrap, .grid, .packets, .convlist, .bubbles, .headpills, .nearby-head, .nearby-section:not(.nearby-ask),"
    " .tncstatus, .statetext, time, .age"
)


def show_tab(page: Any, tab: str) -> None:
    """Choose a tab as a person does: its button, or on a phone the More menu when it is not in the bar."""
    in_bar = page.evaluate("tabs => tabs.filter(t => document.getElementById('tab-' + t))", list(TABS))
    if tab in in_bar:
        page.locator(f"#tab-{tab}").click()
    else:
        page.locator("#tabmenu-button").click()
        page.locator(".tabmenu-item").nth([t for t in TABS if t not in in_bar].index(tab)).click()
    page.wait_for_function(
        "t => { const p = document.getElementById('pane-' + t); return p && p.checkVisibility(); }", arg=tab
    )
    settle(page)


@dataclass
class Change:
    """A box under the root that changed when a control did: its rectangle (left, top, width, height)
    before and after, and where it stands to the control."""

    name: str
    was: list[float]
    now: list[float] | None  # None: it went
    after: bool  # after the control in the page's order
    holds: bool  # it holds the control (a group that grows or shrinks round it)
    beside: bool  # it is in the control's own group (the fieldset round it)

    def __str__(self) -> str:
        return f"{self.name}: {self.was} -> {self.now if self.now is not None else 'gone'}"


def changes(page: Any, root: str, control: str, act: Callable[[], None]) -> tuple[list[Change], list[str]]:
    """Do `act` (which changes the control the selector `control` names); return the boxes under `root`
    that moved, changed size or went, and the names of those that came."""
    at, row = page.evaluate(
        """([root, c]) => { const e = document.querySelector(c); const f = e?.closest('fieldset');
            return e ? [NeoChecks.place(root, e), f ? NeoChecks.place(root, f) : ''] : ['', '']; }""",
        [root, control],
    )
    before = page.evaluate("([root, live]) => NeoChecks.boxes(root, live)", [root, LIVE])
    act()
    settle(page, root)
    after = page.evaluate("([root, live]) => NeoChecks.boxes(root, live)", [root, LIVE])
    order = next((was["order"] for was in before.values() if was["path"] == at), 0)
    found = [
        Change(
            was["name"],
            was["r"],
            now["r"] if now else None,
            was["order"] > order,
            at.startswith(was["path"] + "/"),
            bool(row) and (was["path"] + "/").startswith(row + "/"),
        )
        for key, was in before.items()
        if was["path"] != at
        and ((now := after.get(key)) is None or any(abs(a - b) > 0.5 for a, b in zip(was["r"], now["r"])))
    ]
    return found, [now["name"] for key, now in after.items() if key not in before]
