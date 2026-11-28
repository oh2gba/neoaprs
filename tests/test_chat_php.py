"""The chat of the project's server (server/neo/api/v1/chat.php) under PHP's web server on the loopback
in a folder laid out as the site is: a line is kept with its token's hash, the chat is written beside
the site without it, and the history is the newest hundred lines.
"""

import datetime
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from tests.support.phpserver import PHP, PhpServer
from tests.support.ptyline import posix_only

pytestmark = posix_only

ROOT = Path(__file__).resolve().parent.parent
MAX_LINES = 100
RATE_PER_ADDRESS = 6


def ago(seconds: float) -> str:
    now = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=seconds)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def token() -> str:
    return secrets.token_hex(16)


class Endpoint(PhpServer):
    def __init__(self, folder: Path) -> None:
        super().__init__(folder / "site")
        self.chat = self.site / "chat.json"
        self.stored = self.site / "private" / "chat"
        self.blocked = self.site / "private" / "skeds" / "blocked.txt"

    def start(self, workers: int = 1) -> None:
        (self.site / "api" / "v1").mkdir(parents=True)
        (self.site / "private").mkdir()
        shutil.copy(ROOT / "server" / "neo" / "api" / "v1" / "chat.php", self.site / "api" / "v1" / "chat.php")
        shutil.copy(ROOT / "server" / "neo" / "private" / "endpoint.php", self.site / "private" / "endpoint.php")
        super().start(workers)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/api/v1/chat.php"

    def post(self, body: object, kind: str = "application/json", method: str = "POST") -> tuple[int, dict[str, Any]]:
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        request = urllib.request.Request(self.url, data=data, method=method, headers={"Content-Type": kind})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                assert response.headers["Content-Type"] == "application/json; charset=utf-8"
                assert response.headers["Cache-Control"] == "no-store"
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as e:
            assert e.headers["Content-Type"] == "application/json; charset=utf-8"
            return e.code, json.loads(e.read())

    def say(
        self, text: object = "QRV on 7.0541", key: str | None = None, call: object = "OH2GBA"
    ) -> tuple[int, dict[str, Any]]:
        return self.post({"action": "say", "token": key or token(), "call": call, "text": text})

    def refresh(self) -> tuple[int, dict[str, Any]]:
        return self.post({"action": "refresh"})

    def served(self) -> dict[str, Any]:
        """The chat as a reader gets it: the static file, not PHP."""
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/chat.json", timeout=10) as response:
            return dict(json.loads(response.read()))

    def keep(self, lines: list[dict[str, Any]], next_id: int) -> None:
        """The kept lines written as the endpoint writes them, for a history that would take many
        requests (and minutes of the brake) to fill."""
        self.stored.mkdir(parents=True, exist_ok=True)
        (self.stored / "lines.json").write_text(json.dumps({"next": next_id, "lines": lines}), encoding="utf-8")

    def forget_rate(self) -> None:
        (self.stored / "rate.json").unlink(missing_ok=True)


def kept_line(ident: int, seconds_ago: float = 60, call: str = "OH2XYZ", text: str = "hello") -> dict[str, Any]:
    return {"id": ident, "at": ago(seconds_ago), "call": call, "text": text, "token": hashlib.sha256(b"x").hexdigest()}


@pytest.fixture
def endpoint(tmp_path: Path) -> Iterator[Endpoint]:
    if PHP is None:
        pytest.skip("needs php")
    served = Endpoint(tmp_path / "server")
    yield served
    served.stop()


def test_a_line_is_kept_with_its_tokens_hash_and_the_chat_is_written_beside_the_site_without_it(
    endpoint: Endpoint,
) -> None:
    endpoint.start()
    key = token()
    code, answer = endpoint.say("  QRV   on 7.0541\tUSB ", key, call="oh2gba-0")
    assert code == 200 and answer["ok"] is True and answer["id"] == 1
    chat = answer["chat"]
    assert chat == endpoint.served(), "the answer is the file that is served"
    assert chat["v"] == 1 and chat["closed"] is False and set(chat) == {"v", "written", "closed", "lines"}
    [line] = chat["lines"]
    assert set(line) == {"id", "at", "call", "text"}
    assert (line["id"], line["call"], line["text"]) == (1, "OH2GBA", "QRV on 7.0541 USB")
    served = endpoint.chat.read_text(encoding="utf-8")
    digest = hashlib.sha256(key.encode()).hexdigest()
    assert key not in served and digest not in served, "neither the token nor its hash is served"
    stored = json.loads((endpoint.stored / "lines.json").read_text(encoding="utf-8"))
    assert stored["next"] == 2 and stored["lines"][0]["token"] == digest
    assert (endpoint.stored / ".htaccess").read_text(encoding="utf-8") == "Require all denied\n"
    assert endpoint.say("and another")[1]["id"] == 2, "an id grows by one with each line"


def test_what_is_no_line_is_refused_with_the_boards_codes_and_nothing_is_written(endpoint: Endpoint) -> None:
    endpoint.start()
    assert endpoint.post({"action": "say"}, method="GET")[0] == 405
    assert endpoint.post(b"x" * 1025) == (413, {"ok": False, "reason": "too_large"})
    assert endpoint.post({"action": "say"}, kind="text/plain") == (415, {"ok": False, "reason": "bad_request"})
    for body in (b"not json", b"[]", b'"say"', {"action": "remove", "id": 1}, {"action": "say"}):
        assert endpoint.post(body) == (400, {"ok": False, "reason": "bad_request"}), body
    for over in ({"token": "A" * 32}, {"token": "a" * 31}, {"call": "N0CALL"}, {"call": "OH2GBA/P"}, {"call": 7}):
        body = {"action": "say", "token": token(), "call": "OH2GBA", "text": "hi", **over}
        assert endpoint.post(body) == (400, {"ok": False, "reason": "bad_request"}), over
    for text in ("", "   ", "\u200b\u2060", None, 5, ["hi"]):
        assert endpoint.say(text) == (400, {"ok": False, "reason": "bad_request"}), text
    assert not endpoint.chat.exists(), "nothing is written for a refusal"


def test_the_text_the_daemon_makes_is_the_text_the_server_makes(endpoint: Endpoint) -> None:
    endpoint.start()
    vectors = json.loads((ROOT / "ui" / "src" / "protocol" / "vectors.json").read_text(encoding="utf-8"))
    for case in vectors["chat_texts"]:
        endpoint.forget_rate()
        code, answer = endpoint.say(case["input"])
        if case["text"]:
            assert code == 200 and answer["chat"]["lines"][-1]["text"] == case["text"], case
        else:
            assert code == 400, case


def test_the_history_is_the_newest_hundred_lines_whatever_their_age(endpoint: Endpoint) -> None:
    endpoint.start()
    year = 365 * 86400
    endpoint.keep([kept_line(n, year) for n in range(1, 1 + MAX_LINES)], 1 + MAX_LINES)
    code, answer = endpoint.say("the newest")
    lines = answer["chat"]["lines"]
    assert code == 200 and len(lines) == MAX_LINES
    assert [line["id"] for line in lines] == list(range(2, 2 + MAX_LINES)), "oldest first, the oldest gone"
    assert lines[0]["text"] == "hello" and lines[-1]["text"] == "the newest" and answer["id"] == 1 + MAX_LINES
    stored = json.loads((endpoint.stored / "lines.json").read_text(encoding="utf-8"))
    assert len(stored["lines"]) == MAX_LINES and stored["next"] == 2 + MAX_LINES


def test_a_line_that_is_not_well_formed_is_left_out_and_the_ids_go_on(endpoint: Endpoint) -> None:
    endpoint.start()
    endpoint.keep([{"id": 7, "at": "yesterday", "call": "OH2XYZ", "text": "x"}, kept_line(8)], 9)
    code, answer = endpoint.refresh()
    assert code == 200 and [line["id"] for line in answer["chat"]["lines"]] == [8]
    assert endpoint.say("next")[1]["id"] == 9


def test_the_brake_stops_one_address_after_six_lines_a_minute_and_everyone_after_two_hundred(
    endpoint: Endpoint,
) -> None:
    endpoint.start()
    for n in range(RATE_PER_ADDRESS):
        assert endpoint.say(f"line {n}")[0] == 200, n
    refused = urllib.request.Request(
        endpoint.url,
        data=json.dumps({"action": "say", "token": token(), "call": "OH2GBA", "text": "one too many"}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(refused, timeout=30)
    assert e.value.code == 429 and e.value.headers["Retry-After"] == "60"
    assert json.loads(e.value.read()) == {"ok": False, "reason": "rate"}
    assert len(endpoint.served()["lines"]) == RATE_PER_ADDRESS
    now = int(time.time())
    others = {f"{n:016x}": [now] * 10 for n in range(20)}
    (endpoint.stored / "rate.json").write_text(json.dumps(others), encoding="utf-8")
    assert endpoint.say("from a quiet address") == (429, {"ok": False, "reason": "rate"}), "200 a minute in all"
    stale = {key: [now - 61] * 10 for key in others}
    (endpoint.stored / "rate.json").write_text(json.dumps(stale), encoding="utf-8")
    assert endpoint.say("a minute later")[0] == 200
    assert endpoint.refresh()[0] == 200, "a refresh is counted apart"


def test_a_closed_chat_refuses_every_line_and_says_so(endpoint: Endpoint) -> None:
    endpoint.start()
    assert endpoint.say("before")[0] == 200
    (endpoint.stored / "closed").touch()
    assert endpoint.say("during") == (403, {"ok": False, "reason": "closed"})
    code, answer = endpoint.refresh()
    assert code == 200 and answer["chat"]["closed"] is True and endpoint.served()["closed"] is True
    assert [line["text"] for line in answer["chat"]["lines"]] == ["before"], "what was said stays"
    (endpoint.stored / "closed").unlink()
    endpoint.refresh()
    assert endpoint.served()["closed"] is False and endpoint.say("after")[0] == 200


def test_a_blocked_call_is_refused_and_its_lines_and_a_removed_line_are_taken_out(endpoint: Endpoint) -> None:
    endpoint.start()
    assert endpoint.say("mine", call="OH2XYZ-7")[0] == 200
    assert endpoint.say("hello")[0] == 200
    assert endpoint.say("bye")[0] == 200
    endpoint.blocked.parent.mkdir(parents=True)
    endpoint.blocked.write_text("# the board's list\nOH2XYZ\n", encoding="utf-8")
    (endpoint.stored / "removed.txt").write_text("3\nnot an id\n", encoding="utf-8")
    assert endpoint.say("again", call="oh2xyz") == (403, {"ok": False, "reason": "closed"})
    code, answer = endpoint.refresh()
    assert code == 200 and [(line["id"], line["text"]) for line in answer["chat"]["lines"]] == [(2, "hello")]
    assert endpoint.say("on")[1]["id"] == 4, "an id taken out is never given again"


def test_a_refresh_writes_the_chat_only_when_what_it_says_has_changed(endpoint: Endpoint) -> None:
    endpoint.start()
    endpoint.say("one")
    before = endpoint.chat.read_bytes()
    back = time.time() - 100
    os.utime(endpoint.chat, (back, back))
    mtime = endpoint.chat.stat().st_mtime_ns
    assert endpoint.refresh()[0] == 200
    assert endpoint.chat.read_bytes() == before and endpoint.chat.stat().st_mtime_ns == mtime
    (endpoint.stored / "closed").touch()
    assert endpoint.refresh()[1]["chat"]["closed"] is True and endpoint.chat.stat().st_mtime_ns != mtime


def test_two_writers_at_once_lose_no_line_and_a_reader_never_gets_half_a_file(endpoint: Endpoint) -> None:
    endpoint.start(workers=4)
    torn: list[str] = []
    stop = threading.Event()

    def read() -> None:
        # The file itself: a rename is whole on disk. A web server that takes the length before it opens the
        # file can still cut a body at that instant; the daemon drops such a read and asks again.
        while not stop.is_set():
            try:
                json.loads(endpoint.chat.read_bytes())
            except FileNotFoundError:
                pass
            except ValueError as e:
                torn.append(repr(e))

    reader = threading.Thread(target=read)
    reader.start()
    try:
        with ThreadPoolExecutor(8) as pool:
            answers = list(pool.map(lambda n: endpoint.say(f"line {n}"), range(RATE_PER_ADDRESS)))
    finally:
        stop.set()
        reader.join(30)
    assert all(code == 200 for code, _ in answers), answers
    assert sorted(answer["id"] for _, answer in answers) == list(range(1, RATE_PER_ADDRESS + 1))
    lines = endpoint.served()["lines"]
    assert [line["id"] for line in lines] == list(range(1, RATE_PER_ADDRESS + 1))
    assert sorted(line["text"] for line in lines) == sorted(f"line {n}" for n in range(RATE_PER_ADDRESS))
    assert torn == [] and not list(endpoint.site.glob("*.part")) and not list(endpoint.stored.glob("*.part"))


def test_the_chat_is_where_the_site_wants_it_and_a_deploy_never_touches_it() -> None:
    assert not (ROOT / "site" / "chat.json").exists(), "a chat in site/ would be uploaded over the live one"
    deploy = (ROOT / "server" / "deploy.sh").read_text(encoding="utf-8")
    assert "for board in skeds.json skeds-past.json chat.json; do" in deploy
    site = (ROOT / "server" / "neo" / ".htaccess").read_text(encoding="utf-8")
    assert "api/v1/chat.php" in site and r'<FilesMatch "\.part$">' in site
    endpoint = (ROOT / "server" / "neo" / "api" / "v1" / "chat.php").read_text(encoding="utf-8")
    assert "SITE_ROOT . '/chat.json'" in endpoint and "SITE_ROOT . '/private/chat'" in endpoint
    assert "const MAX_LINES        = 100;" in endpoint and "KEEP" not in endpoint
    for path in (ROOT / "site").rglob("*"):
        if path.is_file() and path.suffix in (".html", ".js", ".css", ".txt", ".xml", ".json"):
            assert "chat.json" not in path.read_text(encoding="utf-8"), path


def test_the_moderation_script_refuses_what_is_no_id_or_call_before_it_asks_for_any_login(tmp_path: Path) -> None:
    script = ROOT / "server" / "chat.sh"
    environment = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "SECRETS_FILE": str(tmp_path / "none")}
    shown = subprocess.run([str(script), "--help"], env=environment, capture_output=True, text=True, timeout=30)
    assert shown.returncode == 0 and all(word in shown.stdout for word in ("--list", "rm", "close", "block"))
    assert "does not bring back the lines" in shown.stdout, "unblock lets new lines in; what was taken out stays out"
    for args in ([], ["rm"], ["rm", "0"], ["rm", "1x"], ["block"], ["block", "OH2GBA/P"], ["close", "now"], ["x"]):
        done = subprocess.run([str(script), *args], env=environment, capture_output=True, text=True, timeout=30)
        assert done.returncode == 2, (args, done.stdout, done.stderr)
    done = subprocess.run([str(script), "rm", "12"], env=environment, capture_output=True, text=True, timeout=30)
    assert done.returncode == 1 and "no .secrets file" in done.stderr, "a good id goes on to the login"


def test_refreshes_from_many_addresses_have_a_total_too(endpoint: Endpoint) -> None:
    """A refresh reads and writes its whole file under the lock: the hour's file cannot grow without end."""
    endpoint.start()
    endpoint.stored.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    others = {f"{n:016x}": [now] * 2 for n in range(1000)}
    (endpoint.stored / "refresh.json").write_text(json.dumps(others), encoding="utf-8")
    assert endpoint.refresh() == (429, {"ok": False, "reason": "rate"})
    (endpoint.stored / "refresh.json").write_text(json.dumps({k: [now - 3601] * 2 for k in others}), encoding="utf-8")
    assert endpoint.refresh()[0] == 200
