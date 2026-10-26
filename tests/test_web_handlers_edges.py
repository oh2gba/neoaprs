"""The handlers of the page's commands (neoaprs/web/handlers.py) where the tests of the features do not go: following topics and leaving them, a search for the radio whose page has left, RX only for the
status, a query for a call that is none, the settings that are refused or cannot be stored, and an error the page reports when nothing keeps them. Through the page's socket as the page does it, except where
the case cannot be made with a real page (a page that has left, a check that raises what it never does)."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from neoaprs.config import Config
from neoaprs.radiosearch import Trying
from neoaprs.web.handlers import find_radio, page_error
from neoaprs.web.protocol import TOPIC_NAMES
from neoaprs.web.supportwire import PageError
from neoaprs.web.portwire import FindRadio
from tests.support.env import Env


async def with_page(tmp_path: Path, **settings: str) -> tuple[Env, Any]:
    e = Env(tmp_path, web=True, settings=settings or None)
    await e.start()
    await e.until_usable()
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == len(TOPIC_NAMES))
    return e, page


async def test_a_page_that_follows_topics_and_leaves_some_of_them_is_not_told_off(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "subscribe", "topics": ["stations", "packets"]})
    await page.send({"cmd": "unsubscribe", "topics": ["packets"]})
    await page.send({"cmd": "ping"})
    await page.expect("pong")
    assert page.of("error") == []
    await page.send({"cmd": "subscribe", "topics": ["stations", "no-such", "worse", "worst", "still worse"]})
    error = await page.expect("error")
    assert error["code"] == "topic.unknown" and "no topic 'no-such', 'worse', 'worst' (and 1 more)" in error["text"]


async def test_the_status_report_is_refused_while_the_station_only_receives_and_nothing_is_sent(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    assert await e.ctl.save_config(replace(e.ctl.config, station_transmit=False, station_status="QRV", status_source="text"))
    await page.send({"cmd": "status_now"})
    error = await page.expect("error")
    assert (error["cmd"], error["code"], error["text"]) == ("status_now", "transmit.off", "status_now: RX only: nothing is sent")
    assert await e.heard(1, 0.2) == b""


async def test_a_query_for_something_that_is_not_a_call_is_refused_with_the_reason_and_nothing_is_asked(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    await page.send({"cmd": "query", "call": "not a call!", "kind": "position"})
    error = await page.expect("error")
    assert error["cmd"] == "query" and error["text"].startswith("query: ") and "no station" not in error["text"]
    assert await e.heard(1, 0.2) == b""


async def test_settings_that_the_database_would_not_take_are_refused_with_a_code_and_nothing_changes(tmp_path: Path) -> None:
    e, page = await with_page(tmp_path)
    assert e.ctl.db is not None
    await e.ctl.db.close()                                                   # (the file is gone from under the daemon: the store says no)
    await page.send({"cmd": "set_config", "values": {"map/radius_km": "200"}})
    error = await page.expect("error")
    assert (error["cmd"], error["code"]) == ("set_config", "setting.not_stored") and "nothing changed" in error["text"]
    assert e.ctl.config.map_radius_km != 200


async def test_a_check_that_raises_a_plain_value_error_is_the_pages_error_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    e, page = await with_page(tmp_path)

    def odd(cls: type[Config], base: Config, values: Any) -> Config:
        raise ValueError("an odd value")

    monkeypatch.setattr(Config, "checked", classmethod(odd))
    await page.send({"cmd": "set_config", "values": {"map/radius_km": "200"}})
    error = await page.expect("error")
    assert (error["cmd"], error["text"]) == ("set_config", "set_config: an odd value") and error["code"] == "other"


async def test_an_error_the_page_reports_when_no_one_keeps_them_is_let_go() -> None:
    ctx = SimpleNamespace(page_errors=None, conn=None)
    await page_error(ctx, PageError(cmd="page_error", message="boom", stack="", source="vue", at="2026-10-21T12:00:00Z", build="abc"))  # type: ignore[arg-type]


class Finder:
    """The search for the radio as the handler sees it: it tells one try, and a page that has left is what it is told about."""

    def __init__(self) -> None:
        self.cancelled = 0

    async def find(self, trying: Any) -> None:
        trying(Trying("/dev/ttyUSB0", 9600, 1, 4))
        return None

    def cancel(self) -> None:
        self.cancelled += 1


class Page:
    def __init__(self, closed: bool) -> None:
        self.closed = closed
        self.sent: list[dict[str, Any]] = []

    def send(self, message: dict[str, Any]) -> None:
        self.sent.append(message)


@pytest.mark.parametrize("closed, cancelled", [(True, 1), (False, 0)])
async def test_a_search_for_the_radio_is_cancelled_when_the_page_that_asked_has_left_and_not_before(closed: bool, cancelled: int) -> None:
    finder, page = Finder(), Page(closed)
    ctx = SimpleNamespace(ctl=SimpleNamespace(radiofinder=finder), conn=page)
    await find_radio(ctx, FindRadio(cmd="find_radio"))  # type: ignore[arg-type]
    assert finder.cancelled == cancelled
    assert [m["state"] for m in page.sent] == ["trying", "cancelled"]
