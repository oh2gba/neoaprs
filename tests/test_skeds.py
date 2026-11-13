"""The sked board in the daemon (neoaprs/skeds.py, neoaprs/services/skeds.py): the rules of a row and the hostile boards that are held to them (a made-up bad row is dropped alone, the rest of the board stands, whatever the server says), the service's rhythm
(a minute after the start, every six hours, when a page shows the tab and never more often than every 15 minutes, never with the update check off), the last board kept and told at the start, what has ended dropped by the daemon's own clock, the installation's secret
token (made when it is first needed, kept, sent only with a post, never when reading, never in the log, the bundle or `neoaprs db list`), our ids, and every refusal of the server: the ones the operator can do something about are errors with codes, the others are
the log's. The service is tried with fakes of the two network calls and with the real ones against a small server on this computer (tests/support/fakeskeds.py)."""
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from neoaprs import nodevices, updatefetch
from neoaprs.cli.redaction import hides, shown_value
from neoaprs.cli.supportgather import secrets_of, settings_json
from neoaprs.clock import iso, utc
from neoaprs.config import Config
from neoaprs.services.skeds import ENV_SWITCH, ENV_URL, EVERY_SEC, MAX_BYTES, RETRY_SEC, SKEDS_EVERY_SEC, SkedError, Skeds
from neoaprs.skeds import MAX_ROWS, OURS_ROW, SKED_TOKEN, SKEDS_ROW, SKEDS_URL, TOKEN, Board, board_text, clean_note, endpoint_url, kept_board, kept_ids, our_call, parse_board, plain_note, request_body, when
from neoaprs.updatefetch import fetch_answer, post_board
from neoaprs.versions import Frequency, is_dial
from tests.support.env import remember_stop, until
from tests.support.fakeskeds import skeds_server
from tests.support.storedb import store_at

NOW = utc(2026, 11, 14, 12, 0, 0)
CALL = "OH2GBA"


def at(hours: float) -> str:
    return iso(NOW + timedelta(hours=hours)) or ""


def row(ident: str = "7f3a9c21d4e0", call: str = "OH2XYZ", start: float = 6.0, end: float | None = None, dial: str = "7.0541 MHz USB", note: str = "Mercury, 10 W") -> dict[str, Any]:
    return {"id": ident, "call": call, "from": at(start), "to": at(start + 2 if end is None else end), "dial": dial, "note": note}


def board(*rows: Any, **more: Any) -> bytes:
    return json.dumps({"v": 1, "written": at(0), "closed": False, "skeds": list(rows), **more}).encode()


GOOD = row()


# ---- the rules of a row and the hostile boards ------------------------------------------------------------------------------------------------------

def test_a_good_board_is_read_in_the_order_of_the_start_and_the_id() -> None:
    found = parse_board(board(row("bbbbbbbbbbbb", start=9), row("aaaaaaaaaaaa", start=9), row("cccccccccccc", start=2)), NOW)
    assert found is not None and not found.closed
    assert [s.id for s in found.skeds] == ["cccccccccccc", "aaaaaaaaaaaa", "bbbbbbbbbbbb"]
    first = found.skeds[0]
    assert (first.call, first.start, first.end, first.dial, first.note) == ("OH2XYZ", NOW + timedelta(hours=2), NOW + timedelta(hours=4), "7.0541 MHz USB", "Mercury, 10 W")


def hostile_rows() -> dict[str, Any]:
    """Made-up rows, each wrong in one way (the server checks the same and more, but nothing it says is believed)."""
    bad: dict[str, Any] = {}
    for name, ident in {"short id": "7f3a9c21d4e", "long id": "7f3a9c21d4e00", "upper id": "7F3A9C21D4E0", "not hex": "7f3a9c21d4eg", "path id": "../../etc/pa", "empty id": "", "number id": 123456789012, "null id": None, "newline id": "7f3a9c21d4e\n"}.items():
        bad[name] = {**GOOD, "id": ident}
    for name, call in {"lower call": "oh2xyz", "placeholder": "N0CALL", "nocall": "NOCALL", "ssid 0": "OH2XYZ-0", "ssid 16": "OH2XYZ-16", "markup": "<script>", "one letter": "A", "slash": "OH2XYZ/P", "newline": "OH2XYZ\n",
                       "non ascii": "ÖH2XYZ", "number": 2, "null": None, "empty": "", "no digit": "ABCDEF", "no letter": "123456", "seven": "OH2XYZ12", "spaces": " OH2XYZ "}.items():
        bad[f"call {name}"] = {**GOOD, "call": call}
    for key in ("from", "to"):
        for name, value in {"no Z": "2026-11-14T18:00:00", "offset": "2026-11-14T18:00:00+00:00", "feb 30": "2026-02-30T18:00:00Z", "hour 25": "2026-11-14T25:00:00Z", "number": 1783000000, "null": None, "newline": "2026-11-14T18:00:00Z\n",
                            "words": "tomorrow"}.items():
            bad[f"{key} {name}"] = {**GOOD, key: value}
    bad["to before from"] = {**GOOD, "from": at(8), "to": at(6)}
    bad["to is from"] = {**GOOD, "from": at(6), "to": at(6)}
    bad["over 24 hours"] = {**GOOD, "from": at(2), "to": at(26.01)}
    bad["ended"] = {**GOOD, "from": at(-3), "to": at(-1)}
    bad["ends now"] = {**GOOD, "from": at(-3), "to": at(0)}
    bad["begins in 2 months"] = {**GOOD, "from": at(24 * 60), "to": at(24 * 60 + 2)}
    for name, dial in {"fm": "7.0541 MHz FM", "no mode": "7.0541 MHz", "newline": "7.0541 MHz USB\n", "huge": "1234.5 MHz USB", "markup": "<b>7.0541 MHz USB</b>", "number": 7.0541, "null": None}.items():
        bad[f"dial {name}"] = {**GOOD, "dial": dial}
    for name, note in {"null": None, "number": 5, "list": ["x"], "81 characters": "x" * 81, "newline": "line one\nline two", "tab": "a\tb", "nul": "a\x00b", "escape": "\x1b[31mred", "bidi override": "gnp.exe‮gpj",
                       "bidi isolate": "a⁦b", "zero width": "a​b", "no break space": "a b", "line separator": "a b", "bom": "﻿a", "private use": "ab", "lone surrogate": "a\ud800b", "unassigned": "a\U000e0001b"}.items():
        bad[f"note {name}"] = {**GOOD, "note": note}
    bad["no id"] = {k: v for k, v in GOOD.items() if k != "id"}
    bad["no call"] = {k: v for k, v in GOOD.items() if k != "call"}
    bad["no from"] = {k: v for k, v in GOOD.items() if k != "from"}
    bad["no dial"] = {k: v for k, v in GOOD.items() if k != "dial"}
    for name, entry in {"text": "oh2xyz", "list": [GOOD], "null": None, "number": 7, "true": True}.items():
        bad[f"entry {name}"] = entry
    return bad


@pytest.mark.parametrize("name", sorted(hostile_rows()))
def test_a_hostile_row_is_dropped_alone_and_the_rest_of_the_board_stands(name: str) -> None:
    other = row("aaaaaaaaaaaa", call="OH2ABC", start=3)
    found = parse_board(board(hostile_rows()[name], other), NOW)
    assert found is not None and [s.id for s in found.skeds] == ["aaaaaaaaaaaa"], name


def test_a_board_that_is_not_one_is_none_and_the_last_board_stands() -> None:
    for body in (b"", b"<html>", b"[]", b'"skeds"', b"null", b"{}", b'{"v": 1}', b'{"v": 2, "skeds": []}', b'{"v": "1", "skeds": []}', b'{"v": true, "skeds": []}', b'{"v": 1, "skeds": {"a": 1}}', b'{"v": 1, "skeds": "x"}',
                 b'{"v": 1, "skeds": [], "closed": "yes"}', b'{"v": 1, "skeds": [], "closed": 1}', b'{"v": 1, "skeds": [], "closed": null}', b"\xff\xfe", b"[" * 100000 + b"]" * 100000, b"{" * 5000):
        assert parse_board(body, NOW) is None, body[:30]
    assert parse_board(b'{"v": 1, "skeds": []}', NOW) == Board(False, ()), "`closed` is false when the board does not say"
    assert parse_board(b'{"v": 1, "skeds": [], "closed": true}', NOW) == Board(True, ()), "a board the moderator closed"


def test_a_row_may_carry_more_than_it_needs_and_the_note_may_be_markup_which_the_page_shows_as_text() -> None:
    found = parse_board(board({**GOOD, "token": "x" * 32, "hash": "y", "extra": [1], "note": "<script>alert(1)</script> & more"}), NOW)
    assert found is not None and found.skeds[0].note == "<script>alert(1)</script> & more"
    assert not hasattr(found.skeds[0], "token"), "only what a sked is is kept"


def test_a_board_holds_at_most_a_hundred_rows_ten_of_one_call_and_an_id_once() -> None:
    many = [row(f"{i:012x}", call=f"OH{i % 40:02d}A", start=1 + i / 100) for i in range(300)]
    found = parse_board(board(*many), NOW)
    assert found is not None and len(found.skeds) == MAX_ROWS == 100 and all(sum(s.call == c for s in found.skeds) <= 10 for c in {s.call for s in found.skeds})
    flood = [row(f"{i:012x}", call="OH2GBA", start=1 + i / 100) for i in range(30)] + [row("ffffffffffff", call="OH9ABC")]
    found = parse_board(board(*flood), NOW)
    assert found is not None and [s.call for s in found.skeds].count("OH2GBA") == 10 and "ffffffffffff" in {s.id for s in found.skeds}, "a call that floods the board leaves room for the others"
    ssids = [row(f"{i:012x}", call=f"OH2GBA-{i}", start=1 + i / 100) for i in range(15)]
    found = parse_board(board(*ssids), NOW)
    assert found is not None and len(found.skeds) == 10, "the SSID makes no other call"
    twice = parse_board(board(row("aaaaaaaaaaaa", call="OH2ABC"), row("aaaaaaaaaaaa", call="OH2DEF")), NOW)
    assert twice is not None and [s.call for s in twice.skeds] == ["OH2ABC"]
    huge = parse_board(board(*([5] * 5000), row("aaaaaaaaaaaa", call="OH2ABC")), NOW)
    assert huge is not None and huge.skeds == (), "only the first thousand entries are looked at"


def test_a_row_is_judged_by_the_readers_own_clock() -> None:
    body = board(row("aaaaaaaaaaaa", start=-1, end=1), row("bbbbbbbbbbbb", start=2, end=3))
    assert [s.id for s in (parse_board(body, NOW) or Board(False, ())).skeds] == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]
    assert [s.id for s in (parse_board(body, NOW + timedelta(hours=1)) or Board(False, ())).skeds] == ["bbbbbbbbbbbb"], "ended by the clock: dropped though the file still has it"
    assert parse_board(board(row(start=24 * 30 + 12, end=24 * 30 + 14)), NOW) is not None, "a month ahead is believed: the clocks may differ a little"


def test_the_notes_form_the_calls_form_and_the_dials_form() -> None:
    assert plain_note("") and plain_note("Mercury, 10 W") and plain_note("café 7 MHz ✓") and plain_note("x" * 80) and not plain_note("x" * 81) and not plain_note("a\nb") and not plain_note(None)
    assert clean_note("  Mercury,\t10 W \n today ") == "Mercury, 10 W today" and clean_note("a‮b​c") == "a b c" and len(clean_note("x" * 200)) == 80 and clean_note("\x00\x01") == ""
    assert [our_call(c) for c in ("oh2gba", " OH2GBA-0 ", "OH2GBA-7", "OH2GBA-16", "N0CALL", "", "AB", "OH2GBA/P", "ÖH2GBA")] == ["OH2GBA", "OH2GBA", "OH2GBA-7", "", "", "", "", "", ""]
    assert is_dial("7.0541 MHz USB") and not is_dial("7.0541 MHz USB\n") and not is_dial("7.0541 MHz CW")
    assert when("2026-11-14T18:00:00Z") == datetime(2026, 11, 14, 18, 0, tzinfo=UTC) and when("2026-11-14T18:00:00Z\n") is None and when("2026-02-30T00:00:00Z") is None and when(5) is None


def test_the_last_board_is_kept_as_the_server_writes_it_and_a_row_edited_by_hand_is_as_good_as_none() -> None:
    found = parse_board(board(GOOD), NOW)
    assert found is not None
    kept = kept_board(board_text(found, NOW), NOW)
    assert kept == (found, NOW)
    for text in ("", "garbage", "[]", '{"v": 1}', '{"v": 1, "skeds": [], "fetched": 5}'):
        again = kept_board(text, NOW)
        assert again is None or again == (Board(False, ()), None), text
    assert kept_ids(json.dumps(["aaaaaaaaaaaa", "bad", 5, "BBBBBBBBBBBB"])) == ["aaaaaaaaaaaa"] and kept_ids("garbage") == [] and kept_ids(None) == [] and kept_ids('{"a": 1}') == []


def test_the_request_is_json_of_the_servers_own_form_and_the_address_is_on_the_same_server() -> None:
    body = json.loads(request_body("add", "a" * 32, {"call": CALL, "from": at(1), "to": at(2), "dial": "7.0541 MHz USB", "note": "ä"}))
    assert body == {"action": "add", "token": "a" * 32, "call": CALL, "from": at(1), "to": at(2), "dial": "7.0541 MHz USB", "note": "ä"}
    assert endpoint_url(SKEDS_URL) == "https://neo.oh2gba.eu/api/v1/skeds.php" and endpoint_url("http://127.0.0.1:8123/skeds.json") == "http://127.0.0.1:8123/api/v1/skeds.php"


# ---- the service with fakes of the two calls --------------------------------------------------------------------------------------------------------

class Net:
    """The two network calls as fakes: the answers in turn (None is a server that is not there), and what was asked."""

    def __init__(self, *reads: tuple[int, bytes] | None, posts: list[tuple[int, Any] | None] | None = None) -> None:
        self.reads = list(reads)
        self.posts = list(posts or [])
        self.read_calls: list[tuple[str, str, str, int]] = []
        self.post_calls: list[tuple[str, dict[str, Any], str, str]] = []
        self.post_limits: list[int] = []
        self.last_read: tuple[int, bytes] | None = (200, board())

    async def fetch(self, url: str, version: str, platform: str, max_bytes: int) -> tuple[int, bytes] | None:
        self.read_calls.append((url, version, platform, max_bytes))
        return self.reads.pop(0) if self.reads else self.last_read

    async def post(self, url: str, body: bytes, version: str, platform: str, max_bytes: int) -> tuple[int, bytes] | None:
        self.post_calls.append((url, json.loads(body), version, platform))
        self.post_limits.append(max_bytes)
        answer = self.posts.pop(0) if self.posts else None
        return None if answer is None else (answer[0], answer[1] if isinstance(answer[1], bytes) else json.dumps(answer[1]).encode())


class Moment:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


class Mono:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Setup:
    def __init__(self, net: Net, **more: Any) -> None:
        self.clock, self.mono = Moment(), Mono()
        self.dials = [Frequency("40 m", "7.0541 MHz USB")]
        self.call = CALL
        self.service = Skeds("0.18.2", "linux", lambda: self.config(), lambda: self.dials, net.fetch, net.post, first_sec=0.05, expire_sec=0.02, environ=more.pop("environ", {}), clock=self.clock, monotonic=self.mono, **more)
        remember_stop(self.service.stop)
        self.told: list[list[str]] = []
        self.service.changed.connect(lambda: self.told.append([s.id for s in self.service.rows()]))

    def config(self) -> Config:
        return Config.from_data({"station/call": self.call})


def good(*rows: Any) -> tuple[int, bytes]:
    return 200, board(*rows)


async def test_the_board_is_read_a_minute_after_the_start_and_told_with_the_dials_and_the_rows() -> None:
    net = Net(good(GOOD))
    s = Setup(net)
    await s.service.start()
    await until(lambda: s.service.asked == 1 and s.told)
    assert net.read_calls == [(SKEDS_URL, "0.18.2", "linux", 131072)] and s.service.state == "ok" and [r.id for r in s.service.rows()] == ["7f3a9c21d4e0"] and s.service.fetched_at == NOW
    assert s.service.frequencies() == [Frequency("40 m", "7.0541 MHz USB")] and s.service.ours == frozenset()
    assert EVERY_SEC == 6 * 3600.0 and SKEDS_EVERY_SEC == 900.0


async def test_the_tab_asks_at_most_every_fifteen_minutes_however_many_pages_there_are() -> None:
    net = Net(good(GOOD))
    s = Setup(net)
    s.service.wanted()
    s.service.wanted()
    s.service.wanted()
    await until(lambda: len(s.told) >= 1)
    assert s.service.asked == 1 and len(net.read_calls) == 1, "three pages at once ask once"
    s.mono.now += SKEDS_EVERY_SEC - 1
    s.service.wanted()
    assert s.service.asked == 1
    s.mono.now += 2
    net.last_read = good(GOOD, row("aaaaaaaaaaaa", call="OH2ABC", start=1))
    s.service.wanted()
    await until(lambda: len(s.service.rows()) == 2)
    assert s.service.asked == 2


async def test_the_timer_of_the_first_minute_counts_as_a_reading_and_a_page_just_after_it_asks_nothing() -> None:
    net = Net(good(GOOD))
    s = Setup(net)
    await s.service.start()
    await until(lambda: s.service.asked == 1)
    s.service.wanted()
    assert s.service.asked == 1


async def test_nothing_is_read_or_posted_while_the_update_check_is_off_in_the_environment() -> None:
    net = Net(good(GOOD))
    s = Setup(net, environ={ENV_SWITCH: "0"})
    assert not s.service.enabled and s.service.state == "off"
    await s.service.start()
    s.service.wanted()
    await s.service.ask()
    with pytest.raises(SkedError) as refused:
        await s.service.post(NOW + timedelta(hours=1), NOW + timedelta(hours=2), "7.0541 MHz USB", "")
    assert refused.value.code == "sked.unreachable"
    await until(lambda: True)
    assert net.read_calls == [] and net.post_calls == [] and s.service.asked == 0 and s.service.rows() == [] and s.service.state == "off"


def test_the_address_is_the_projects_unless_a_server_on_this_computer_is_named() -> None:
    assert SKEDS_URL == "https://neo.oh2gba.eu/skeds.json"
    assert Setup(Net()).service.url == SKEDS_URL
    assert Setup(Net(), environ={ENV_URL: "http://127.0.0.1:8123/skeds.json"}).service.url == "http://127.0.0.1:8123/skeds.json"
    for bad in ("https://evil.example/skeds.json", "http://127.0.0.1.evil.example/skeds.json", "http://user@127.0.0.1/skeds.json", "ftp://127.0.0.1/skeds.json", "file:///etc/passwd", ""):
        assert Setup(Net(), environ={ENV_URL: bad}).service.url == SKEDS_URL, bad


async def test_a_board_that_is_not_there_or_not_a_board_leaves_the_last_board_and_says_offline_and_a_404_is_an_empty_board() -> None:
    net = Net(good(GOOD), None, (200, b"<html>"), (500, b""), (403, board(GOOD)), (404, b"not found"))
    s = Setup(net)
    states = []
    for _ in range(6):
        await s.service.ask()
        states.append((s.service.state, [r.id for r in s.service.rows()]))
        s.mono.now += SKEDS_EVERY_SEC + 1
    kept = (("ok", ["7f3a9c21d4e0"]), ("offline", ["7f3a9c21d4e0"]), ("offline", ["7f3a9c21d4e0"]), ("offline", ["7f3a9c21d4e0"]), ("offline", ["7f3a9c21d4e0"]))
    assert states[:5] == list(kept) and states[5] == ("ok", []), "a board nobody has posted to yet has no skeds, and the server is there"


async def test_a_read_that_did_not_reach_the_server_is_not_counted_and_the_tab_reads_again_a_minute_later() -> None:
    net = Net(None, good(GOOD))
    s = Setup(net)
    await s.service.ask()
    assert s.service.state == "offline"
    s.mono.now += RETRY_SEC - 1
    s.service.wanted()
    assert s.service.asked == 1, "not at once: a page that is opened again and again does not hammer a server that is away"
    s.mono.now += 2
    s.service.wanted()
    await until(lambda: s.service.state == "ok")
    assert s.service.asked == 2 and [r.id for r in s.service.rows()] == ["7f3a9c21d4e0"], "the network came back two minutes after the start: the tab need not wait 15 minutes"
    s.mono.now += RETRY_SEC + 1
    s.service.wanted()
    assert s.service.asked == 2, "a read that reached the server is counted as before"


async def test_a_post_that_did_not_reach_the_server_lets_the_tab_read_again_a_minute_later() -> None:
    net = Net(good(GOOD), good(GOOD))
    s = Setup(net)
    await s.service.ask()
    with pytest.raises(SkedError):
        await post_one(s)
    assert s.service.state == "offline"
    s.mono.now += RETRY_SEC + 1
    s.service.wanted()
    await until(lambda: s.service.state == "ok")
    assert s.service.asked == 2


async def test_a_board_that_is_away_for_a_moment_keeps_our_ids(tmp_path: Path) -> None:
    store = await store_at(tmp_path / "neoaprs.sqlite")
    ours = row("aaaaaaaaaaaa", call=CALL, start=5, end=7)
    net = Net((404, b"not found"), good(ours), posts=[added("aaaaaaaaaaaa")])
    s = Setup(net, memory=store)
    await post_one(s)
    s.mono.now += SKEDS_EVERY_SEC + 1
    await s.service.ask()
    assert s.service.rows() == [] and s.service.ours == frozenset({"aaaaaaaaaaaa"}) and json.loads(await store.setting(OURS_ROW) or "") == ["aaaaaaaaaaaa"], "a 404 (after a deploy, say) is no board to prune by"
    s.mono.now += SKEDS_EVERY_SEC + 1
    await s.service.ask()
    assert [r.id for r in s.service.rows()] == ["aaaaaaaaaaaa"] and s.service.ours == frozenset({"aaaaaaaaaaaa"}), "when the file is back, ours is still ours to delete"


async def test_offline_is_told_once_and_a_closed_board_is_closed_for_everyone() -> None:
    net = Net(None, None, good(), (200, board(closed=True)))
    s = Setup(net)
    for _ in range(4):
        await s.service.ask()
        s.mono.now += SKEDS_EVERY_SEC + 1
    assert s.told.count([]) == 3 and s.service.state == "closed", "offline once, then ok, then closed"


async def test_the_last_board_is_kept_and_told_at_the_next_start_before_the_server_is_asked(tmp_path: Path) -> None:
    store = await store_at(tmp_path / "neoaprs.sqlite")
    first = Setup(Net(good(GOOD)), memory=store)
    await first.service.ask()
    assert kept_board(await store.setting(SKEDS_ROW) or "", NOW) is not None and await store.setting(OURS_ROW) == "[]", "kept in the settings table, as rows that are no settings"
    net = Net(None)
    again = Setup(net, memory=store)
    again.service.first_sec = 3600.0
    await again.service.start()
    await until(lambda: again.told)
    assert [r.id for r in again.service.rows()] == ["7f3a9c21d4e0"] and again.service.fetched_at == NOW and net.read_calls == [] and again.service.state == "ok"
    await store.put_settings({SKEDS_ROW: "garbage", OURS_ROW: "garbage"})
    third = Setup(Net(None), memory=store)
    third.service.first_sec = 3600.0
    await third.service.start()
    await until(lambda: third.told)
    assert third.service.rows() == [] and third.service.ours == frozenset()


async def test_what_has_ended_is_dropped_by_the_daemons_own_clock_and_told() -> None:
    net = Net(good(row("aaaaaaaaaaaa", start=-1, end=1), row("bbbbbbbbbbbb", start=2, end=3)))
    s = Setup(net)
    await s.service.start()
    await until(lambda: s.told)
    assert [r.id for r in s.service.rows()] == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]
    s.clock.now = NOW + timedelta(hours=1, minutes=1)
    await until(lambda: s.told[-1] == ["bbbbbbbbbbbb"])
    s.clock.now = NOW + timedelta(hours=4)
    await until(lambda: s.told[-1] == [])


async def test_the_dials_follow_the_radio_and_tell_nothing_by_themselves() -> None:
    s = Setup(Net())
    assert s.service.frequencies() == [Frequency("40 m", "7.0541 MHz USB")]
    s.dials = [Frequency("20 m", "14.1070 MHz USB")]
    assert s.service.frequencies() == [Frequency("20 m", "14.1070 MHz USB")]


START, END = NOW + timedelta(hours=5), NOW + timedelta(hours=7)


async def post_one(s: Setup, note: str = "Mercury, 10 W") -> None:
    await s.service.post(START, END, "7.0541 MHz USB", note)


def added(ident: str = "aaaaaaaaaaaa", **more: Any) -> tuple[int, Any]:
    rows = [{**row(ident, call=CALL, start=5, end=7), **more}]
    return 200, {"ok": True, "id": ident, "board": json.loads(board(*rows))}


async def test_a_post_sends_the_call_the_times_the_dial_the_note_and_the_token_and_takes_the_board_from_the_answer() -> None:
    net = Net(posts=[added()])
    s = Setup(net)
    await post_one(s)
    (url, body, version, platform), = net.post_calls
    assert url == "https://neo.oh2gba.eu/api/v1/skeds.php" and (version, platform) == ("0.18.2", "linux")
    assert set(body) == {"action", "token", "call", "from", "to", "dial", "note"} and body["action"] == "add" and TOKEN.fullmatch(body["token"])
    assert (body["call"], body["from"], body["to"], body["dial"], body["note"]) == (CALL, iso(START), iso(END), "7.0541 MHz USB", "Mercury, 10 W")
    assert [r.id for r in s.service.rows()] == ["aaaaaaaaaaaa"] and s.service.ours == frozenset({"aaaaaaaaaaaa"}) and net.read_calls == [] and s.service.state == "ok"
    assert s.told[-1] == ["aaaaaaaaaaaa"]


async def test_the_token_is_made_when_it_is_first_needed_kept_and_the_same_after_a_restart(tmp_path: Path) -> None:
    store = await store_at(tmp_path / "neoaprs.sqlite")
    net = Net(posts=[added("aaaaaaaaaaaa"), added("bbbbbbbbbbbb")])
    s = Setup(net, memory=store)
    await s.service.ask()
    assert await store.setting(SKED_TOKEN) is None, "made when it is needed, not before: reading needs none"
    await post_one(s)
    token = await store.setting(SKED_TOKEN)
    assert token is not None and TOKEN.fullmatch(token) and net.post_calls[0][1]["token"] == token
    again = Setup(net, memory=store)
    await post_one(again)
    assert net.post_calls[1][1]["token"] == token and await store.setting(SKED_TOKEN) == token
    for bad in ("", "short", "G" * 32, token.upper(), token + "0"):
        await store.put_settings({SKED_TOKEN: bad})
        net.posts.append(added("cccccccccccc"))
        await post_one(Setup(net, memory=store))
        made = await store.setting(SKED_TOKEN)
        assert made is not None and made != bad and TOKEN.fullmatch(made), "a row that is not a token is made again"


async def test_the_token_is_not_the_installations_number_and_is_never_sent_when_reading_or_written_to_the_log(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    store = await store_at(tmp_path / "neoaprs.sqlite")
    number = "0123456789abcdef0123456789abcdef"
    await store.put_settings({"update/install_id": number})
    net = Net(good(GOOD), posts=[added(), (403, {"ok": False, "reason": "bad_request"}), None])
    s = Setup(net, memory=store)
    with caplog.at_level(logging.DEBUG):
        await s.service.ask()
        await post_one(s)
        for _ in range(2):
            with pytest.raises(SkedError):
                await post_one(s)
    token = await store.setting(SKED_TOKEN)
    assert token is not None and token != number and number not in json.dumps(net.post_calls)
    assert all(token not in json.dumps(call) for call in net.read_calls), "reading sends nothing about the installation"
    assert all(token not in record.getMessage() and number not in record.getMessage() for record in caplog.records), "no line of the log has it"


async def test_a_post_is_refused_before_the_network_when_it_cannot_be_right_and_a_sked_that_has_ended_is_an_error_with_a_code() -> None:
    net = Net()
    s = Setup(net)
    with pytest.raises(SkedError) as ended:
        await s.service.post(NOW - timedelta(hours=3), NOW - timedelta(hours=1), "7.0541 MHz USB", "")
    assert ended.value.code == "sked.past"
    for start, end in ((START, START), (END, START), (START, START + timedelta(hours=24, seconds=1))):
        with pytest.raises(ValueError, match="cannot be posted"):
            await s.service.post(start, end, "7.0541 MHz USB", "")
    with pytest.raises(SkedError) as far:
        await s.service.post(NOW + timedelta(days=30, minutes=30), NOW + timedelta(days=30, hours=1), "7.0541 MHz USB", "")
    assert far.value.code == "sked.far", "the page's clock may be ahead of the daemon's, and a row of the board may begin up to 31 days ahead: Join on it is told why"
    s.call = ""
    with pytest.raises(ValueError, match="no call"):
        await post_one(s)
    s.call = "N0CALL"
    with pytest.raises(ValueError, match="no call"):
        await post_one(s)
    assert net.post_calls == [] and net.read_calls == []


async def test_the_refusals_the_operator_can_do_something_about_are_errors_with_codes() -> None:
    for reason, status, code in (("rate", 429, "sked.rate"), ("full", 409, "sked.full"), ("past", 422, "sked.past"), ("too_far", 422, "sked.far")):
        net = Net(posts=[(status, {"ok": False, "reason": reason})])
        s = Setup(net)
        with pytest.raises(SkedError) as refused:
            await post_one(s)
        assert refused.value.code == code and s.service.ours == frozenset() and s.service.state == "ok", reason


async def test_the_others_are_the_logs_a_server_that_is_away_or_says_something_odd_is_one_error_and_the_board_closed_for_a_call_is_no_error(caplog: pytest.LogCaptureFixture) -> None:
    odd = [(400, {"ok": False, "reason": "bad_request"}), (422, {"ok": False, "reason": "too_long"}), (500, {"ok": False, "reason": "storage"}), (413, {"ok": False, "reason": "too_large"}),
           (500, b"<html>"), (200, b"[]"), (200, {"ok": False}), (200, {"ok": "yes"}), (403, {"ok": False, "reason": ["x"]}), (403, {"ok": False, "reason": "not_yours"}), (302, b"")]
    net = Net(posts=[*odd, None])
    s = Setup(net)
    with caplog.at_level(logging.INFO):
        for _ in range(len(odd) + 1):
            with pytest.raises(SkedError) as refused:
                await post_one(s)
            assert refused.value.code == "sked.unreachable", refused.value
    assert s.service.ours == frozenset() and s.service.state == "offline", "the last try did not reach the server"
    assert any("refused the add" in r.getMessage() for r in caplog.records), "the log has it"


async def test_a_board_closed_to_our_call_is_closed_for_that_call_only_until_the_next_read_and_nothing_is_said_to_the_operator() -> None:
    net = Net(good(GOOD), good(GOOD), posts=[(403, {"ok": False, "reason": "closed"}), added("aaaaaaaaaaaa")])
    s = Setup(net)
    await s.service.ask()
    await post_one(s)
    assert len(net.read_calls) == 2, "the refusal is told apart by the board read at once"
    assert s.service.state == "closed" and s.told[-1] == ["7f3a9c21d4e0"] and s.service.ours == frozenset(), "no error, no sked: the board is open but closed to this call"
    s.service.wanted()
    assert s.service.asked == 1, "the board read at once counts as a read"
    s.call = "OH2ABC"
    assert s.service.state == "ok", "another call is not blocked"
    s.call = "OH2GBA-7"
    assert s.service.state == "closed", "the SSID makes no other call"
    s.call = CALL
    s.mono.now += SKEDS_EVERY_SEC + 1
    await s.service.ask()
    assert s.service.state == "ok", "the moderator may have let the call in since: the next read opens the form again"
    await post_one(s)
    assert s.service.state == "ok" and s.service.ours == frozenset({"aaaaaaaaaaaa"})


async def test_a_closed_answer_read_against_a_board_the_moderator_closed_meanwhile_is_closed_by_the_board_and_opens_with_it() -> None:
    net = Net(good(GOOD), (200, board(GOOD, closed=True)), good(GOOD), posts=[(403, {"ok": False, "reason": "closed"})])
    s = Setup(net)
    await s.service.ask()
    assert s.service.state == "ok"
    await post_one(s)
    assert s.service.state == "closed" and s.service._shut == "", "closed for everyone, by the board: our call is not taken for a blocked one"
    s.mono.now += SKEDS_EVERY_SEC + 1
    await s.service.ask()
    assert s.service.state == "ok", "the moderator opened the board again, and the next read shows the form"


async def test_an_answer_without_a_usable_board_is_read_again_and_a_hostile_board_in_an_answer_is_held_to_the_same_rules() -> None:
    net = Net(good(row("aaaaaaaaaaaa", call=CALL, start=5, end=7)), posts=[(200, {"ok": True, "id": "aaaaaaaaaaaa"})])
    s = Setup(net)
    await post_one(s)
    assert len(net.read_calls) == 1 and s.service.ours == frozenset({"aaaaaaaaaaaa"}) and [r.id for r in s.service.rows()] == ["aaaaaaaaaaaa"]
    hostile = json.loads(board(GOOD, hostile_rows()["call markup"], hostile_rows()["note bidi override"], {**GOOD, "id": "bbbbbbbbbbbb", "call": "OH2ABC"}))
    net2 = Net(posts=[(200, {"ok": True, "id": "7f3a9c21d4e0", "board": hostile})])
    s2 = Setup(net2)
    await post_one(s2)
    assert [r.id for r in s2.service.rows()] == ["7f3a9c21d4e0", "bbbbbbbbbbbb"]


async def test_a_delete_takes_the_sked_off_and_what_is_not_ours_is_dropped_quietly_and_the_board_read_again() -> None:
    net = Net(posts=[added("aaaaaaaaaaaa"), (200, {"ok": True, "board": json.loads(board())}), (403, {"ok": False, "reason": "not_yours"}), (429, {"ok": False, "reason": "rate"}), None])
    s = Setup(net)
    await post_one(s)
    assert s.service.ours == frozenset({"aaaaaaaaaaaa"})
    await s.service.delete("aaaaaaaaaaaa")
    assert s.service.ours == frozenset() and s.service.rows() == [] and net.post_calls[1][1]["action"] == "remove" and net.post_calls[1][1]["id"] == "aaaaaaaaaaaa" and TOKEN.fullmatch(net.post_calls[1][1]["token"])
    net.last_read = good(GOOD)
    await s.service.delete("7f3a9c21d4e0")
    assert [r.id for r in s.service.rows()] == ["7f3a9c21d4e0"] and len(net.read_calls) == 1, "not ours: the board is read again, nothing is said"
    with pytest.raises(SkedError) as limited:
        await s.service.delete("7f3a9c21d4e0")
    assert limited.value.code == "sked.rate"
    with pytest.raises(SkedError) as away:
        await s.service.delete("7f3a9c21d4e0")
    assert away.value.code == "sked.unreachable"


async def test_our_ids_are_kept_and_the_ones_that_are_not_on_the_board_any_more_are_dropped(tmp_path: Path) -> None:
    store = await store_at(tmp_path / "neoaprs.sqlite")
    net = Net(posts=[added("aaaaaaaaaaaa"), added("bbbbbbbbbbbb", note="again")])
    s = Setup(net, memory=store)
    await post_one(s)
    assert json.loads(await store.setting(OURS_ROW) or "") == ["aaaaaaaaaaaa"]
    again = Setup(Net(good(row("aaaaaaaaaaaa", call=CALL, start=5, end=7))), memory=store)
    again.service.first_sec = 3600.0
    await again.service.start()
    await until(lambda: again.service.ours == frozenset({"aaaaaaaaaaaa"}))
    assert [r.id for r in again.service.rows()] == ["aaaaaaaaaaaa"], "kept, and told at the start"
    again.mono.now += SKEDS_EVERY_SEC + 1
    again.service._fetch = Net(good()).fetch
    await again.service.ask()
    assert again.service.ours == frozenset() and json.loads(await store.setting(OURS_ROW) or "") == [], "the sked ended or was removed by the moderator: it is not ours to delete any more"


# ---- the secrets stay out of the log and the bundle -------------------------------------------------------------------------------------------------

def test_the_token_is_a_secret_by_its_name_for_the_log_the_bundle_and_the_listing() -> None:
    token = "ab" * 16                                # (made up: the form of a token, 32 hex characters)
    assert SKED_TOKEN == "update/sked_token" and hides(SKED_TOKEN, token) and shown_value(SKED_TOKEN, token) == "(set, 32 characters)"
    rows = {SKED_TOKEN: token, "station/call": "OH2GBA"}
    assert token not in settings_json(rows) and "(set, 32 characters)" in settings_json(rows) and secrets_of(rows) == [token], "the support bundle: out of the settings and out of every file"


def test_neoaprs_db_list_does_not_print_the_token(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from neoaprs.cli.dbcmd import main
    import sqlite3
    from neoaprs.store import DB_NAME
    assert main(["--data", str(tmp_path), "set", "station/call", "oh2gba"]) == 0
    connection = sqlite3.connect(tmp_path / DB_NAME)
    connection.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (SKED_TOKEN, "ab" * 16))
    connection.commit()
    connection.close()
    capsys.readouterr()
    assert main(["--data", str(tmp_path), "list"]) == 0
    out = capsys.readouterr().out
    assert "0123456789abcdef0123456789abcdef" not in out and any(line.startswith(SKED_TOKEN) and "(set, 32 characters)" in line and line.endswith("not a setting") for line in out.splitlines())


# ---- the real calls against a server on this computer -----------------------------------------------------------------------------------------------

async def test_the_real_calls_read_a_404_as_no_board_post_json_with_the_token_and_read_nothing_about_the_station(tmp_path: Path) -> None:
    server = await skeds_server()
    store = await store_at(tmp_path / "neoaprs.sqlite")
    clock = Moment()
    clock.now = datetime.now(tz=UTC)
    made = Skeds("0.18.2", "linux", lambda: Config.from_data({"station/call": CALL}), lambda: [], fetch_answer, post_board, environ={ENV_URL: server.url}, memory=store, clock=clock)
    remember_stop(made.stop)
    await made.ask()
    assert made.state == "ok" and made.rows() == [] and server.gets[0][0].startswith("GET /skeds.json HTTP/1.1") and made.fetched_at is not None, "no board yet is no skeds, and the server is there"
    start = clock.now + timedelta(hours=2)
    await made.post(start, start + timedelta(hours=2), "7.0541 MHz USB", "Mercury, 10 W")
    (posted,) = server.posts
    assert posted["action"] == "add" and posted["call"] == CALL and posted["note"] == "Mercury, 10 W" and TOKEN.fullmatch(posted["token"])
    assert [(r.call, r.dial, r.note) for r in made.rows()] == [(CALL, "7.0541 MHz USB", "Mercury, 10 W")] and made.ours == frozenset(r.id for r in made.rows())
    assert MAX_BYTES == 131072
    token = await store.setting(SKED_TOKEN)
    assert token == posted["token"] and all(token not in line and token not in json.dumps(headers) for line, headers in server.gets), "the token goes with a post and nowhere else"
    assert all(set(headers) <= {"host", "user-agent", "accept-encoding", "connection"} for _, headers in server.gets) and "NeoAPRS/0.18.2" in server.gets[0][1]["user-agent"], "a read carries the version and the kind of system only"
    other = Skeds("0.18.2", "linux", lambda: Config.from_data({"station/call": CALL}), lambda: [], fetch_answer, post_board, environ={ENV_URL: server.url}, clock=clock)
    remember_stop(other.stop)
    await other.ask()
    (ident,) = made.ours
    await other.delete(ident)
    assert [r.id for r in other.rows()] == [ident], "another installation's token cannot delete it: the server says not_yours, nothing is said, and the board is read again"
    await made.delete(ident)
    assert made.rows() == [] and made.ours == frozenset() and server.rows == []


async def test_the_answer_to_a_post_is_read_to_the_boards_own_limit_however_long_the_notes_of_the_others_are() -> None:
    server = await skeds_server()
    clock = Moment()
    clock.now = datetime.now(tz=UTC).replace(microsecond=0)
    server.rows = [{"id": f"{0xfff000 + n:012x}", "call": f"OH{n % 10}A{n:02d}", "from": iso(clock.now + timedelta(hours=1 + n)) or "", "to": iso(clock.now + timedelta(hours=2 + n)) or "", "dial": "7.0541 MHz USB", "note": "é" * 80}
                   for n in range(40)]
    made = Skeds("0.18.2", "linux", lambda: Config.from_data({"station/call": CALL}), lambda: [], fetch_answer, post_board, environ={ENV_URL: server.url}, clock=clock)
    remember_stop(made.stop)
    start = clock.now + timedelta(hours=2)
    await made.post(start, start + timedelta(hours=2), "7.0541 MHz USB", "Mercury, 10 W")
    assert len(json.dumps({"board": server.board()})) > 8192 * 2, "far more than a few lines"
    assert len(made.ours) == 1 and len(made.rows()) == 41 and made.state == "ok", "the post the server took is ours, and can be deleted"
    await made.delete(next(iter(made.ours)))
    assert made.ours == frozenset() and len(server.rows) == 40


async def test_a_server_that_says_something_else_for_the_board_is_offline_and_a_server_that_is_not_there_too() -> None:
    server = await skeds_server()
    server.rows = [GOOD]
    clock = Moment()
    made = Skeds("0.18.2", "linux", lambda: Config.from_data({"station/call": CALL}), lambda: [], fetch_answer, post_board, environ={ENV_URL: server.url}, clock=clock, monotonic=Mono())
    remember_stop(made.stop)
    server.raw = b'{"v": 1, "skeds": "not a list"}'
    await made.ask()
    assert made.state == "offline" and made.rows() == []
    await server.stop()
    made._last = None
    await made.ask()
    assert made.state == "offline"


def test_the_environment_of_the_tests_switches_the_service_off() -> None:
    assert Skeds("0.18.2", "linux", lambda: Config.from_data({"station/call": CALL}), lambda: []).enabled is False


def test_every_error_code_the_service_has_is_a_code_of_the_pattern() -> None:
    assert re.fullmatch(r"sked\.[a-z_]+", SkedError("x", "sked.rate").code)


@pytest.fixture
def under_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The no-devices switch is on in this test's own process too (tests/conftest.py lifts it for every test that does not ask for a fixture of this name)."""
    monkeypatch.setenv(nodevices.ENV, "1")
    monkeypatch.setattr(nodevices, "_told", set())


async def test_under_the_no_devices_switch_nothing_is_read_from_or_posted_to_a_server_that_is_not_this_computer(under_the_switch: None) -> None:
    assert updatefetch.get_answer(SKEDS_URL, "0.18.2", "linux") is None
    assert updatefetch.post_json(endpoint_url(SKEDS_URL), request_body("remove", "a" * 32, {"id": "aaaaaaaaaaaa"}), "0.18.2", "linux") is None
    assert updatefetch.post_json("ftp://127.0.0.1/skeds.php", b"{}", "0.18.2", "linux") is None and updatefetch.get_answer("file:///etc/passwd", "0.18.2", "linux") is None
