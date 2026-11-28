"""Every tab at a phone's and a desktop's width in every language, element by element: nothing past its
box or the screen, no text cut or drawn outside its box, no select narrower than an entry, no siblings over
each other, no text at the very side of its box, and the house rules the tree shows."""

from typing import Any

import pytest

from tests.browser import drive, rules
from tests.browser.drive import LANGUAGES, TABS, WIDTHS

EDGE_GAP = 3  # px of room text keeps from the side of its box


def findings(page: Any, language: str) -> list[str]:
    """Everything the checks find on the page as it is now."""
    arrow = page.evaluate("NeoChecks.arrow()")
    calls = (
        ("outside", [None, rules.selector({**rules.OUTSIDE, **rules.CUT})]),
        ("clipped", [None, rules.selector({**rules.ELLIPSIS, **rules.CUT})]),
        ("selects", [None, arrow, rules.selector(rules.SELECTS), rules.selector(rules.SELECTS_CUT)]),
        ("overlaps", [None, rules.selector(rules.OVERLAPS)]),
        ("edges", [None, EDGE_GAP, rules.selector({**rules.EDGES, **rules.ELLIPSIS, **rules.CUT})]),
    )
    found = [line for check, args in calls for line in page.evaluate(f"a => NeoChecks.{check}(...a)", args)]
    found += (
        page.evaluate("NeoChecks.infos()") + page.evaluate("NeoChecks.sameIds()") + page.evaluate("NeoChecks.columns()")
    )
    texts = [(where, text) for where, text in page.evaluate("NeoChecks.texts(null)")]
    shown = [
        (where, text) for where, text in page.evaluate("s => NeoChecks.texts(null, s)", rules.selector(rules.MAY_SHOW))
    ]
    found += rules.internals(shown)
    if language != "en":
        found += rules.untranslated(language, texts)
    return found


def open_everything(page: Any, tab: str) -> None:
    """Open every (i) of the tab that opens in place and every disclosure, as a curious person would."""
    page.evaluate(
        """tab => {
          const pane = document.getElementById('pane-' + tab);
          for (const b of pane.querySelectorAll('.info-toggle[aria-controls][aria-expanded=false]')) if (b.checkVisibility()) b.click();
          for (const d of pane.querySelectorAll('details:not([open])')) if (d.checkVisibility()) d.open = true;
        }""",
        tab,
    )
    drive.settle(page)


def walk(page: Any, language: str, tabs: tuple[str, ...]) -> list[str]:
    found = []
    for tab in tabs:
        drive.show_tab(page, tab)
        found += [f"{tab}: {line}" for line in findings(page, language)]
        open_everything(page, tab)
        found += [f"{tab}, all open: {line}" for line in findings(page, language)]
    return list(dict.fromkeys(found))


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("language", LANGUAGES)
def test_every_tab_holds_together_element_by_element(
    browser: Any, demo: Any, faults: Any, language: str, width: int
) -> None:
    with drive.opened(browser, demo.url, faults, language=language, width=width, tab="messages") as page:
        found = walk(page, language, TABS)
    assert not found, f"{language} at {width} px:\n  " + "\n  ".join(found[:40])


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("language", LANGUAGES)
def test_the_map_in_both_themes_and_the_settings_in_the_dark_hold_together(
    browser: Any, demo: Any, faults: Any, language: str, width: int
) -> None:
    with drive.opened(browser, demo.url, faults, language=language, width=width, tab="settings", theme="dark") as page:
        found = walk(page, language, ("settings",))
    for theme in ("light", "dark"):
        with drive.opened(browser, demo.url, faults, language=language, width=width, theme=theme, view="map") as page:
            found += [f"map, {theme}: {line}" for line in findings(page, language)]
    assert not found, f"{language} at {width} px:\n  " + "\n  ".join(found[:40])
