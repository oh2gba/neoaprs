"""The sked board of the project's server (server/neo/api/v1/skeds.php) under PHP's own web server on the loopback, in a folder laid out as the site is (the endpoint in api/v1/, the board skeds.json in the root,
the stored skeds in private/skeds/): an add is kept in a file of its own and the board is written beside the site's files, without the token or its hash; a remove needs the token that posted; every refusal
answers its reason with its status; the limits for a token, a call and the whole board, and the rate limit by the hash of the address; ended skeds and the skeds of a blocked call are removed at every write;
the closed switch; two writers at once under the one lock; hostile input (control and invisible characters, an over-long body, a wrong content type, a path in an id). Skipped without `php`."""
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from tests.support.ptyline import posix_only

pytestmark = posix_only

ROOT = Path(__file__).resolve().parent.parent
PHP = shutil.which("php")
ID = re.compile(r"^[0-9a-f]{12}$")
HOUR = datetime.timedelta(hours=1)
DAY = datetime.timedelta(days=1)
DIAL = "7.0541 MHz USB"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def at(offset: datetime.timedelta) -> str:
    """The instant `offset` from now, to the minute, as the board writes it."""
    now = datetime.datetime.now(datetime.UTC).replace(second=0, microsecond=0)
    return (now + offset).strftime("%Y-%m-%dT%H:%M:%SZ")


def token() -> str:
    """A token as an installation makes it: made here, for this test."""
    return secrets.token_hex(16)


class Endpoint:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.site = folder / "site"
        self.board = self.site / "skeds.json"
        self.stored = self.site / "private" / "skeds"
        self.process: subprocess.Popen[bytes] | None = None
        self.port = free_port()

    def start(self, workers: int = 1) -> None:
        (self.site / "api" / "v1").mkdir(parents=True)
        shutil.copy(ROOT / "server" / "neo" / "api" / "v1" / "skeds.php", self.site / "api" / "v1" / "skeds.php")
        environment = {"PATH": os.environ["PATH"], **({"PHP_CLI_SERVER_WORKERS": str(workers)} if workers > 1 else {})}
        assert PHP is not None
        for _ in range(3):
            self.process = subprocess.Popen([PHP, "-S", f"127.0.0.1:{self.port}", "-t", str(self.site)], env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/api/v1/skeds.php"

    def post(self, body: object, kind: str = "application/json", method: str = "POST") -> tuple[int, dict[str, Any]]:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        request = urllib.request.Request(self.url, data=data, method=method, headers={"Content-Type": kind})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                assert response.headers["Content-Type"] == "application/json; charset=utf-8" and response.headers["Cache-Control"] == "no-store"
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as e:
            assert e.headers["Content-Type"] == "application/json; charset=utf-8"
            return e.code, json.loads(e.read())

    def add(self, key: str, **over: object) -> tuple[int, dict[str, Any]]:
        return self.post({"action": "add", "token": key, "call": "OH2GBA", "from": at(HOUR), "to": at(3 * HOUR), "dial": DIAL, "note": "Mercury, 10 W", **over})

    def remove(self, key: str, sked: object) -> tuple[int, dict[str, Any]]:
        return self.post({"action": "remove", "token": key, "id": sked})

    def refresh(self) -> tuple[int, dict[str, Any]]:
        return self.post({"action": "refresh"})

    def served(self) -> dict[str, Any]:
        """The board as a reader gets it: the static file, not PHP."""
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/skeds.json", timeout=10) as response:
            return dict(json.loads(response.read()))

    def files(self) -> list[str]:
        return sorted(p.name for p in self.stored.glob("*.json") if p.name != "rate.json")

    def keep(self, sked: str, call: str = "OH2GBA", start: str | None = None, end: str | None = None, key: str | None = None) -> None:
        """A stored sked written as the endpoint writes it, for a board that would take many requests to fill."""
        self.stored.mkdir(parents=True, exist_ok=True)
        row = {"id": sked, "call": call, "from": start or at(HOUR), "to": end or at(2 * HOUR), "dial": DIAL, "note": "", "token": hashlib.sha256((key or token()).encode()).hexdigest(), "posted": at(-HOUR)}
        (self.stored / f"{sked}.json").write_text(json.dumps(row), encoding="utf-8")

    def counted(self) -> int:
        path = self.stored / "rate.json"
        return sum(len(times) for times in json.loads(path.read_text(encoding="utf-8")).values()) if path.exists() else 0


@pytest.fixture
def endpoint(tmp_path: Path) -> Iterator[Endpoint]:
    if PHP is None:
        pytest.skip("needs php")
    served = Endpoint(tmp_path / "server")
    served.folder.mkdir()
    yield served
    served.stop()


def test_an_add_is_kept_in_its_own_file_and_the_board_is_written_beside_the_site_without_the_token(endpoint: Endpoint) -> None:
    endpoint.start()
    key = token()
    start, end = at(HOUR), at(3 * HOUR)
    code, answer = endpoint.add(key, call="oh2gba-0", **{"from": start, "to": end})
    sked = str(answer["id"])
    assert code == 200 and answer["ok"] is True and ID.match(sked)
    board = answer["board"]
    assert board["v"] == 1 and board["closed"] is False and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", board["written"])
    assert board["skeds"] == [{"id": sked, "call": "OH2GBA", "from": start, "to": end, "dial": DIAL, "note": "Mercury, 10 W"}]
    assert json.loads(endpoint.board.read_text(encoding="utf-8")) == board == endpoint.served()
    kept = json.loads((endpoint.stored / f"{sked}.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(key.encode()).hexdigest()
    assert kept["token"] == digest and kept["call"] == "OH2GBA" and kept["from"] == start
    for text in (endpoint.board.read_text(encoding="utf-8"), json.dumps(answer)):
        assert key not in text and digest not in text and "token" not in text
    assert not list(endpoint.site.rglob("*.part")), "no half-written file is left"
    assert (endpoint.stored / ".htaccess").read_text(encoding="utf-8") == "Require all denied\n"


def test_the_same_sked_posted_again_is_answered_with_its_id(endpoint: Endpoint) -> None:
    endpoint.start()
    key = token()
    first = endpoint.add(key)[1]["id"]
    assert endpoint.add(key)[1]["id"] == first and endpoint.files() == [f"{first}.json"]
    assert endpoint.add(token())[1]["id"] != first, "another installation's is a sked of its own"


def test_only_the_token_that_posted_removes_and_a_wrong_one_is_counted(endpoint: Endpoint) -> None:
    endpoint.start()
    key = token()
    sked = str(endpoint.add(key)[1]["id"])
    before = endpoint.counted()
    assert endpoint.remove(token(), sked) == (403, {"ok": False, "reason": "not_yours"})
    assert endpoint.files() == [f"{sked}.json"] and endpoint.counted() == before + 1
    code, answer = endpoint.remove(key, sked)
    assert code == 200 and answer["ok"] is True and answer["board"]["skeds"] == [] and endpoint.served()["skeds"] == []
    assert endpoint.files() == [] and endpoint.counted() == before + 1, "a remove with the right token is not counted"
    code, answer = endpoint.remove(key, sked)
    assert code == 200 and answer["board"]["skeds"] == [], "an id that is gone is answered with the board"


@pytest.mark.parametrize("over", [
    {"token": None}, {"token": "abc"}, {"token": "G" * 32}, {"token": "A" * 32}, {"token": 12345},
    {"call": None}, {"call": "N0CALL"}, {"call": "OH"}, {"call": "ABCDEF"}, {"call": "123456"}, {"call": "OH2GBA-16"}, {"call": "OH2GBA/P"}, {"call": "OH2GBAXX"}, {"call": ["OH2GBA"]},
    {"dial": None}, {"dial": "7.0541 MHz"}, {"dial": "7.0541 MHz FM"}, {"dial": "145.800 MHz USB"}, {"dial": "7,0541 MHz USB"}, {"dial": 7.0541},
    {"from": None}, {"from": "2026-02-30T10:00:00Z"}, {"from": "2026-11-14T18:00:00"}, {"from": "2026-11-14 18:00:00Z"}, {"from": "2026-11-14T18:00:00+02:00"}, {"from": 1790000000},
    {"to": "2026-11-14T24:00:00Z"}, {"from": at(2 * HOUR), "to": at(2 * HOUR)}, {"from": at(3 * HOUR), "to": at(2 * HOUR)},
    {"note": 5}, {"note": ["a"]}, {"action": "change"}, {"action": None},
])
def test_what_is_not_a_sked_is_a_bad_request_and_nothing_is_kept(endpoint: Endpoint, over: dict[str, object]) -> None:
    endpoint.start()
    assert endpoint.add(token(), **over) == (400, {"ok": False, "reason": "bad_request"}), over
    assert endpoint.files() == []


@pytest.mark.parametrize("body", [b"", b"not json", b"[1, 2]", b'"add"', b"{}", b'{"action": "add"', b'{"action": "add", "a": {"b": {"c": {"d": 1}}}}'])
def test_a_body_that_is_no_request_is_a_bad_request(endpoint: Endpoint, body: bytes) -> None:
    endpoint.start()
    assert endpoint.post(body) == (400, {"ok": False, "reason": "bad_request"})


def test_a_note_that_is_not_utf8_is_a_bad_request(endpoint: Endpoint) -> None:
    endpoint.start()
    body = b'{"action": "add", "token": "' + token().encode() + b'", "call": "OH2GBA", "from": "' + at(HOUR).encode() + b'", "to": "' + at(2 * HOUR).encode() + b'", "dial": "7.0541 MHz USB", "note": "\xff\xfe"}'
    assert endpoint.post(body) == (400, {"ok": False, "reason": "bad_request"})


def test_the_server_clock_refuses_the_past_the_far_and_the_long(endpoint: Endpoint) -> None:
    endpoint.start()
    key = token()
    assert endpoint.add(key, **{"from": at(-3 * HOUR), "to": at(-HOUR)}) == (422, {"ok": False, "reason": "past"})
    assert endpoint.add(key, **{"from": at(31 * DAY), "to": at(31 * DAY + HOUR)}) == (422, {"ok": False, "reason": "too_far"})
    assert endpoint.add(key, **{"from": at(HOUR), "to": at(HOUR + DAY + datetime.timedelta(minutes=30))}) == (422, {"ok": False, "reason": "too_long"})
    assert endpoint.files() == []
    assert endpoint.add(key, **{"from": at(-HOUR), "to": at(HOUR)})[0] == 200, "a sked that runs now is taken"
    assert endpoint.add(key, **{"from": at(29 * DAY), "to": at(29 * DAY + DAY)})[0] == 200, "24 hours, 29 days ahead"


def test_a_token_has_five_skeds_to_come(endpoint: Endpoint) -> None:
    endpoint.start()
    key = token()
    answers = [endpoint.add(key, **{"from": at((n + 1) * HOUR), "to": at((n + 2) * HOUR)}) for n in range(6)]
    assert [code for code, _ in answers] == [200] * 5 + [409] and answers[5][1] == {"ok": False, "reason": "full"}
    assert endpoint.add(token())[0] == 200, "another installation still posts under the same call"


def test_a_call_has_ten_skeds_to_come_whatever_its_ssid_and_the_board_a_hundred(endpoint: Endpoint) -> None:
    endpoint.start()
    for n in range(10):
        endpoint.keep(f"{n:012x}", call="OH2GBA" if n % 2 else "OH2GBA-7")
    assert endpoint.add(token(), call="OH2GBA-9") == (409, {"ok": False, "reason": "full"})
    assert endpoint.add(token(), call="OH2XYZ")[0] == 200
    for n in range(10, 99):
        endpoint.keep(f"{n:012x}", call=f"OH{n % 10}A{n:02d}")
    assert len(endpoint.files()) == 100
    assert endpoint.add(token(), call="OH3ABC") == (409, {"ok": False, "reason": "full"})


def test_the_board_is_sorted_by_its_start_and_holds_a_hundred_rows(endpoint: Endpoint) -> None:
    endpoint.start()
    for n in range(105):
        endpoint.keep(f"{n:012x}", call=f"OH{n % 10}A{n % 100:02d}", start=at((105 - n) * HOUR), end=at((106 - n) * HOUR))
    code, answer = endpoint.refresh()
    rows = answer["board"]["skeds"]
    assert code == 200 and len(rows) == 100 and [row["from"] for row in rows] == sorted(row["from"] for row in rows)
    assert rows[0]["id"] == f"{104:012x}"


def test_an_ended_sked_is_removed_at_the_next_write(endpoint: Endpoint) -> None:
    endpoint.start()
    key = token()
    ended, running = str(endpoint.add(key)[1]["id"]), str(endpoint.add(key, **{"from": at(-HOUR), "to": at(HOUR)})[1]["id"])
    path = endpoint.stored / f"{ended}.json"
    row = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(row | {"from": at(-3 * HOUR), "to": at(-datetime.timedelta(minutes=1))}), encoding="utf-8")
    code, answer = endpoint.refresh()
    assert code == 200 and [row["id"] for row in answer["board"]["skeds"]] == [running]
    assert endpoint.files() == [f"{running}.json"] and [row["id"] for row in endpoint.served()["skeds"]] == [running]


def test_a_stored_file_that_is_not_a_sked_of_ours_is_dropped(endpoint: Endpoint) -> None:
    endpoint.start()
    endpoint.stored.mkdir(parents=True)
    (endpoint.stored / "0123456789ab.json").write_text('{"id": "ffffffffffff", "call": "OH2GBA"}', encoding="utf-8")
    (endpoint.stored / "aaaaaaaaaaaa.json").write_text("not json", encoding="utf-8")
    endpoint.keep("bbbbbbbbbbbb", call="<b>x</b>")
    assert endpoint.refresh()[1]["board"]["skeds"] == [] and endpoint.files() == []


def test_the_closed_switch_refuses_every_add_and_the_board_says_so(endpoint: Endpoint) -> None:
    endpoint.start()
    key = token()
    sked = str(endpoint.add(key)[1]["id"])
    (endpoint.stored / "closed").write_text("", encoding="utf-8")
    assert endpoint.add(key, note="another") == (403, {"ok": False, "reason": "closed"})
    code, answer = endpoint.refresh()
    assert code == 200 and answer["board"]["closed"] is True and endpoint.served()["closed"] is True
    assert endpoint.remove(key, sked)[0] == 200, "what is there can still be deleted"
    (endpoint.stored / "closed").unlink()
    assert endpoint.add(key)[0] == 200 and endpoint.served()["closed"] is False


def test_a_blocked_call_cannot_add_and_its_skeds_go_at_the_next_write(endpoint: Endpoint) -> None:
    endpoint.start()
    kept = str(endpoint.add(token(), call="OH2XYZ")[1]["id"])
    endpoint.keep("cccccccccccc", call="OH2GBA-7")
    (endpoint.stored / "blocked.txt").write_text("# made up\noh2gba\n", encoding="utf-8")
    assert endpoint.add(token(), call="OH2GBA-5") == (403, {"ok": False, "reason": "closed"})
    assert [row["id"] for row in endpoint.refresh()[1]["board"]["skeds"]] == [kept] and endpoint.files() == [f"{kept}.json"]


def test_an_address_has_ten_adds_an_hour_and_only_its_hash_is_kept(endpoint: Endpoint) -> None:
    endpoint.start()
    key = token()
    sked = str(endpoint.add(key)[1]["id"])
    for n in range(9):
        assert endpoint.add(token(), call=f"OH{n}XYZ")[0] == 200
    body = json.dumps({"action": "add", "token": token(), "call": "OH2XYZ", "from": at(HOUR), "to": at(2 * HOUR), "dial": DIAL}).encode()
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(urllib.request.Request(endpoint.url, data=body, headers={"Content-Type": "application/json"}), timeout=10)
    assert e.value.code == 429 and json.loads(e.value.read()) == {"ok": False, "reason": "rate"} and e.value.headers["Retry-After"] == "3600"
    assert endpoint.refresh()[0] == 200, "a refresh is not held"
    assert endpoint.remove(token(), sked) == (429, {"ok": False, "reason": "rate"}), "a wrong token is held too"
    assert endpoint.remove(key, sked)[0] == 200, "the right token is not held"
    kept = "".join(p.read_text(encoding="utf-8", errors="replace") for p in endpoint.site.rglob("*") if p.is_file())
    assert "127.0.0.1" not in kept, "the address is written nowhere"
    rates = json.loads((endpoint.stored / "rate.json").read_text(encoding="utf-8"))
    assert len(rates) == 1 and all(re.fullmatch(r"[0-9a-f]{16}", k) for k in rates)
    path = endpoint.stored / "rate.json"
    path.write_text(json.dumps({k: [int(time.time()) - 3700] * 10 for k in rates}), encoding="utf-8")
    assert endpoint.add(token(), call="OH2XYZ")[0] == 200, "the hour gives the share back"


def test_a_flood_of_cheap_requests_cannot_keep_the_moderator_from_making_the_board_again(endpoint: Endpoint) -> None:
    endpoint.start()
    for _ in range(30):
        assert endpoint.refresh()[0] == 200
        assert endpoint.post({"action": "add"}) == (400, {"ok": False, "reason": "bad_request"})
        assert endpoint.add(token(), **{"from": at(-3 * HOUR), "to": at(-HOUR)}) == (422, {"ok": False, "reason": "past"})
    assert endpoint.counted() == 0, "a refresh, and an add that is not well formed or not within the times, are not counted"
    key = token()
    sked = str(endpoint.add(key)[1]["id"])
    assert endpoint.counted() == 1
    endpoint.stored.joinpath("rate.json").write_text(json.dumps({f"{n:016x}": [int(time.time())] * 10 for n in range(6)}), encoding="utf-8")
    assert endpoint.add(token(), call="OH2XYZ") == (429, {"ok": False, "reason": "rate"}), "the share of the hour is used up by others"
    (endpoint.stored / f"{sked}.json").unlink()
    (endpoint.stored / "closed").write_text("", encoding="utf-8")
    code, answer = endpoint.refresh()
    assert code == 200 and answer["board"]["skeds"] == [] and answer["board"]["closed"] is True and endpoint.served() == answer["board"], "the moderator's rm and close reach the board"


def test_a_refresh_writes_the_board_only_when_what_it_says_has_changed(endpoint: Endpoint) -> None:
    endpoint.start()
    endpoint.add(token())
    written = endpoint.board.read_bytes()
    endpoint.board.touch()
    stamp = endpoint.board.stat().st_mtime_ns
    time.sleep(1.1)
    code, answer = endpoint.refresh()
    assert code == 200 and endpoint.board.read_bytes() == written and endpoint.board.stat().st_mtime_ns == stamp and answer["board"] == json.loads(written)
    (endpoint.stored / "closed").write_text("", encoding="utf-8")
    assert endpoint.refresh()[1]["board"]["closed"] is True and json.loads(endpoint.board.read_text(encoding="utf-8"))["closed"] is True
    endpoint.board.write_text("garbage", encoding="utf-8")
    assert endpoint.refresh()[1]["board"]["closed"] is True and json.loads(endpoint.board.read_text(encoding="utf-8"))["closed"] is True, "a board that is not one is written again"


def test_two_writers_at_once_are_one_after_the_other(endpoint: Endpoint) -> None:
    endpoint.start(workers=4)
    key = token()
    with ThreadPoolExecutor(8) as pool:
        answers = list(pool.map(lambda n: endpoint.add(key, **{"from": at((n + 1) * HOUR), "to": at((n + 2) * HOUR)}), range(8)))
    codes = sorted(code for code, _ in answers)
    assert codes == [200] * 5 + [409] * 3, "the limit holds when the adds meet"
    ids = {str(answer["id"]) for code, answer in answers if code == 200}
    assert len(ids) == 5 and {f"{i}.json" for i in ids} == set(endpoint.files())
    assert {row["id"] for row in endpoint.served()["skeds"]} == ids, "the last board written has every sked"
    assert not list(endpoint.site.rglob("*.part"))


def test_the_note_is_one_line_without_control_or_invisible_characters_and_cut_to_80(endpoint: Endpoint) -> None:
    endpoint.start()
    note = "Mercury,\u200b 10\u00a0W\r\nline two\t\x00\x07\x1b[31m red \u202eevil\u202c \u2066x\u2069 \ufeffq\U0001f4fb \u00e4\u3042 " + "y" * 200
    code, answer = endpoint.add(token(), note=note)
    kept = answer["board"]["skeds"][0]["note"]
    assert code == 200 and kept.startswith("Mercury, 10 W line two [31m red evil x q \u00e4\u3042 y") and len(kept) == 80
    assert not re.search(r"[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff\n\r\t]", kept)
    assert [row["note"] for row in endpoint.add(token(), call="OH2XYZ", note="   ")[1]["board"]["skeds"] if row["call"] == "OH2XYZ"] == [""]


def test_markup_in_the_note_stays_text_in_json(endpoint: Endpoint) -> None:
    endpoint.start()
    endpoint.add(token(), note="<script>alert(1)</script> & co")
    raw = endpoint.board.read_text(encoding="utf-8")
    assert "<" not in raw and ">" not in raw and endpoint.served()["skeds"][0]["note"] == "<script>alert(1)</script> & co"


def test_a_body_over_2048_bytes_is_refused_before_it_is_parsed(endpoint: Endpoint) -> None:
    endpoint.start()
    assert endpoint.add(token(), note="x" * 3000) == (413, {"ok": False, "reason": "too_large"})
    assert endpoint.files() == [] and endpoint.counted() == 0, "refused before it is counted or kept"
    assert endpoint.add(token(), note="x" * 1500)[0] == 200


def test_a_body_without_its_length_is_read_only_to_the_limit(endpoint: Endpoint) -> None:
    endpoint.start()
    body = json.dumps({"action": "refresh", "pad": "x" * 4000}).encode()
    chunked = b"".join(b"%x\r\n%s\r\n" % (len(part), part) for part in (body[:1000], body[1000:])) + b"0\r\n\r\n"
    with socket.create_connection(("127.0.0.1", endpoint.port), timeout=10) as s:
        s.sendall(b"POST /api/v1/skeds.php HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n" + chunked)
        reply = b""
        while chunk := s.recv(4096):
            reply += chunk
    assert reply.startswith(b"HTTP/1.1 413") and b'{"ok":false,"reason":"too_large"}' in reply


@pytest.mark.parametrize("kind", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", "application/jsonx", ""])
def test_a_body_that_is_not_json_by_its_type_is_refused(endpoint: Endpoint, kind: str) -> None:
    endpoint.start()
    assert endpoint.post({"action": "refresh"}, kind=kind) == (415, {"ok": False, "reason": "bad_request"})
    assert endpoint.post({"action": "refresh"}, kind="application/json; charset=utf-8")[0] == 200


@pytest.mark.parametrize("sked", ["../../skeds", "../salt", "aaaaaaaaaaaa/../../x", "aaaaaaaaaaaa.json", "AAAAAAAAAAAA", "/etc/passwd", "aaaaaaaaaaa\u0000", "rate", 123456789012, None, ["aaaaaaaaaaaa"]])
def test_a_path_in_an_id_is_a_bad_request_and_touches_nothing(endpoint: Endpoint, sked: object) -> None:
    endpoint.start()
    key = token()
    endpoint.add(key)
    before = {p: p.read_bytes() for p in endpoint.site.rglob("*") if p.is_file() and p.name != "rate.json"}
    assert endpoint.remove(key, sked) == (400, {"ok": False, "reason": "bad_request"})
    assert {p: p.read_bytes() for p in endpoint.site.rglob("*") if p.is_file() and p.name != "rate.json"} == before


def test_only_a_post_is_answered(endpoint: Endpoint) -> None:
    endpoint.start()
    for method in ("GET", "PUT", "DELETE"):
        assert endpoint.post({"action": "refresh"}, method=method) == (405, {"ok": False, "reason": "method"}), method
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(endpoint.url, timeout=10)
    assert e.value.code == 405 and e.value.headers["Allow"] == "POST"
    assert not endpoint.board.exists(), "nothing is written for a refusal"


def test_the_board_and_the_stored_skeds_are_where_the_site_wants_them() -> None:
    assert not (ROOT / "site" / "skeds.json").exists(), "a board in site/ would be uploaded over the live one"
    deploy = (ROOT / "server" / "deploy.sh").read_text(encoding="utf-8")
    assert "skeds.json" in deploy
    assert "Disallow: /skeds.json" in (ROOT / "site" / "robots.txt").read_text(encoding="utf-8").splitlines()
    site = (ROOT / "server" / "neo" / ".htaccess").read_text(encoding="utf-8")
    assert r"RewriteRule ^private(/|$) - [F,L]" in site and "api/v1/skeds.php" in site and r'<FilesMatch "\.part$">' in site
    endpoint = (ROOT / "server" / "neo" / "api" / "v1" / "skeds.php").read_text(encoding="utf-8")
    assert "SITE_ROOT . '/skeds.json'" in endpoint and "SITE_ROOT . '/private/skeds'" in endpoint


def test_the_moderation_script_refuses_what_is_no_id_or_call_before_it_asks_for_any_login(tmp_path: Path) -> None:
    script = ROOT / "server" / "skeds.sh"
    environment = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "SECRETS_FILE": str(tmp_path / "none")}
    shown = subprocess.run([str(script), "--help"], env=environment, capture_output=True, text=True, timeout=30)
    assert shown.returncode == 0 and "--list" in shown.stdout and "rm" in shown.stdout and "close" in shown.stdout and "block" in shown.stdout
    for args in (["rm", "../salt"], ["rm"], ["rm", "--since", "yesterday"], ["block", "OH2GBA; rm -rf /"], ["block"], ["unblock", "x y"], ["remove"], []):
        done = subprocess.run([str(script), *args], env=environment, capture_output=True, text=True, timeout=30)
        assert done.returncode == 2, (args, done.stdout, done.stderr)
    done = subprocess.run([str(script), "rm", "0123456789ab"], env=environment, capture_output=True, text=True, timeout=30)
    assert done.returncode == 1 and "no .secrets file" in done.stderr, "a good id goes on to the login"
