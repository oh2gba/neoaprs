"""The Monitor card's waterfall as long as the card is tall: at 300, 600 and 1200 px and at each speed its
picture is drawn to the bottom once the rows kept have come, and a card made taller keeps the top of its
picture where it was and is drawn to its new bottom. The Dummy HF radio has no scope, so the page's socket is
given the made-up one of the screenshots (scripts/screenshots.py `scope_page`), ten minutes of rows in the
daemon's own frames, cut to the seconds the page asks for as the daemon cuts them."""

import importlib.machinery
import importlib.util
import json
import sys
from functools import cache
from types import ModuleType
from typing import Any

import pytest

from neoaprs.mercuryscope import HISTORY_SEC
from tests.browser import drive
from tests.browser.drive import ROOT

HEIGHTS = (300, 600, 1200)
SPEEDS = ("slow", "normal", "fast")
WIDTH = 1280
VIEW_HEIGHT = 1500  # room in the map for the tallest card
CARD_WIDTH = 540
# The rows of the picture of the card's canvas, as lib/waterfall.ts `layout` cuts the canvas (ruler on top, the
# curve under the picture), and the first of them that is wholly the ground colour: -1 when every one is drawn.
UNDRAWN = """() => {
  const canvas = document.querySelector('.monitorcard canvas');
  if (!canvas || canvas.width < 2 || canvas.height < 2) return { ready: false };
  const ratio = window.devicePixelRatio || 1, css = canvas.clientHeight, h = canvas.height, w = canvas.width;
  const px = (v) => Math.max(1, Math.round(v * ratio));
  const ruler = Math.min(px(22), Math.max(1, Math.floor(h / 5)));
  const curve = Math.min(px(Math.max(40, Math.min(80, css * 0.2))), Math.max(1, Math.floor(h / 3)));
  const rowPx = Math.max(1, Math.round(ratio));
  const bottom = ruler + Math.max(1, Math.floor((h - ruler - curve - px(1)) / rowPx)) * rowPx;
  const ground = getComputedStyle(canvas).getPropertyValue('--waterfall-0').trim();
  const g = [1, 3, 5].map((i) => parseInt(ground.slice(i, i + 2), 16));
  const data = canvas.getContext('2d').getImageData(0, ruler, w, bottom - ruler).data;
  let first = -1;
  for (let y = 0; y < bottom - ruler && first < 0; y++) {
    let drawn = false;
    for (let x = 0; x < w && !drawn; x++) {
      const i = (y * w + x) * 4;
      drawn = data[i] !== g[0] || data[i + 1] !== g[1] || data[i + 2] !== g[2];
    }
    if (!drawn) first = y;
  }
  const box = canvas.getBoundingClientRect();
  return { ready: true, first, lines: (bottom - ruler) / rowPx, top: box.top, height: box.height };
}"""


@cache
def screenshots() -> ModuleType:
    """scripts/screenshots.py as a module, with scripts/ on the path as when it is run."""
    folder = str(ROOT / "scripts")
    if folder not in sys.path:
        sys.path.insert(0, folder)
    path = str(ROOT / "scripts" / "screenshots.py")
    spec = importlib.util.spec_from_file_location(
        "screenshots", path, loader=importlib.machinery.SourceFileLoader("screenshots", path)
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# What the page asks of the scope, written down as it asks
ASKS = """(() => {
  const Given = window.WebSocket;
  window.__scopeAsks = [];
  window.WebSocket = class extends Given {
    send(data) {
      if (typeof data === "string" && data.includes('"radio_scope"')) window.__scopeAsks.push(JSON.parse(data));
      return super.send(data);
    }
  };
})();"""


@pytest.fixture(scope="module")
def scope_page(demo: Any) -> str:
    """The made-up scope of the demo's Dummy HF radio, ten minutes of rows kept, and the asks written down."""
    return str(screenshots().scope_page(demo.radios["dummy-hf"], float(HISTORY_SEC))) + "\n" + ASKS


def card_page(browser: Any, demo: Any, faults: Any, init: str, height: int, speed: str, place: str = "") -> Any:
    stored = {"monitor": "open", "monitorsize": f"{CARD_WIDTH},{height}", "monitorspeed": speed}
    if place:
        stored["monitorplace"] = place
    return drive.opened(browser, demo.url, faults, width=WIDTH, height=VIEW_HEIGHT, stored=stored, init=init)


def drawn_to_the_bottom(page: Any) -> dict[str, Any]:
    """Wait until every line of the picture is drawn (the rows kept have come); return what was measured."""
    try:
        page.wait_for_function(f"() => {{ const m = ({UNDRAWN})(); return m.ready && m.first < 0; }}", polling=250)
    except Exception as failed:
        said = {"measured": page.evaluate(UNDRAWN), "asked": page.evaluate("window.__scopeAsks")}
        raise AssertionError(f"the picture is not drawn to its bottom: {json.dumps(said)}") from failed
    measured: dict[str, Any] = page.evaluate(UNDRAWN)
    return measured


@pytest.mark.parametrize("speed", SPEEDS)
@pytest.mark.parametrize("height", HEIGHTS)
def test_the_monitor_cards_picture_is_drawn_to_its_bottom_at_each_height_and_speed(
    browser: Any, demo: Any, faults: Any, scope_page: str, height: int, speed: str
) -> None:
    with card_page(browser, demo, faults, scope_page, height, speed) as page:
        page.locator(".monitorcard canvas").wait_for()
        card = page.locator(".monitorcard").bounding_box()
        assert card is not None and abs(card["height"] - height) <= 1, f"the card is {card}, not {height} px tall"
        measured = drawn_to_the_bottom(page)
        assert measured["lines"] > 100, measured


def test_a_card_made_taller_keeps_the_top_of_its_picture_and_is_drawn_to_its_new_bottom(
    browser: Any, demo: Any, faults: Any, scope_page: str
) -> None:
    with card_page(browser, demo, faults, scope_page, 600, "slow", place="20,20") as page:
        page.locator(".monitorcard canvas").wait_for()
        before = drawn_to_the_bottom(page)
        handle = page.locator(".monitorcard .sizer-s").bounding_box()
        assert handle is not None
        x, y = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        tops = []
        for step in range(1, 13):
            page.mouse.move(x, y + step * 50)
            tops.append(page.evaluate(UNDRAWN)["top"])
        page.mouse.up()
        assert set(tops) == {before["top"]}, f"the picture's top moved while the card grew: {tops}"
        after = drawn_to_the_bottom(page)
        assert after["top"] == before["top"] and after["height"] >= before["height"] + 590, (before, after)
