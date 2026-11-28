"""Show Internet packets heard by radio in the Internet (APRS-IS) group: ticked at first, kept by the daemon when
unticked, and its (i) opens the picture of the three ways a packet reaches the radio, in the page's colours in light
and dark, inside the window at both widths."""

from typing import Any

import pytest

from tests.browser import drive
from tests.browser.drive import WIDTHS

TICK = "#set-igate-show_gated"
INFO = f".field:has({TICK}) .info-toggle"
PICTURE = 'svg.hp[data-picture="gated"]'


def colours(page: Any) -> list[str]:
    return page.evaluate(
        """s => [...document.querySelectorAll(s + ' path')].map(p => getComputedStyle(p).stroke)""", PICTURE
    )


@pytest.mark.parametrize("width", WIDTHS)
def test_the_tick_is_on_its_i_opens_the_picture_in_both_themes_and_the_daemon_keeps_it_unticked(
    browser: Any, own_demo: Any, faults: Any, width: int
) -> None:
    seen: dict[str, list[str]] = {}
    for theme in ("light", "dark"):
        with drive.opened(browser, own_demo.url, faults, width=width, tab="settings", theme=theme) as page:
            tick = page.locator(TICK)
            assert tick.is_checked() and tick.is_enabled()
            button = page.locator(INFO)
            assert button.get_attribute("title") is None
            assert button.get_attribute("aria-label") == "About Internet packets heard by radio"
            button.click()
            picture = page.locator(PICTURE)
            picture.wait_for()
            box = picture.bounding_box()
            assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= width
            seen[theme] = colours(page)
            page.keyboard.press("Escape")
            picture.wait_for(state="detached")
    assert seen["light"] != seen["dark"], "the picture follows the theme"
    with drive.opened(browser, own_demo.url, faults, width=width, tab="settings") as page:
        page.locator(TICK).click()
        page.wait_for_function("s => !document.querySelector(s).checked", arg=TICK)
        drive.settle(page)
    with drive.opened(browser, own_demo.url, faults, width=width, tab="settings") as page:
        assert not page.locator(TICK).is_checked(), "the daemon kept it"
        page.locator(TICK).click()
        page.wait_for_function("s => document.querySelector(s).checked", arg=TICK)
        drive.settle(page)
