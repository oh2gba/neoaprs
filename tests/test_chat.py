"""The chat of the HF tests tab in the daemon (neoaprs/chat.py, neoaprs/services/chat.py): the rules of
a line, hostile chats held to them, the conditional reading, what notifies, and saying a line."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from neoaprs import nodevices, updatefetch
from neoaprs.chat import CHAT_URL, MAX_LINES, MAX_TEXT, SEEN_ROW, chat_of, clean_text, line_of, request_body, seen_of
from neoaprs.config import Config
from neoaprs.services.alerts import Alerts, chat_environment
from neoaprs.services.chat import ENV_URL, EVERY_SEC, JITTER, MAX_WAIT_SEC, ChatError, ChatRoom
from neoaprs.services.updatecheck import ENV_SWITCH
from tests.support.env import remember_stop, until
from tests.support.fakechat import WRITTEN, FakeChat, chat_server
from tests.support.storedb import store_at

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "0123456789abcdef0123456789abcdef"


def line(ident: int = 1, call: str = "OH2XYZ", text: str = "hello", at: str = WRITTEN) -> dict[str, Any]:
    return {"id": ident, "at": at, "call": call, "text": text}


class Room:
    """A chat service on a fake server, with what its signals told."""

    def __init__(self, server: FakeChat, memory: Any = None, call: str = "OH2GBA-7", **more: Any) -> None:
        self.call = call
        environ = more.pop("environ", {ENV_URL: server.url})
        self.service = ChatRoom(
            "0.26.1",
            "linux",
            lambda: Config.from_data({"station/call": self.call}),
            self.token,
            environ=environ,
            memory=memory,
            draw=lambda low, high: 0.0,
            **more,
        )
        remember_stop(self.service.stop)
        self.moved: list[list[int]] = []
        self.fresh: list[list[str]] = []
        self.changed = 0
        self.service.lines_changed.connect(self.moved.append)
        self.service.fresh.connect(lambda lines: self.fresh.append([f"{x.call}: {x.text}" for x in lines]))
        self.service.changed.connect(self._changed)

    def _changed(self) -> None:
        self.changed += 1

    async def token(self) -> str:
        return TOKEN


# ---- the rules of a line ------------------------------------------------------------------------


def test_the_text_of_a_line_is_cleaned_as_the_vectors_say_and_the_server_holds() -> None:
    vectors = json.loads((ROOT / "ui" / "src" / "protocol" / "vectors.json").read_text(encoding="utf-8"))
    cases = vectors["chat_texts"]
    assert cases and all(clean_text(c["input"]) == c["text"] for c in cases)
    texts = {c["input"]: c["text"] for c in cases}
    assert texts["a​b⁠c﻿d"] == "abcd" and texts["‮evil‬"] == "evil", "invisible ones go"
    assert texts["5° up € \U0001f642 \U0001f4fb x"] == "5° up € \U0001f642 \U0001f4fb x", "symbols stay"
    assert texts["<b>&amp;</b> <script>alert(1)</script>"] == "<b>&amp;</b> <script>alert(1)</script>", "markup is text"
    assert {len(c["text"]) for c in cases} >= {0, MAX_TEXT} and max(len(c["text"]) for c in cases) == MAX_TEXT


def hostile_lines() -> dict[str, Any]:
    bad: dict[str, Any] = {}
    for name, ident in {"zero": 0, "negative": -1, "text id": "1", "bool": True, "float": 1.5, "huge": 2**60}.items():
        bad[f"{name} id"] = {**line(), "id": ident}
    for name, call in {"lower": "oh2xyz", "ssid 0": "OH2XYZ-0", "slash": "OH2XYZ/P", "none": None, "empty": ""}.items():
        bad[f"{name} call"] = {**line(), "call": call}
    for name, text in {
        "empty": "",
        "spaced": " hi",
        "control": "a\x07b",
        "long": "x" * (MAX_TEXT + 1),
        "number": 5,
    }.items():
        bad[f"{name} text"] = {**line(), "text": text}
    for name, at in {"no zone": "2026-11-28T12:00:00", "no day": "2026-02-30T10:00:00Z", "none": None}.items():
        bad[f"{name} time"] = {**line(), "at": at}
    bad["not an object"] = ["1", "OH2XYZ"]
    return bad


@pytest.mark.parametrize("entry", list(hostile_lines().values()), ids=list(hostile_lines()))
def test_a_bad_line_is_dropped_alone(entry: Any) -> None:
    assert line_of(entry) is None
    chat = chat_of({"v": 1, "closed": False, "lines": [entry, line(2)]})
    assert chat is not None and [x.id for x in chat.lines] == [2]


def test_a_chat_keeps_the_newest_hundred_lines_oldest_first_and_an_id_once() -> None:
    entries = [line(n, text=f"line {n}") for n in range(150, 0, -1)] + [line(150, text="again")]
    chat = chat_of({"v": 1, "written": WRITTEN, "closed": True, "lines": entries})
    assert chat is not None and chat.closed and len(chat.lines) == MAX_LINES
    assert [x.id for x in chat.lines] == list(range(51, 151)) and chat.lines[-1].text == "line 150"
    for broken in ({"v": 2, "lines": []}, {"v": True, "lines": []}, {"v": 1}, {"v": 1, "lines": {}}, [], "x"):
        assert chat_of(broken) is None, broken
    assert chat_of({"v": 1, "closed": "no", "lines": []}) is None
    assert seen_of("12") == 12 and seen_of(None) is None and seen_of("x") is None and seen_of("0") is None


def test_a_post_is_the_line_with_the_token_and_the_call() -> None:
    assert json.loads(request_body(TOKEN, "OH2GBA-7", "café")) == {
        "action": "say",
        "token": TOKEN,
        "call": "OH2GBA-7",
        "text": "café",
    }
    assert "café".encode() in request_body(TOKEN, "OH2GBA", "café"), "UTF-8 as it is, so a line fits 1024 bytes"
    assert len(request_body(TOKEN, "OH2GBA-15", "\U0001f642" * MAX_TEXT)) <= 1024


# ---- reading ------------------------------------------------------------------------------------


async def test_the_first_reading_of_a_new_installation_tells_the_lines_and_notifies_of_none(tmp_path: Path) -> None:
    server = await chat_server()
    server.add("OH2XYZ", "older")
    server.add("OH3ABC", "newer")
    store = await store_at(tmp_path / "neoaprs.sqlite")
    room = Room(server, store)
    await room.service.poll()
    assert [(x.id, x.text) for x in room.service.lines()] == [(1, "older"), (2, "newer")]
    assert room.moved == [[1, 2]] and room.fresh == [] and room.service.state == "ok"
    assert await store.setting(SEEN_ROW) == "2"


async def test_new_lines_of_others_notify_once_for_a_reading_and_ones_own_never() -> None:
    server = await chat_server()
    server.add("OH2XYZ", "history")
    room = Room(server)
    await room.service.poll()
    server.add("OH2XYZ", "one")
    server.add("OH2GBA-7", "mine, said from elsewhere")
    server.add("OH3ABC", "two")
    await room.service.poll()
    assert room.fresh == [["OH2XYZ: one", "OH3ABC: two"]]
    assert room.moved[-1] == [2, 3, 4]
    assert [room.service.ours(x) for x in room.service.lines()] == [False, False, True, False]


async def test_an_unchanged_chat_is_a_304_by_its_etag_and_nothing_is_told() -> None:
    server = await chat_server()
    server.add("OH2XYZ", "hello")
    room = Room(server)
    await room.service.poll()
    await room.service.poll()
    assert server.gets[0].get("if-none-match") is None and server.gets[1]["if-none-match"] == '"v1"'
    assert server.gets[1]["if-modified-since"] == "Sat, 28 Nov 2026 12:00:01 GMT"
    assert room.moved == [[1]] and room.service.asked == 2 and len(room.service.lines()) == 1
    server.add("OH3ABC", "new")
    await room.service.poll()
    assert room.moved == [[1], [2]] and room.fresh == [["OH3ABC: new"]]


async def test_a_host_without_an_etag_is_asked_by_last_modified_and_one_without_either_by_written_and_newest() -> None:
    server = await chat_server()
    server.etag = False
    server.add("OH2XYZ", "hello")
    room = Room(server)
    await room.service.poll()
    await room.service.poll()
    assert "if-none-match" not in server.gets[1] and server.gets[1]["if-modified-since"].endswith("12:00:01 GMT")
    assert room.moved == [[1]]
    server.modified = False
    await room.service.poll()
    await room.service.poll()
    assert "if-modified-since" not in server.gets[3] and "if-none-match" not in server.gets[3]
    assert room.moved == [[1]], "the same `written` and newest id: nothing changed"
    server.add("OH3ABC", "new")
    server.written = "2026-11-28T12:05:00Z"
    await room.service.poll()
    assert room.moved == [[1], [2]] and room.fresh == [["OH3ABC: new"]]


async def test_after_a_restart_only_lines_newer_than_the_newest_seen_notify(tmp_path: Path) -> None:
    server = await chat_server()
    server.add("OH2XYZ", "seen")
    store = await store_at(tmp_path / "neoaprs.sqlite")
    await Room(server, store).service.poll()
    server.add("OH3ABC", "while we were off")
    again = Room(server, store)
    await again.service.poll()
    assert again.fresh == [["OH3ABC: while we were off"]] and len(again.service.lines()) == 2


async def test_a_chat_whose_ids_went_back_is_the_new_baseline_and_notifies_of_nothing(tmp_path: Path) -> None:
    server = await chat_server()
    store = await store_at(tmp_path / "neoaprs.sqlite")
    await store.put_settings({SEEN_ROW: "500"})
    server.add("OH2XYZ", "a chat made anew")
    room = Room(server, store)
    await room.service.poll()
    assert room.fresh == [] and await store.setting(SEEN_ROW) == "1"
    server.add("OH3ABC", "next")
    await room.service.poll()
    assert room.fresh == [["OH3ABC: next"]]


async def test_no_chat_yet_is_an_empty_one_and_a_line_the_server_no_longer_has_goes(caplog: Any) -> None:
    server = await chat_server()
    room = Room(server)
    await room.service.poll()
    assert room.service.state == "ok" and room.service.lines() == []
    server.add("OH2XYZ", "a")
    server.add("OH2XYZ", "b")
    await room.service.poll()
    assert server.lines is not None
    server.lines = server.lines[1:]
    server.version += 1
    await room.service.poll()
    assert room.moved[-1] == [1] and [x.id for x in room.service.lines()] == [2]


async def test_a_server_that_does_not_answer_is_said_once_in_the_log_and_asked_less_often(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.chat")
    server = await chat_server()
    server.add("OH2XYZ", "kept")
    room = Room(server)
    await room.service.poll()
    server.down = True
    for _ in range(4):
        await room.service.poll()
    assert room.service.state == "offline" and [x.text for x in room.service.lines()] == ["kept"]
    told = [r for r in caplog.records if "could not be read" in r.getMessage()]
    assert (
        len(told) == 1
        and told[0].levelno == logging.INFO
        and not any(r.levelno >= logging.WARNING for r in caplog.records)
    )
    assert room.service.failures == 4 and room.service.wait_sec() == EVERY_SEC * 16
    room.service.failures = 30
    assert room.service.wait_sec() == MAX_WAIT_SEC
    server.down = False
    await room.service.poll()
    assert room.service.state == "ok" and room.service.failures == 0 and room.service.wait_sec() == EVERY_SEC
    assert sum("is read again" in r.getMessage() for r in caplog.records) == 1


async def test_the_wait_is_jittered_within_its_share() -> None:
    server = await chat_server()
    drawn: list[tuple[float, float]] = []

    def draw(low: float, high: float) -> float:
        drawn.append((low, high))
        return high

    service = ChatRoom("0.26.1", "linux", lambda: Config.from_data({}), Room(server).token, environ={}, draw=draw)
    assert service.wait_sec() == pytest.approx(EVERY_SEC * (1 + JITTER)) and drawn == [(-JITTER, JITTER)]


async def test_the_daemon_asks_the_chat_at_its_pace_while_it_runs() -> None:
    server = await chat_server()
    server.add("OH2XYZ", "hello")
    room = Room(server, every_sec=0.01)
    await room.service.start()
    await until(lambda: room.service.asked >= 3)
    assert len(room.service.lines()) == 1 and room.moved == [[1]]


async def test_the_switch_and_an_address_of_another_computer_keep_it_from_asking_anyone() -> None:
    server = await chat_server()
    off = Room(server, environ={ENV_SWITCH: "0", ENV_URL: server.url})
    await off.service.start()
    await off.service.poll()
    assert server.gets == [] and off.service.state == "off" and off.service.lines() == []
    with pytest.raises(ChatError) as e:
        await off.service.say("hello")
    assert e.value.code == "chat.unreachable" and server.posts == []
    for bad in ("https://neo.oh2gba.eu.example/chat.json", "http://10.0.0.1/chat.json", "file:///etc/passwd", ""):
        assert Room(server, environ={ENV_URL: bad}).service.url == CHAT_URL, bad
    assert CHAT_URL == "https://neo.oh2gba.eu/chat.json"


@pytest.fixture
def under_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The no-devices switch is on in this test's own process too (tests/conftest.py lifts it for
    every test that does not ask for a fixture of this name)."""
    monkeypatch.setenv(nodevices.ENV, "1")
    monkeypatch.setattr(nodevices, "_told", set())


async def test_under_the_no_devices_switch_the_real_chat_is_neither_read_nor_posted_to(
    under_the_switch: None,
) -> None:
    assert await updatefetch.fetch_fresh(CHAT_URL, "0.26.1", "linux", "", "", 1024) is None
    assert updatefetch.post_json("https://neo.oh2gba.eu/api/v1/chat.php", b"{}", "0.26.1", "linux") is None


# ---- saying -------------------------------------------------------------------------------------


async def test_a_line_is_said_with_the_token_and_the_call_as_configured_and_is_ours_without_notifying() -> None:
    server = await chat_server()
    server.add("OH2XYZ", "hello")
    room = Room(server, call="oh2gba-7")
    await room.service.poll()
    server.add("OH3ABC", "between")
    await room.service.say("  hi   there\t")
    assert server.posts == [{"action": "say", "token": TOKEN, "call": "OH2GBA-7", "text": "hi there"}]
    last = room.service.lines()[-1]
    assert (last.id, last.text) == (3, "hi there") and room.service.ours(last)
    assert room.fresh == [["OH3ABC: between"]], "the line of another that came with the answer, not ours"


async def test_a_refusal_says_its_code_and_a_closed_chat_is_closed_for_that_call() -> None:
    server = await chat_server()
    server.add("OH2XYZ", "hello")
    room = Room(server)
    await room.service.poll()
    server.refuse = ("rate", 429)
    with pytest.raises(ChatError) as e:
        await room.service.say("hi")
    assert e.value.code == "chat.rate"
    server.refuse = ("closed", 403)
    with pytest.raises(ChatError) as e:
        await room.service.say("hi")
    assert e.value.code == "chat.closed" and room.service.state == "closed", "blocked: closed for this call"
    room.call = "OH3ABC"
    assert room.service.state == "ok"
    server.refuse = ("storage", 500)
    with pytest.raises(ChatError) as e:
        await room.service.say("hi")
    assert e.value.code == "chat.unreachable"
    server.refuse, server.closed = None, True
    server.version += 1
    await room.service.poll()
    assert room.service.state == "closed"


async def test_a_server_that_cannot_be_reached_keeps_nothing_and_says_so() -> None:
    server = await chat_server()
    room = Room(server)
    server.down = True
    with pytest.raises(ChatError) as e:
        await room.service.say("hi")
    assert e.value.code == "chat.unreachable" and room.service.state == "offline"
    with pytest.raises(ValueError):
        await room.service.say("​ ")


# ---- the alert ----------------------------------------------------------------------------------


def test_the_alert_command_is_told_the_newest_line_and_how_many_came() -> None:
    chat = chat_of({"v": 1, "lines": [line(1, "OH2XYZ", "one"), line(2, "OH3ABC", "two")]})
    assert chat is not None
    one = chat_environment(list(chat.lines[:1]), {})
    assert (one["NEOAPRS_KIND"], one["NEOAPRS_TITLE"], one["NEOAPRS_FROM"], one["NEOAPRS_TEXT"]) == (
        "chat",
        "NeoAPRS chat: OH2XYZ",
        "OH2XYZ",
        "one",
    )
    both = chat_environment(list(chat.lines), {})
    assert both["NEOAPRS_TITLE"] == "NeoAPRS chat: 2 new lines" and both["NEOAPRS_TEXT"] == "OH3ABC: two"
    assert both["NEOAPRS_AT"] == WRITTEN and both["NEOAPRS_MSG_ID"] == ""


async def test_the_alert_runs_for_the_chat_only_while_its_kind_is_on() -> None:
    chat = chat_of({"v": 1, "lines": [line(1)]})
    assert chat is not None
    for value, runs in (("false", 0), ("true", 1)):
        alerts = Alerts(lambda v=value: Config.from_data({"messages/chat_alert": v, "messages/alert_command": "true"}))  # type: ignore[misc]
        remember_stop(alerts.stop)
        alerts.chat(list(chat.lines))
        assert len(alerts._tasks) == runs, value
        await alerts.stop()
