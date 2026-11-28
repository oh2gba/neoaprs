"""Typed text is never lost: whatever a person types in a field of a form, and in a conversation's box,
is still there, in its own place, after they change tab, hide the page and come back, lose the page's
connection and get it again, or choose from a list beside it."""

import re
from collections.abc import Callable
from functools import partial
from typing import Any

import pytest

from tests.browser import drive
from tests.browser.drive import LONGEST, WIDTHS

TABS = ("email", "bulletins", "skeds", "objects", "nearby", "beacon", "settings", "stations", "packets")
# What a person would type in a field, by its id: a value the field takes (most take any words).
TYPED = {
    r"set-station-call": "OH2TSU",
    r"set-beacon-power_w|v-1-course|v-1-speed|set-map-radius_km|v-\d+-radius": "42",
    r".*path": "WIDE1-1",
    r"mail-to": "someone@example.org",
    r"sked-dial": "7047.5",
    r"post-group": "TEST",
    r"v-1-name": "TYPED",
}
FIELDS = "input[type=text], input[type=search], input:not([type]), textarea"


def typed_for(field_id: str, n: int) -> str:
    found = next((text for pattern, text in TYPED.items() if field_id and re.fullmatch(pattern, field_id)), None)
    return found if found is not None else f"typed words {n}"


def fields(page: Any, tab: str) -> list[Any]:
    found = page.locator(f"#pane-{tab}").locator(FIELDS)
    return [
        f
        for f in (found.nth(i) for i in range(found.count()))
        if f.is_visible() and f.is_editable() and f.evaluate("e => !e.closest('[inert]')")
    ]


def until_back(page: Any, states: int) -> None:
    """The socket is up again and the daemon has sent the page its state anew."""
    page.wait_for_function(
        "n => window.__neoSocket.states >= n && window.__neoSocket.current.readyState === 1", arg=states
    )
    drive.settle(page)


def drop(page: Any) -> None:
    states = page.evaluate("window.__neoSocket.states + 1")
    page.evaluate("window.__neoSocketDrop()")
    until_back(page, states)


def away_and_back(page: Any, tab: str) -> None:
    drive.show_tab(page, "messages" if tab != "messages" else "stations")
    drive.show_tab(page, tab)


def hide_and_show(page: Any) -> None:
    page.evaluate("window.__neoHide(true)")
    drive.settle(page)
    page.evaluate("window.__neoHide(false)")
    drive.settle(page)


def lost(page: Any, tab: str, typed: dict[int, str], what: str) -> list[str]:
    now = [f.input_value() for f in fields(page, tab)]
    return [
        f"{tab}: after {what} field {i} holds {now[i] if i < len(now) else 'nothing'!r}, not {text!r}"
        for i, text in typed.items()
        if i >= len(now) or now[i] != text
    ]


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("language", ("en", *LONGEST))
def test_text_typed_in_a_form_stays_through_a_tab_change_a_hidden_page_and_a_lost_connection(
    browser: Any, own_demo: Any, faults: Any, language: str, width: int
) -> None:
    found: list[str] = []
    with drive.opened(browser, own_demo.url, faults, language=language, width=width, tab="email") as page:
        typed: dict[str, dict[int, str]] = {}
        for tab in TABS:
            drive.show_tab(page, tab)
            typed[tab] = {}
            for i, field in enumerate(fields(page, tab)):
                field.fill(typed_for(field.get_attribute("id") or "", i))
                typed[tab][i] = field.input_value()  # (as much as the field takes)
        drive.settle(page)
        steps: tuple[tuple[str, Callable[[], None]], ...] = (
            ("the other tabs and back", lambda: None),
            ("the page hidden and shown", partial(hide_and_show, page)),
            ("the connection lost and found", partial(drop, page)),
        )
        for what, step in steps:
            step()
            for tab in TABS:
                drive.show_tab(page, tab)
                found += lost(page, tab, typed[tab], what)
    assert not found, f"{language} at {width} px:\n  " + "\n  ".join(found[:30])


def write(page: Any, service: str, width: int) -> None:
    """Choose a service and press Write, from the list of conversations."""
    back = page.locator(".convo-back")
    if width < 768 and back.is_visible():
        back.click()
    page.locator("#msg-service").select_option(service)
    page.locator(".convlist-services button").click()
    page.locator("#msg-text").wait_for()
    drive.settle(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_a_conversations_words_stay_its_own_through_another_conversation_write_and_a_lost_connection(
    browser: Any, own_demo: Any, faults: Any, width: int
) -> None:
    mine = "words for ANSRVR"
    with drive.opened(browser, own_demo.url, faults, width=width, tab="messages") as page:
        write(page, "ansrvr", width)
        box = page.locator("#msg-text")
        box.fill(mine)
        write(page, "ota_cq", width)
        found = [] if box.input_value() != mine else ["another conversation shows ANSRVR's words"]
        write(page, "ansrvr", width)
        steps: tuple[tuple[str, Callable[[], None]], ...] = (
            ("going back to it with Write", lambda: None),
            ("another tab and back", partial(away_and_back, page, "messages")),
            ("the page hidden and shown", partial(hide_and_show, page)),
            ("the connection lost and found", partial(drop, page)),
        )
        for what, step in steps:
            step()
            if box.input_value() != mine:
                found.append(f"after {what} the box holds {box.input_value()!r}")
    assert not found, f"at {width} px:\n  " + "\n  ".join(found)
