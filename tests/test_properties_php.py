"""Properties of the project server's endpoints (server/) under PHP's web server on the loopback, with every
error logged to a file of the test and the mail and the status library stood in for:
no request, however malformed, is answered with a PHP error, an undocumented status or a body the client cannot read;
a refused request stores nothing, and what is stored reads back as it was sent;
a chat line, a sked and a support note NeoAPRS sends are taken, in the form NeoAPRS made of them;
the server cleans a chat text as NeoAPRS does, and a call NeoAPRS accepts is accepted in the same form;
the update check's query is logged as sent, and the answer is one the daemon reads.
"""

import asyncio
import http.client
import io
import json
import os
import re
import shutil
import socket
import subprocess
import time
import unicodedata
import urllib.parse
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
import tornado.web
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from neoaprs.chat import clean_text
from neoaprs.chat import request_body as chat_body
from neoaprs.config import Config
from neoaprs.satellitelist import read_file
from neoaprs.services import chat as chatservice
from neoaprs.services import skeds as skedservice
from neoaprs.skeds import clean_note, our_call, when
from neoaprs.skeds import request_body as sked_body
from neoaprs.updatefetch import multipart, post_board, request_url
from neoaprs.versions import parse_update
from neoaprs.web.skedwire import SkedPost
from neoaprs.web.supportsend import SupportSend, reply_address, send_bundle
from tests.support.phpserver import PHP, free_port
from tests.support.ptyline import posix_only

pytestmark = posix_only

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "0123456789abcdef0123456789abcdef"
# what PHP writes into a page for an error it shows
PHP_TEXT = re.compile(rb"(Fatal error|Parse error|Warning|Notice|Deprecated): .* on line \d+|Stack trace:")
CHAT_REASONS = {
    200: set(),
    400: {"bad_request"},
    403: {"closed"},
    405: {"method"},
    413: {"too_large"},
    415: {"bad_request"},
    429: {"rate"},
}
SKED_REASONS = {
    **CHAT_REASONS,
    403: {"closed", "not_yours"},
    409: {"full"},
    422: {"past", "too_long", "too_far"},
}
SUPPORT_REASONS = {200: set(), 400: {"bad_request", "not_a_bundle"}, 405: {"method"}, 413: {"too_large"}, 429: {"rate"}}
METHODS = ["POST", "GET", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS"]
KINDS = [
    "application/json",
    "application/json; charset=utf-8",
    "Application/JSON ; x=y",
    "text/plain",
    "",
    "multipart/form-data",
    "application/x-www-form-urlencoded",
]
PREPEND = """<?php
function support_send_mail(string $subject, string $body): bool
{
    $line = json_encode([$subject, $body], JSON_INVALID_UTF8_SUBSTITUTE) . "\\n";
    file_put_contents(getenv('MAIL_OUT'), $line, FILE_APPEND);
    return true;
}
"""
LIBRARY = """<?php
if (!function_exists('status_db')) {
    function status_db(): string { return 'db'; }
    function neo_test_record(array $what): void
    {
        file_put_contents(getenv('RECORDS'), json_encode($what, JSON_INVALID_UTF8_SUBSTITUTE) . "\\n", FILE_APPEND);
    }
}
"""
VISITORS = """
function visitor_record(mixed $db, string $site, array $in, string $ip, string $ua): void
{
    neo_test_record(['view', $in]);
}
function visitor_dwell(mixed $db, string $site, array $in, string $ip, string $ua): void
{
    neo_test_record(['dwell', $in]);
}
"""
STARTS = """
function app_start_record(mixed $db, string $app, string $version, string $os, string $id): void
{
    neo_test_record([$app, $version, $os, $id]);
}
"""


@dataclass(frozen=True)
class Answer:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> dict[str, Any]:
        data = json.loads(self.body)
        assert isinstance(data, dict), self.body
        return data


class Site:
    """The server's files laid out as on the host, under one `php -S` that logs every error to a file."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.site = folder / "site"
        self.support = folder / "support"
        self.errors = folder / "php-errors.log"
        self.mails = folder / "mails.jsonl"
        self.records = folder / "records.jsonl"
        self.process: subprocess.Popen[bytes] | None = None
        self.port = free_port()
        server = ROOT / "server"
        (self.site / "api" / "v1").mkdir(parents=True)
        (self.site / "private").mkdir()
        (self.site / "support").mkdir()
        (self.site / "log").mkdir()
        for name in ("chat.php", "skeds.php", "satellites.php", "view.php"):
            shutil.copy(server / "neo" / "api" / "v1" / name, self.site / "api" / "v1" / name)
        for name in ("endpoint.php", "satellites-list.json"):
            shutil.copy(server / "neo" / "private" / name, self.site / "private" / name)
        shutil.copy(server / "neo" / "support" / "send.php", self.site / "support" / "send.php")
        for name in ("version.php", "latest.php"):
            shutil.copy(server / name, self.site / name)
        (folder / "prepend.php").write_text(PREPEND, encoding="utf-8")
        library = folder / "library"
        library.mkdir()
        (library / "visitors.php").write_text(LIBRARY + VISITORS, encoding="utf-8")
        (library / "starts.php").write_text(LIBRARY + STARTS, encoding="utf-8")
        closed = f"http://127.0.0.1:{free_port()}/"  # nothing listens: no download ever leaves the machine
        self.environment = {
            "PATH": os.environ["PATH"],
            "HOME": str(folder),
            "SUPPORT_DIR": str(self.support),
            "MAIL_OUT": str(self.mails),
            "RECORDS": str(self.records),
            "STATUS_LIB": str(library),
            "RELEASES_URL": closed,
            "CELESTRAK_URL": closed,
        }

    def start(self) -> None:
        assert PHP is not None
        ini = {
            "display_errors": "1",
            "html_errors": "0",
            "log_errors": "1",
            "error_reporting": "-1",
            "error_log": str(self.errors),
            "auto_prepend_file": str(self.folder / "prepend.php"),
            "upload_tmp_dir": str(self.folder),
            "upload_max_filesize": "22M",
            "post_max_size": "24M",
        }
        flags = [part for key, value in ini.items() for part in ("-d", f"{key}={value}")]
        for _ in range(3):
            self.process = subprocess.Popen(
                [PHP, "-S", f"127.0.0.1:{self.port}", "-t", str(self.site), *flags],
                env=self.environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and self.process.poll() is None:
                try:
                    socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                    return
                except OSError:
                    time.sleep(0.05)
            if self.process.poll() is None:
                break
            self.port = free_port()
        raise AssertionError("php did not start")

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process.wait(10)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def fresh(self) -> None:
        """What an earlier example stored and counted is gone; the latest release is known."""
        for path in (self.site / "chat.json", self.site / "skeds.json", self.site / "skeds-past.json"):
            path.unlink(missing_ok=True)
        for folder in (self.site / "private" / "chat", self.site / "private" / "skeds", self.support):
            shutil.rmtree(folder, ignore_errors=True)
        for path in (self.mails, self.records):
            path.unlink(missing_ok=True)
        for path in (self.site / "log").glob("starts-*.log"):
            path.unlink()
        (self.site / "log" / "latest.json").write_text('{"version": "0.26.1"}', encoding="utf-8")

    def send(self, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> Answer:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return Answer(response.status, {k.lower(): v for k, v in response.getheaders()}, response.read())
        finally:
            connection.close()

    def post_json(self, path: str, body: object) -> Answer:
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        return self.send("POST", path, data, {"Content-Type": "application/json"})

    def logged(self) -> str:
        """PHP's error log and the endpoints' own logs of an exception; emptied for the next request."""
        found = self.errors.read_text(encoding="utf-8", errors="replace") if self.errors.exists() else ""
        # PHP's own reading of a form, before any line of an endpoint runs: nothing the endpoint can change
        found = "".join(line for line in found.splitlines(True) if "PHP Request Startup:" not in line)
        self.errors.unlink(missing_ok=True)
        for log in [*(self.site / "private" / "logs").glob("*.log"), self.folder / "logs" / "support.log"]:
            if log.exists():
                found += "".join(line for line in log.read_text(encoding="utf-8").splitlines(True) if "error:" in line)
                log.unlink()
        return found

    def kept(self, *places: Path) -> dict[str, bytes]:
        """The data files under `places`, without the brake's counts, the salt, the locks and the marks."""
        bookkeeping = {"rate.json", "refresh.json", "salt", "lock", "store.lock", "cleaned", ".htaccess", "failed"}
        found: dict[str, bytes] = {}
        for place in places:
            for path in [place] if place.is_file() else sorted(place.rglob("*")) if place.is_dir() else []:
                if path.is_file() and path.name not in bookkeeping:
                    found[str(path)] = path.read_bytes()
        return found


def clean_answer(site: Site, answer: Answer, statuses: dict[int, set[str]] | None, method: str = "POST") -> None:
    """The answer is no PHP error: a documented status, no error text, nothing logged; JSON of the protocol."""
    assert not PHP_TEXT.search(answer.body), answer.body[:300]
    assert site.logged() == ""
    if statuses is None:
        return
    assert answer.status in statuses, (answer.status, answer.body[:300])
    assert answer.headers.get("content-type") == "application/json; charset=utf-8"
    if method == "HEAD":
        assert answer.body == b""
        return
    data = answer.json()
    if answer.status == 200:
        assert data["ok"] is True
    else:
        assert data == {"ok": False, "reason": data.get("reason")} and data["reason"] in statuses[answer.status]


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Site]:
    if PHP is None:
        pytest.skip("needs php")
    served = Site(tmp_path_factory.mktemp("php-properties"))
    served.start()
    yield served
    served.stop()


# ---- what is drawn

_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**70), max_value=2**70),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=20),
)
_JSON = st.recursive(
    _SCALARS,
    lambda inner: st.lists(inner, max_size=3) | st.dictionaries(st.text(max_size=6), inner, max_size=3),
    max_leaves=8,
)
_ODD_TEXT = st.one_of(
    st.sampled_from(["", " ", "\x00", "\t\n\r", "​⁠﻿", "\x7f\x85\x9f", "\U0010ffff", ""]),
    st.builds(lambda c, n: c * n, st.sampled_from(["A", "é", "😀", '"', "\\", " "]), st.integers(150, 3000)),
    st.text(alphabet=st.characters(max_codepoint=0x40), max_size=10),
    st.text(max_size=60),
)


def mostly(good: st.SearchStrategy[Any], other: st.SearchStrategy[Any]) -> st.SearchStrategy[Any]:
    """`good` about half the time, else `other` (one_of would weigh each of other's own branches as one)."""
    return st.booleans().flatmap(lambda pick: good if pick else other)


_GOOD_CALL = st.from_regex(r"\A[A-Z]{1,2}[0-9][A-Z]{1,3}(-([0-9]|1[0-5]))?\Z")
_GOOD_DIAL = st.from_regex(r"\A[0-9]{1,2}\.[0-9]{3,4} MHz (USB|LSB)\Z")
_CALLS = st.one_of(
    _GOOD_CALL,
    st.sampled_from(["OH2GBA", "oh2gba-0", " OH2GBA-15 ", "OH2GBA-16", "N0CALL", "MYCALL-1", "OH2GBA/P", "SM0", "AB1"]),
    st.from_regex(r"\A\s?[A-Za-z0-9]{2,7}(-[0-9]{1,2})?\s?\Z"),
    _ODD_TEXT,
)
_DIALS = st.one_of(
    st.just("7.0541 MHz USB"),
    _GOOD_DIAL,
    st.from_regex(r"\A[0-9]{1,3}\.[0-9]{2,5} ?(MHz|mhz|kHz) ?(USB|LSB|FM|usb)\Z"),
    st.sampled_from(["٧.٠٥٤١ MHz USB", "7.0541 MHz USB\n", " 7.0541 MHz USB", "7.0541 MHz USB"]),
    _ODD_TEXT,
)


@st.composite
def mutated(draw: st.DrawFn, base: dict[str, Any]) -> dict[str, Any]:
    """The request with a few of its fields dropped, replaced by any JSON or an odd text, or added."""
    body = dict(base)
    for _ in range(draw(st.integers(0, 3))):
        keys = sorted(body)
        op = draw(st.sampled_from(["drop", "json", "text", "add"]))
        if op == "add" or not keys:
            body[draw(st.text(max_size=8))] = draw(_JSON)
            continue
        key = draw(st.sampled_from(keys))
        if op == "drop":
            del body[key]
        else:
            body[key] = draw(_JSON if op == "json" else _ODD_TEXT)
    return body


@st.composite
def encoded(draw: st.DrawFn, body: dict[str, Any]) -> bytes:
    """The JSON of the body, now and then broken: bytes that are no UTF-8, cut short, nested deep."""
    data = json.dumps(body, ensure_ascii=draw(st.booleans())).encode()
    op = draw(st.sampled_from(["as is"] * 6 + ["bytes", "cut", "nest", "list", "raw"]))
    if op == "bytes":
        at = draw(st.integers(0, len(data)))
        return data[:at] + draw(st.sampled_from([b"\xff", b"\xc3", b"\xed\xa0\x80", b"\x00", b'\\ud800"'])) + data[at:]
    if op == "cut":
        return data[: draw(st.integers(0, max(0, len(data) - 1)))]
    if op == "nest":
        depth = draw(st.integers(1, 600))
        return b'{"action": ' + b"[" * depth + b"1" + b"]" * depth + b"}"
    if op == "list":
        return b"[" + data + b"]"
    return draw(st.binary(max_size=200))


@st.composite
def requests(draw: st.DrawFn, base: dict[str, Any]) -> tuple[str, str, bytes]:
    method = draw(st.sampled_from(["POST"] * 8 + METHODS))
    kind = draw(st.sampled_from(KINDS[:1] * 6 + KINDS))
    return method, kind, draw(encoded(draw(mutated(base))))


def future(seconds: float) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def sked_fields(start: float = 3600, length: float = 7200) -> dict[str, str]:
    return {
        "call": "OH2GBA",
        "from": future(start),
        "to": future(start + length),
        "dial": "7.0541 MHz USB",
        "note": "Mercury, 10 W",
    }


def station(call: str) -> str:
    """The call as the settings give it to the daemon."""
    return Config.from_data({"station/call": call}).station_call


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


# ---- the chat


@settings(max_examples=150)
@given(st.data())
def test_no_request_to_the_chat_is_answered_with_a_php_error_and_a_refused_one_stores_nothing(
    site: Site, data: st.DataObject
) -> None:
    """Mutations of the say and the refresh NeoAPRS posts, with any method and type, get a documented answer."""
    site.fresh()
    base = (
        json.loads(chat_body(TOKEN, "OH2GBA", "QRV on 7.0541")) if data.draw(st.booleans()) else {"action": "refresh"}
    )
    method, kind, body = data.draw(requests(base))
    before = site.kept(site.site / "chat.json", site.site / "private" / "chat")
    answer = site.send(method, "/api/v1/chat.php", body, {"Content-Type": kind} if kind else {})
    event(f"status {answer.status}")
    clean_answer(site, answer, CHAT_REASONS, method)
    if answer.status != 200:
        assert site.kept(site.site / "chat.json", site.site / "private" / "chat") == before
    elif "chat" in answer.json():
        assert answer.json()["chat"] == json.loads((site.site / "chat.json").read_bytes())


@settings(max_examples=150)
@given(st.text(max_size=260), mostly(_GOOD_CALL, _CALLS))
def test_a_line_neoaprs_says_is_kept_as_neoaprs_cleaned_it_under_the_call_neoaprs_made(
    site: Site, text: str, call: str
) -> None:
    """The daemon's say goes out only for a line and a call it accepts; the server then takes both as they are."""
    site.fresh()
    sent: list[tuple[int, bytes]] = []

    async def post(url: str, body: bytes, version: str, platform: str, max_bytes: int) -> tuple[int, bytes] | None:
        got = await post_board(url, body, version, platform, max_bytes)
        assert got is not None
        sent.append(got)
        return got

    async def nothing(*_: object) -> None:
        return None

    async def token() -> str:
        return TOKEN

    service = chatservice.ChatRoom(
        "0.26.1",
        "linux",
        lambda: Config.from_data({"station/call": call}),
        token,
        nothing,
        post,
        environ={chatservice.ENV_URL: f"{site.base}/chat.json"},
    )
    try:
        run(service.say(text))
    except ValueError:
        event("refused by the daemon")
        assert not sent and not (our_call(station(call)) and clean_text(text)), "refused by the daemon alone"
        return
    [(status, body)] = sent
    clean_answer(site, Answer(status, {"content-type": "application/json; charset=utf-8"}, body), CHAT_REASONS)
    assert status == 200, body
    said = json.loads(body)["chat"]["lines"][-1]
    assert (said["call"], said["text"]) == (our_call(station(call)), clean_text(text))
    assert [(line.call, line.text) for line in service.lines()][-1:] == [(said["call"], said["text"])]


def _known(c: str) -> bool:
    # a character this Python's Unicode has not assigned may be one that PHP's newer Unicode has
    return unicodedata.category(c) != "Cn"


@settings(max_examples=200)
@given(st.text(alphabet=st.characters(codec="utf-8").filter(_known), max_size=240))
def test_the_server_cleans_a_chat_text_as_neoaprs_does(site: Site, text: str) -> None:
    """The text the server keeps of any text is clean_text's; an empty one is refused."""
    site.fresh()
    answer = site.post_json("/api/v1/chat.php", {"action": "say", "token": TOKEN, "call": "OH2GBA", "text": text})
    clean_answer(site, answer, CHAT_REASONS)
    if clean_text(text):
        assert answer.status == 200 and answer.json()["chat"]["lines"][-1]["text"] == clean_text(text)
    else:
        assert answer.status == 400


@settings(max_examples=200)
@given(_CALLS)
def test_a_call_neoaprs_accepts_the_server_accepts_in_the_same_form(site: Site, call: str) -> None:
    """What our_call makes of a text the server takes as it is; what the server refuses our_call refuses."""
    site.fresh()
    answer = site.post_json("/api/v1/chat.php", {"action": "say", "token": TOKEN, "call": call, "text": "hi"})
    event(f"status {answer.status}")
    clean_answer(site, answer, CHAT_REASONS)
    if our_call(call):
        assert answer.status == 200 and answer.json()["chat"]["lines"][-1]["call"] == our_call(call)
    if answer.status != 200:
        assert our_call(call) == ""


# ---- the sked board


@settings(max_examples=150)
@given(st.data())
def test_no_request_to_the_board_is_answered_with_a_php_error_and_a_refused_one_stores_nothing(
    site: Site, data: st.DataObject
) -> None:
    """Mutations of the add, the remove and the refresh NeoAPRS posts get a documented answer."""
    site.fresh()
    action = data.draw(st.sampled_from(["add", "add", "remove", "refresh"]))
    if action == "remove":
        added = site.post_json("/api/v1/skeds.php", json.loads(sked_body("add", TOKEN, sked_fields())))
        assert added.status == 200
        base = json.loads(sked_body("remove", TOKEN, {"id": added.json()["id"]}))
    elif action == "add":
        base = json.loads(sked_body("add", TOKEN, sked_fields()))
    else:
        base = {"action": "refresh", "past": True}
    method, kind, body = data.draw(requests(base))
    places = (site.site / "skeds.json", site.site / "skeds-past.json", site.site / "private" / "skeds")
    before = site.kept(*places)
    answer = site.send(method, "/api/v1/skeds.php", body, {"Content-Type": kind} if kind else {})
    event(f"status {answer.status}")
    clean_answer(site, answer, SKED_REASONS, method)
    if answer.status != 200:
        assert site.kept(*places) == before
    elif method != "HEAD":
        assert answer.json()["board"] == json.loads((site.site / "skeds.json").read_bytes())


# times kept clear of the limits by a minute, so that the daemon's and the server's second agree
_OFFSETS = st.one_of(
    st.integers(-3 * 3600, 30 * 86400),
    st.integers(-40 * 86400, 40 * 86400),
    st.sampled_from([-3600, 3600, 30 * 86400 - 61, 30 * 86400 + 61]),
)
_LENGTHS = mostly(st.integers(60, 86400), st.one_of(st.integers(-3600, 30 * 3600), st.sampled_from([1, 86400, 86401])))


@settings(max_examples=120)
@given(
    mostly(_GOOD_CALL, _CALLS), _OFFSETS, _LENGTHS, mostly(_GOOD_DIAL, _DIALS), mostly(st.text(max_size=120), _ODD_TEXT)
)
def test_a_sked_neoaprs_posts_is_on_the_board_as_it_was_sent_and_its_delete_takes_it_off(
    site: Site, call: str, start: int, length: int, dial: str, note: str
) -> None:
    """The page's command and the daemon's checks let through only what the server takes; the board shows it as sent."""
    assume(abs(start + length) > 60 and abs(start - 30 * 86400) > 60)
    site.fresh()
    sent: list[tuple[bytes, int, bytes]] = []

    async def post(url: str, body: bytes, version: str, platform: str, max_bytes: int) -> tuple[int, bytes] | None:
        got = await post_board(url, body, version, platform, max_bytes)
        assert got is not None
        sent.append((body, *got))
        return got

    async def nothing(*_: object) -> tuple[int, bytes]:
        return 404, b""

    service = skedservice.Skeds(
        "0.26.1",
        "linux",
        lambda: Config.from_data({"station/call": call}),
        list,
        nothing,
        post,
        environ={skedservice.ENV_URL: f"{site.base}/skeds.json"},
        clock=lambda: datetime.now(UTC),
    )
    try:
        command = SkedPost.model_validate(
            {"cmd": "sked_post", "from": future(start), "to": future(start + length), "dial": dial, "note": note}
        )
    except ValueError:
        event("refused by the page's command")
        return
    begins, ends = when(command.from_), when(command.to)
    assert begins is not None and ends is not None
    try:
        run(service.post(begins, ends, command.dial, clean_note(command.note)))
    except (ValueError, skedservice.SkedError) as e:
        event("refused by the daemon")
        assert not sent, f"the server refused what the daemon sent: {e} {sent}"
        return
    [(body, status, answer)] = sent
    event("sent")
    clean_answer(site, Answer(status, {"content-type": "application/json; charset=utf-8"}, answer), SKED_REASONS)
    assert status == 200, answer
    posted = json.loads(body)
    [row] = [row for row in json.loads(answer)["board"]["skeds"] if row["id"] == json.loads(answer)["id"]]
    assert {k: row[k] for k in ("call", "from", "to", "dial", "note")} == {
        k: posted[k] for k in ("call", "from", "to", "dial", "note")
    }
    assert (row["call"], row["note"]) == (our_call(station(call)), clean_note(note))
    run(service.delete(row["id"]))
    assert len(sent) == 2 and sent[1][1] == 200
    assert row["id"] not in [r["id"] for r in json.loads(sent[1][2])["board"]["skeds"]]


# ---- the support files

_BUNDLE_NAMES = ["summary.txt", "README.txt", "settings.json", "logs/", "logs/neoaprs.log", "x.error.txt", "../evil"]


def a_bundle(names: list[str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as made:
        for name in names:
            made.writestr(name, "" if name.endswith("/") else f"{name}\n")
    return out.getvalue()


@st.composite
def bundles(draw: st.DrawFn) -> bytes:
    data = a_bundle(draw(st.lists(st.sampled_from(_BUNDLE_NAMES), min_size=1, max_size=5, unique=True)))
    op = draw(st.sampled_from(["as is", "as is", "flip", "cut", "junk"]))
    if op == "flip":
        at = draw(st.integers(0, len(data) - 1))
        return data[:at] + bytes([draw(st.integers(0, 255))]) + data[at + 1 :]
    if op == "cut":
        return data[: draw(st.integers(0, len(data)))]
    if op == "junk":
        return b"PK\x03\x04" + draw(st.binary(max_size=200)) + b"PK\x05\x06" + draw(st.binary(max_size=30))
    return data


_FIELD_NAMES = st.sampled_from(
    ["note", "email", "call", "version", "platform", "bundle", "note[]", "bundle[x]", "other"]
)


@settings(max_examples=150)
@given(
    st.dictionaries(_FIELD_NAMES, st.one_of(_ODD_TEXT, st.text(max_size=40)), max_size=6),
    st.dictionaries(
        _FIELD_NAMES, st.tuples(st.sampled_from(["neoaprs-support.zip", "", 'a"b']), bundles()), max_size=2
    ),
    st.sampled_from(["POST"] * 6 + METHODS),
    st.sampled_from(["form"] * 6 + ["raw", "json"]),
)
def test_no_request_to_send_logs_is_answered_with_a_php_error_and_a_refused_one_stores_nothing(
    site: Site, fields: dict[str, str], files: dict[str, tuple[str, bytes]], method: str, shape: str
) -> None:
    """Forms of any fields and files, a zip mutated or of foreign names, and other bodies get a documented answer."""
    site.fresh()
    kind, body = multipart(fields, files)
    if shape == "raw":
        body = body[: len(body) // 2]
    elif shape == "json":
        kind, body = "application/json", json.dumps(fields).encode()
    answer = site.send(method, "/support/send.php", body, {"Content-Type": kind})
    event(f"status {answer.status}")
    clean_answer(site, answer, SUPPORT_REASONS, method)
    stored = site.kept(site.support)
    if answer.status != 200:
        assert stored == {} and not site.mails.exists()
    elif method != "HEAD":
        ref = answer.json()["ref"]
        meta = json.loads(stored[str(site.support / f"{ref}.json")])
        assert meta["file"] == (str(site.support / f"{ref}.zip") in stored)
        if meta["file"]:
            assert stored[str(site.support / f"{ref}.zip")] == files["bundle"][1]


_NOTES = st.one_of(_ODD_TEXT, st.text(max_size=300), st.text(alphabet=st.characters(max_codepoint=0xA0), max_size=10))


def server_note(note: str) -> str:
    """The note as send.php keeps it, for the one fault the property leaves to its own test."""
    kept = re.sub("[^\t\n\x20-\x7e\xa0-\U0010ffff]", "", note.replace("\r\n", "\n").replace("\r", "\n"))
    return kept[:2000].strip(" \t\n\r\0\x0b")


@settings(max_examples=120)
@given(
    _NOTES,
    st.one_of(st.just(""), st.emails(), _ODD_TEXT, st.text(max_size=30).map(lambda t: f"{t}@{t}")),
    _CALLS,
    st.from_regex(r"\A[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}(-rc[0-9]|\+g[0-9a-f]{4})?\Z"),
    st.sampled_from(["linux", "linux-arm", "linux-appimage", "windows", "macos"]),
    st.booleans(),
)
def test_a_report_neoaprs_sends_is_taken_and_kept_as_sent(
    site: Site, note: str, email: str, call: str, version: str, platform: str, with_file: bool
) -> None:
    """What the dialog lets through is stored: the reply address as reply_address reads it, the rest as sent."""
    assume(with_file or server_note(note.strip()) != "")  # the fault of a note of no words is its own test below
    site.fresh()
    try:
        words, file = SupportSend.words(cast(SupportSend, None), {"note": note, "file": with_file})
    except tornado.web.HTTPError:
        assert not with_file
        return
    bundle = ("neoaprs-support.zip", a_bundle(["README.txt", "summary.txt"])) if file else None
    sent = run(
        send_bundle(
            f"{site.base}/support/send.php", bundle, words, reply_address(email), station(call), version, platform
        )
    )
    assert site.logged() == ""
    assert sent.ok, sent
    meta = json.loads((site.support / f"{sent.ref}.json").read_bytes())
    assert (meta["email"], meta["version"], meta["platform"], meta["file"]) == (
        reply_address(email),
        version,
        platform,
        bundle is not None,
    )
    assert meta["call"] == re.sub("[^A-Za-z0-9-]", "", station(call))[:12], (
        "the call of the settings, kept in send.php's form"
    )


@settings(max_examples=200)
@given(st.one_of(st.emails(), _ODD_TEXT, st.text(max_size=30).map(lambda t: f"{t}@x"), st.text(max_size=300)))
def test_the_server_reads_a_reply_address_as_neoaprs_does(site: Site, email: str) -> None:
    """send.php keeps exactly the address reply_address makes of a text, and '' for one it does not."""
    site.fresh()
    kind, body = multipart({"note": "hello", "email": email}, {})
    answer = site.send("POST", "/support/send.php", body, {"Content-Type": kind})
    clean_answer(site, answer, SUPPORT_REASONS)
    meta = json.loads((site.support / f"{answer.json()['ref']}.json").read_bytes())
    assert meta["email"] == reply_address(email)


# ---- the update check, the satellites and the page views

_QUERY_VALUE = st.one_of(_ODD_TEXT, st.text(max_size=30), st.sampled_from(["0", "0.26.1", TOKEN, "linux"]))
_QUERY_KEY = st.sampled_from(["v", "os", "id", "v[]", "os[a]", "id[]", "v[a][b]", "x", "", "%ff", "v%00"])


@settings(max_examples=150)
@given(st.lists(st.tuples(_QUERY_KEY, _QUERY_VALUE), max_size=5), st.sampled_from(["GET"] * 4 + METHODS))
def test_the_update_check_is_always_answered_with_a_version_the_daemon_reads(
    site: Site, query: list[tuple[str, str]], method: str
) -> None:
    """Any query and method get the JSON parse_update reads, and nothing else on the page."""
    site.fresh()
    path = "/version.php?" + "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in query)
    answer = site.send(method, path)
    clean_answer(site, answer, None)
    assert answer.status == 200 and answer.headers["content-type"] == "application/json; charset=utf-8"
    if method != "HEAD":
        update = parse_update(answer.body)
        assert update is not None and update.version == "0.26.1" and update.hf_dial == "7.0541 MHz USB"


@settings(max_examples=100)
@given(
    st.from_regex(r"\A[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}(-rc[0-9])?\Z"),
    st.sampled_from(["linux", "linux-arm", "linux-appimage", "windows", "macos"]),
    st.sampled_from(["", "0", TOKEN]),
)
def test_the_update_checks_query_is_logged_and_counted_as_the_daemon_sent_it(
    site: Site, version: str, platform: str, install_id: str
) -> None:
    """request_url's version, platform and number are the log's line and the status library's record."""
    site.fresh()
    url = urllib.parse.urlsplit(request_url(f"{site.base}/version.php", version, platform, install_id))
    answer = site.send("GET", f"{url.path}?{url.query}")
    clean_answer(site, answer, None)
    [log] = (site.site / "log").glob("starts-*.log")
    [line] = log.read_text(encoding="utf-8").splitlines()
    assert line.split("\t")[1:] == [version, platform, install_id or "-"]
    records = site.records.read_text(encoding="utf-8").splitlines() if site.records.exists() else []
    assert [json.loads(r) for r in records] == (
        [] if install_id == "0" else [["neoaprs", version, platform, install_id]]
    )


@settings(max_examples=60)
@given(st.sampled_from(METHODS), st.text(max_size=20))
def test_the_satellites_are_answered_with_a_file_the_map_reads_or_a_refusal(
    site: Site, method: str, query: str
) -> None:
    """Any method and query get the list the map reads, or 405 for another method; never a PHP error."""
    answer = site.send(method, "/api/v1/satellites.php?" + urllib.parse.quote(query))
    assert not PHP_TEXT.search(answer.body) and site.logged() == ""
    assert answer.headers.get("content-type") == "application/json; charset=utf-8"
    if method in ("GET", "HEAD"):
        assert answer.status == 200
        if method == "GET":
            assert read_file(answer.body) is not None
    else:
        assert answer.status == 405 and json.loads(answer.body) == {"ok": False, "reason": "method"}


@settings(max_examples=120)
@given(
    st.sampled_from(["POST"] * 6 + METHODS),
    st.one_of(
        _JSON.map(lambda v: json.dumps(v).encode()),
        st.dictionaries(st.sampled_from(["path", "dwell", "ref", "w"]), _JSON).map(lambda v: json.dumps(v).encode()),
        st.binary(max_size=100),
        st.builds(lambda n: b'{"path": "' + b"a" * n + b'"}', st.integers(2000, 2100)),
    ),
)
def test_a_page_view_is_counted_only_when_it_is_one_and_never_answered_with_a_php_error(
    site: Site, method: str, body: bytes
) -> None:
    """A JSON value of at most 2048 bytes is counted and answered 204; else 400, 405 or 413; never a body."""
    site.fresh()
    answer = site.send(method, "/api/v1/view.php", body, {"Content-Type": "application/json"})
    assert not PHP_TEXT.search(answer.body) and site.logged() == "" and answer.body == b""
    records = site.records.read_text(encoding="utf-8").splitlines() if site.records.exists() else []
    if method != "POST":
        assert answer.status == 405
    elif len(body) > 2048:
        assert answer.status == 413
    else:
        try:
            value = json.loads(body)
        except ValueError:
            value = None
        counted = isinstance(value, (dict, list))
        assert answer.status == (204 if counted else 400)
        assert len(records) == (1 if counted else 0)
        if counted:
            assert json.loads(records[0])[0] == ("dwell" if isinstance(value, dict) and "dwell" in value else "view")
    if answer.status != 204:
        assert records == []


# ---- the faults found, each by its smallest request


def test_the_update_check_with_a_version_given_as_a_list_is_answered_with_json_alone(site: Site) -> None:
    site.fresh()
    answer = site.send("GET", "/version.php?v[]=1&os[a]=2")
    clean_answer(site, answer, None)
    assert parse_update(answer.body) is not None


@pytest.mark.xfail(
    strict=True,
    reason="fault: a note of control characters alone passes the dialog and the daemon, and send.php refuses it",
)
def test_a_note_alone_the_daemon_sends_is_taken(site: Site) -> None:
    site.fresh()
    note, file = SupportSend.words(cast(SupportSend, None), {"note": "\x00", "file": False})
    assert file is False
    sent = run(send_bundle(f"{site.base}/support/send.php", None, note, "", "OH2GBA", "0.26.1", "linux"))
    assert sent.ok, sent
