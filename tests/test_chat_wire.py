"""The chat through the page socket: the topics `chat` and `chat_lines`, the command `chat_say` and the
message `chat_fresh`, against a small local server (tests/support/fakechat.py)."""

from pathlib import Path
from typing import Any

from neoaprs.services.chat import ENV_URL
from tests.support.env import Env
from tests.support.fakechat import FakeChat, chat_server
from tests.support.wsclient import WsClient


async def started(tmp_path: Path, server: FakeChat | None = None, **settings: str) -> Env:
    e = Env(tmp_path / "data", web=True, settings=settings or None)
    await e.start()
    if server is not None:
        e.ctl.chat._environ = {ENV_URL: server.url}
    return e


async def lines(e: Env) -> tuple[WsClient, dict[str, Any]]:
    page = await e.ws()
    await page.expect("state", "chat")
    return page, (await page.expect("state", "chat_lines"))["value"]


async def test_the_chat_is_off_while_the_update_check_is_off(tmp_path: Path) -> None:
    e = await started(tmp_path)
    page, value = await lines(e)
    assert value == {} and page.topics["chat"] == {"state": "off"}
    await page.send({"cmd": "chat_say", "text": "hello"})
    error = await page.expect("error")
    assert (error["cmd"], error["code"]) == ("chat_say", "chat.unreachable")
    await e.stop()


async def test_the_lines_are_told_to_every_page_a_line_said_is_ours_and_new_lines_of_others_alert_once(
    tmp_path: Path,
) -> None:
    server = await chat_server()
    server.add("OH2XYZ", "history")
    e = await started(tmp_path, server)
    page, _ = await lines(e)
    other, _ = await lines(e)
    await e.ctl.chat.poll()
    await other.until(lambda: len(other.topics["chat_lines"]) == 1)
    assert other.topics["chat_lines"]["1"] == {
        "id": 1,
        "at": "2026-11-28T12:00:00Z",
        "call": "OH2XYZ",
        "text": "history",
        "ours": False,
    }
    assert page.topics["chat"] == {"state": "ok"}
    await page.send({"cmd": "chat_say", "text": "<b>hi</b>  there"})
    await other.until(lambda: len(other.topics["chat_lines"]) == 2)
    assert (
        other.topics["chat_lines"]["2"]["ours"] is True and other.topics["chat_lines"]["2"]["text"] == "<b>hi</b> there"
    )
    assert server.posts[-1]["call"] == "OH2GBA" and len(server.posts[-1]["token"]) == 32
    server.add("OH3ABC", "one")
    server.add("OH3ABC", "two")
    await e.ctl.chat.poll()
    fresh = await page.expect("chat_fresh")
    assert fresh == {"type": "chat_fresh", "count": 2, "id": 4, "call": "OH3ABC", "text": "two"}
    await page.until(lambda: len(page.topics["chat_lines"]) == 4)
    await page.quiet(0.2)
    assert sum(1 for m in page.messages if m.get("type") == "chat_fresh") == 1, "one alert for the lines of one reading"
    await e.stop()


async def test_the_alert_of_the_chat_is_not_told_while_its_kind_is_off(tmp_path: Path) -> None:
    server = await chat_server()
    e = await started(tmp_path, server, **{"messages/chat_alert": "false"})
    page, _ = await lines(e)
    await e.ctl.chat.poll()
    server.add("OH3ABC", "one")
    await e.ctl.chat.poll()
    await page.until(lambda: len(page.topics["chat_lines"]) == 1)
    await page.quiet(0.2)
    assert not any(m.get("type") == "chat_fresh" for m in page.messages)
    await e.stop()


async def test_the_refusals_come_with_codes_and_without_a_call_nothing_is_said(tmp_path: Path) -> None:
    server = await chat_server()
    e = await started(tmp_path, server)
    page, _ = await lines(e)
    for reason, status, code in (
        ("rate", 429, "chat.rate"),
        ("closed", 403, "chat.closed"),
        ("storage", 500, "chat.unreachable"),
    ):
        server.refuse = (reason, status)
        await page.send({"cmd": "chat_say", "text": "hi"})
        error = await page.expect("error")
        assert (error["cmd"], error["code"]) == ("chat_say", code), reason
    await page.until(lambda: page.topics["chat"] == {"state": "closed"})
    await page.send({"cmd": "chat_say", "text": "​"})
    assert (await page.expect("error"))["cmd"] == "chat_say"
    await e.stop()
    e = await started(tmp_path / "nocall", server, **{"station/call": ""})
    page, _ = await lines(e)
    server.refuse, before = None, len(server.posts)
    await page.send({"cmd": "chat_say", "text": "hi"})
    error = await page.expect("error")
    assert (error["cmd"], error["code"]) == ("chat_say", "transmit.call") and len(server.posts) == before
    await e.stop()
