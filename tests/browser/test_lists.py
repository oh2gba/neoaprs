"""The lists that grow: the chat of the HF tests tab and the lines put on APRS-IS behind the Internet row.
The demo daemon has neither a chat nor APRS-IS, so the page is told the daemon's frames (`__neoTell`, the
page's own code takes them). Nothing a reader scrolled up looks at moves when a line comes at the bound,
and the lists with lines pass the screen checks."""

from typing import Any

import pytest

from tests.browser import drive
from tests.browser.drive import WIDTHS
from tests.browser.test_every_screen import findings

REVISION = [10**6]
SERVER = "finland.aprs2.net:14580"


def tell(page: Any, message: dict[str, Any]) -> None:
    page.evaluate("m => window.__neoTell(m)", message)


def state(page: Any, topic: str, value: Any) -> None:
    REVISION[0] += 1
    tell(page, {"type": "state", "topic": topic, "rev": REVISION[0], "value": value})


def chat_lines(first: int, last: int) -> dict[str, Any]:
    calls = ("OH2XYZ", "OH2GBA-7", "SM5ABC", "DL1ABC-10")
    return {
        str(n): {
            "id": n,
            "at": f"2026-11-28T10:{n % 60:02d}:00Z",
            "call": calls[n % 4],
            "text": f"CQ test {n} on 7.0541 MHz, hearing you 579 here in the north" + (" and more" * (n % 5)),
            "ours": n % 4 == 1,
        }
        for n in range(first, last + 1)
    }


def sent_line(n: int) -> dict[str, Any]:
    tail = "very long status text without a break " * (n % 7)
    return {
        "at": f"2026-11-28T10:{n % 60:02d}:{n % 60:02d}Z",
        "radio": 1 if n % 3 else None,
        "line": f"OH2XYZ-{n % 9}>APRS,TCPIP*,qAC,OH2TST:!6012.34N/02443.21E-test {n} {tail}",
    }


def first_in_view(page: Any, box: str) -> dict[str, Any]:
    """The first row the reader sees in the list: its text and where it stands on the screen."""
    assert page.locator(box).evaluate("b => b.clientHeight > 50 && b.scrollTop > 0"), "the list is shown, scrolled up"
    return dict(
        page.evaluate(
            """box => { const b = document.querySelector(box); const top = b.getBoundingClientRect().top;
                const row = [...b.children].find(r => r.getBoundingClientRect().top > top + 4);
                return {text: row.textContent, top: row.getBoundingClientRect().top}; }""",
            box,
        )
    )


def stands(page: Any, box: str, text: str) -> float:
    return float(
        page.evaluate(
            "([box, text]) => [...document.querySelector(box).children].find(r => r.textContent === text)"
            ".getBoundingClientRect().top",
            [box, text],
        )
    )


def scrolled_up(page: Any, box: str) -> None:
    page.locator(box).evaluate("b => { b.scrollTop = Math.floor(b.scrollHeight / 3); }")
    drive.settle(page)


def ours(lines: list[str]) -> list[str]:
    return [f for f in lines if any(word in f for word in ("chat", "igate", "Server"))]


def open_sent_lines(page: Any) -> None:
    config = page.evaluate("window.__neoSocket.last.config")
    config["values"].update({"igate/gate": "true", "igate/enabled": "true"})
    state(page, "config", config)
    igate = {"enabled": True, "gate": True, "state": "connected", "server": SERVER, "reason": ""}
    state(page, "igate", {**igate, "gated": 12, "dropped": {}, "last_gated_at": "2026-11-28T10:00:00Z"})
    fold = page.locator(".igatestatus")
    fold.scroll_into_view_if_needed()
    fold.locator("summary").first.click()
    page.locator(".igatesent").wait_for()
    drive.settle(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_the_chat_full_and_scrolled_up_holds_still_when_a_line_comes_and_the_oldest_goes(
    browser: Any, demo: Any, faults: Any, width: int
) -> None:
    with drive.opened(browser, demo.url, faults, width=width, tab="skeds") as page:
        state(page, "chat", {"state": "ok"})
        state(page, "chat_lines", chat_lines(1, 100))
        drive.settle(page)
        assert ours(findings(page, "en")) == []
        scrolled_up(page, ".chat-lines")
        seen = first_in_view(page, ".chat-lines")
        state(page, "chat_lines", chat_lines(2, 101))
        drive.settle(page)
        assert abs(stands(page, ".chat-lines", seen["text"]) - seen["top"]) < 1, "the line read moved"


@pytest.mark.parametrize("width", WIDTHS)
def test_the_sent_lines_full_and_scrolled_up_hold_still_when_a_line_comes_and_read_well(
    browser: Any, demo: Any, faults: Any, width: int
) -> None:
    with drive.opened(browser, demo.url, faults, width=width, tab="settings") as page:
        open_sent_lines(page)
        tell(page, {"type": "igate_sent", "whole": True, "lines": []})
        drive.settle(page)
        assert page.locator(".igatesent .empty").inner_text() == "No packet yet."
        tell(page, {"type": "igate_sent", "whole": True, "lines": [sent_line(n) for n in range(200)]})
        drive.settle(page)
        assert ours(findings(page, "en")) == []
        assert "14580" not in page.locator(".igatestatus").inner_text(), "the port is the log's"
        scrolled_up(page, ".igatesent")
        seen = first_in_view(page, ".igatesent")
        tell(page, {"type": "igate_sent", "whole": False, "lines": [sent_line(200)]})
        drive.settle(page)
        assert abs(stands(page, ".igatesent", seen["text"]) - seen["top"]) < 1, "the line read moved"
        widths = page.evaluate(
            "() => { const b = document.querySelector('.igatesent'); const w = b.clientWidth;"
            " return [w, Math.min(...[...b.querySelectorAll('.igatesent-line')].map(r => r.getBoundingClientRect().width))]; }"
        )
        assert widths[1] > widths[0] * 0.85, f"a line has the list's width, not a column beside the tag: {widths}"
