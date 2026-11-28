"""The lists that grow: the chat of the HF tests tab and the lines put on APRS-IS behind the Internet row,
and the past tests that the operator takes off. The demo daemon has neither a chat, nor APRS-IS, nor the
sked board, so the page is told the daemon's frames (`__neoTell`, the page's own code takes them). Nothing a
reader scrolled up looks at moves when a line comes at the bound, nothing above a past test moves when it
goes, and the lists with lines pass the screen checks."""

from datetime import datetime, timedelta
from typing import Any

from neoaprs.clock import iso, utcnow

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


def skeds_with(past: list[str]) -> dict[str, Any]:
    """The topic `skeds` with a test to come and the past tests named, an hour apart, newest first."""

    def at(hours: float) -> str:
        return iso(utcnow().replace(microsecond=0) + timedelta(hours=hours)) or ""

    def row(ident: str, start: float, call: str) -> dict[str, Any]:
        return {"id": ident, "call": call, "from": at(start), "to": at(start + 1), "dial": "7.0541 MHz USB", "note": ""}

    return {
        "state": "ok",
        "fetched_at": at(0),
        "frequencies": [{"band": "40 m", "dial": "7.0541 MHz USB"}],
        "rows": [{**row("0000000000aa", 2, "OH2XYZ"), "ours": False}],
        "past": [row(f"0000000000{n:02d}", -2 - 2 * n, "SM5ABC") for n in range(4) if f"p{n}" in past],
    }


# where each row stands in the pane's content: a shorter list scrolled to its end scrolls back, as any list does
PLACES = """rs => rs.map(r => { const pane = r.closest(".boardpane");
    return r.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop; })"""


@pytest.mark.parametrize("width", WIDTHS)
def test_a_past_test_taken_off_asks_twice_sends_its_ids_and_goes_with_nothing_above_it_moving(
    browser: Any, demo: Any, faults: Any, width: int
) -> None:
    with drive.opened(browser, demo.url, faults, width=width, tab="skeds") as page:
        # (the demo daemon has no board: the command is kept here, not refused there)
        page.evaluate(
            """() => { const s = window.__neoSocket.current; window.__neoKept = []; const send = s.send.bind(s);
                s.send = (d) => JSON.parse(d).cmd === "sked_past_delete" ? window.__neoKept.push(JSON.parse(d)) : send(d); }"""
        )
        state(page, "skeds", skeds_with(["p0", "p1", "p2", "p3"]))
        drive.settle(page)
        page.locator(".sked-past legend button.groupfold").click()  # (folded at first)
        drive.settle(page)
        assert [f for f in findings(page, "en") if "sked" in f] == []
        rows = ".boardpane .sked"
        trash = page.locator(".sked-past .sked").nth(2).locator(".xbtn")
        trash.scroll_into_view_if_needed()
        drive.settle(page)
        tops = page.eval_on_selector_all(rows, PLACES)
        place = trash.bounding_box()
        trash.click()
        drive.settle(page)
        assert trash.bounding_box() == place and trash.get_attribute("class") == "xbtn armed", "sure? in its place"
        assert page.eval_on_selector_all(rows, PLACES) == tops
        trash.click()
        assert page.evaluate("window.__neoKept") == [{"cmd": "sked_past_delete", "ids": ["000000000002"]}]
        state(page, "skeds", skeds_with(["p0", "p1", "p3"]))
        drive.settle(page)
        after = page.eval_on_selector_all(rows, PLACES)
        assert len(after) == len(tops) - 1 and after[:3] == tops[:3], "the board and the newer past tests stay put"


def busy_board() -> dict[str, Any]:
    """The topic `skeds` with five tests to come, each with a note, and two past tests."""
    value = skeds_with(["p0", "p1"])
    first = value["rows"][0]
    start = datetime.fromisoformat(first["from"])
    value["rows"] = [
        {
            **first,
            "id": f"00000000001{n}",
            "call": call,
            "from": iso(start + timedelta(hours=n)),
            "to": iso(start + timedelta(hours=n + 1)),
            "note": "Mercury 10 W, dipole, will listen first",
        }
        for n, call in enumerate(("OH2XYZ", "SM5ABC", "DL1ABC", "OH3XYZ", "G4ABC"))
    ]
    return value


# (the rows of the board, the past tests' title, Plan a test and the chat, where they stand)
COLUMN = """() => { const box = s => document.querySelector(s)?.getBoundingClientRect();
    const rows = [...document.querySelectorAll('#pane-skeds .boardpane > .board > .sked')].map(r => r.getBoundingClientRect());
    const pane = document.querySelector('#pane-skeds .boardpane');
    return { rows: rows.map(r => [r.top, r.bottom]), past: box('.sked-past')?.bottom, plan: box('.sked-planbar')?.top,
      chat: box('#pane-skeds fieldset.chat')?.top, lines: box('.chat-lines')?.height, paneScrolls: pane.scrollHeight > pane.clientHeight + 1,
      wide: [...document.querySelectorAll('#pane-skeds *')].filter(e => e.getBoundingClientRect().right > innerWidth + 1).length }; }"""


@pytest.mark.parametrize(("width", "height"), [(390, 844), (360, 780)])
def test_the_hf_tests_tab_on_a_phone_is_one_column_with_the_board_whole_and_the_chat_reachable_with_the_keyboard_up(
    browser: Any, demo: Any, faults: Any, width: int, height: int
) -> None:
    with drive.opened(browser, demo.url, faults, width=width, height=height, tab="skeds") as page:
        state(page, "skeds", busy_board())
        state(page, "chat", {"state": "ok"})
        state(page, "chat_lines", chat_lines(1, 40))
        drive.settle(page)
        assert ours(findings(page, "en")) == [] and [f for f in findings(page, "en") if "sked" in f] == []
        assert page.locator(".sked-past legend button").get_attribute("aria-expanded") == "false"
        found = page.evaluate(COLUMN)
        assert len(found["rows"]) == 5 and all(bottom - top > 40 for top, bottom in found["rows"]), "each row whole"
        assert found["rows"][-1][1] <= found["past"] <= found["plan"] <= found["chat"], "one column, none over another"
        assert not found["paneScrolls"], "the tab scrolls as one, the board has no scroll of its own"
        assert found["lines"] >= 120 and found["wide"] == 0
        field = page.locator("#pane-skeds fieldset.chat input").first
        field.click()
        page.set_viewport_size({"width": width, "height": height - 300})  # (the keyboard up)
        page.wait_for_timeout(400)  # (the page scrolls the field into view after the keyboard's 300 ms)
        drive.settle(page)
        for part in (field, page.locator("#pane-skeds .chat-compose button[type='submit']")):
            place = part.bounding_box()
            shown = place is not None and place["y"] >= 84 and place["y"] + place["height"] <= height - 300 + 0.5
            assert shown, "the input and Send show"
